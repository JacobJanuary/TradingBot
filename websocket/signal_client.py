#!/usr/bin/env python3
"""
WebSocket клиент для получения торговых сигналов
Используется в боте вместо прямого подключения к БД
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Callable, List, Dict
from enum import Enum

import websockets

logger = logging.getLogger('SignalWSClient')


class ConnectionState(Enum):
    """Состояния подключения"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    RECONNECTING = "reconnecting"


class SignalWebSocketClient:
    """
    WebSocket клиент для получения сигналов от сервера
    """

    def __init__(self, config: dict):
        # Настройки подключения
        self.server_url = config.get('SIGNAL_WS_URL', 'ws://localhost:8765')
        self.auth_token = config.get('SIGNAL_WS_TOKEN')
        self.auto_reconnect = config.get('AUTO_RECONNECT', True)
        self.reconnect_interval = int(config.get('RECONNECT_INTERVAL', 5))
        self.max_reconnect_attempts = int(config.get('MAX_RECONNECT_ATTEMPTS', -1))

        # Callbacks для обработки событий
        self.on_signals_callback: Optional[Callable] = None
        self.on_connect_callback: Optional[Callable] = None
        self.on_disconnect_callback: Optional[Callable] = None
        self.on_error_callback: Optional[Callable] = None

        # Состояние
        self.websocket = None
        self.state = ConnectionState.DISCONNECTED
        self.running = False
        self.reconnect_attempts = 0

        # Буфер последних сигналов
        self.signal_buffer: List[dict] = []
        self.buffer_size = int(config.get('SIGNAL_BUFFER_SIZE', 100))

        # Health monitoring settings
        self.health_check_enabled = config.get('HEALTH_CHECK_ENABLED', True)
        self.signal_timeout = int(config.get('SIGNAL_TIMEOUT', 900))  # 15 minutes default
        self.health_check_interval = int(config.get('HEALTH_CHECK_INTERVAL', 60))  # 1 minute

        # Статистика
        self.stats = {
            'connected_at': None,
            'signals_received': 0,
            'last_signal_time': None,
            'reconnections': 0,
            'total_bytes_received': 0
        }

        logger.info(f"Signal WebSocket Client initialized for {self.server_url}")

    def set_callbacks(self, **kwargs):
        """Установка callbacks для обработки событий"""
        if 'on_signals' in kwargs:
            self.on_signals_callback = kwargs['on_signals']
        if 'on_connect' in kwargs:
            self.on_connect_callback = kwargs['on_connect']
        if 'on_disconnect' in kwargs:
            self.on_disconnect_callback = kwargs['on_disconnect']
        if 'on_error' in kwargs:
            self.on_error_callback = kwargs['on_error']

    async def connect(self) -> bool:
        """Подключение к серверу"""
        try:
            self.state = ConnectionState.CONNECTING
            logger.info(f"Connecting to signal server: {self.server_url}")

            self.websocket = await websockets.connect(
                self.server_url,
                ping_interval=20,
                ping_timeout=10
            )

            self.state = ConnectionState.CONNECTED
            self.stats['connected_at'] = datetime.now()
            self.reconnect_attempts = 0

            logger.info("Connected to signal server")

            # Вызов callback подключения
            if self.on_connect_callback:
                await self.on_connect_callback()

            # Аутентификация
            success = await self.authenticate()

            if success:
                self.state = ConnectionState.AUTHENTICATED

            return success

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self.state = ConnectionState.DISCONNECTED

            if self.on_error_callback:
                await self.on_error_callback(e)

            return False

    async def authenticate(self) -> bool:
        """Аутентификация на сервере"""
        try:
            # Сначала читаем auth_required от сервера
            auth_req = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=5
            )
            auth_req_data = json.loads(auth_req)
            self.stats['total_bytes_received'] += len(auth_req)

            if auth_req_data.get('type') != 'auth_required':
                logger.error(f"Expected auth_required, got: {auth_req_data.get('type')}")
                return False

            # Теперь отправляем токен
            await self.websocket.send(json.dumps({
                'type': 'auth',
                'token': self.auth_token
            }))

            # Ждем ответ
            response = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=5
            )

            data = json.loads(response)
            self.stats['total_bytes_received'] += len(response)

            if data.get('type') == 'auth_success':
                logger.info("Authentication successful")
                logger.info(f"Server config: interval={data.get('query_interval')}s, "
                          f"window={data.get('signal_window')}min")
                return True
            else:
                logger.error(f"Authentication failed: {data.get('message')}")
                return False

        except asyncio.TimeoutError:
            logger.error("Authentication timeout")
            return False
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

    async def _cleanup_connection(self):
        """
        Полная очистка WebSocket connection и state

        Закрывает connection, очищает buffers, reset state
        """
        logger.info("🧹 Cleaning up old connection...")

        # 1. Закрываем WebSocket если есть
        if self.websocket:
            try:
                await asyncio.wait_for(
                    self.websocket.close(),
                    timeout=5.0
                )
                logger.debug("Old WebSocket closed")
            except asyncio.TimeoutError:
                logger.warning("WebSocket close timeout, forcing...")
            except Exception as e:
                logger.warning(f"Error closing websocket: {e}")
            finally:
                self.websocket = None

        # 2. Очищаем signal buffer
        old_buffer_size = len(self.signal_buffer)
        self.signal_buffer.clear()
        if old_buffer_size > 0:
            logger.debug(f"Cleared signal buffer ({old_buffer_size} signals)")

        # 3. Reset state (кроме reconnect_attempts - его сохраняем!)
        self.state = ConnectionState.DISCONNECTED

        logger.info("✅ Connection cleanup complete")

    async def _verify_connection_health(self, timeout: int = 60) -> bool:
        """
        Проверка работоспособности connection после reconnect

        Ждет получения первого сообщения в течение timeout секунд.
        Если сообщение приходит - connection работает.

        Args:
            timeout: Максимальное время ожидания первого сообщения (секунды)

        Returns:
            True если connection работает, False иначе
        """
        logger.info(f"🔍 Verifying connection health (timeout={timeout}s)...")

        initial_signals_received = self.stats['signals_received']
        start_time = datetime.now()

        # Ждем появления нового сигнала
        while (datetime.now() - start_time).total_seconds() < timeout:
            # Проверяем что получили новые данные
            if self.stats['signals_received'] > initial_signals_received:
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(f"✅ Connection health VERIFIED (first signal in {elapsed:.1f}s)")
                return True

            # Проверяем что connection все еще AUTHENTICATED
            if self.state != ConnectionState.AUTHENTICATED:
                logger.error(f"❌ Connection state changed to {self.state}")
                return False

            # Короткая пауза перед следующей проверкой
            await asyncio.sleep(2)

        # Timeout - сигналы не пришли
        logger.error(f"❌ Connection health check TIMEOUT ({timeout}s) - no signals received")
        return False

    def _check_signal_timeout(self) -> bool:
        """
        Проверка не истек ли timeout с последнего полученного сигнала

        Returns:
            True если все OK, False если timeout истек
        """
        if not self.health_check_enabled:
            return True

        if self.stats['last_signal_time'] is None:
            # Еще не получали сигналов - это OK после start/reconnect
            return True

        time_since_last_signal = (datetime.now() - self.stats['last_signal_time']).total_seconds()

        if time_since_last_signal > self.signal_timeout:
            logger.error(
                f"⚠️ SIGNAL TIMEOUT! Last signal was {time_since_last_signal:.0f}s ago "
                f"(threshold: {self.signal_timeout}s)"
            )
            return False

        return True

    async def handle_message(self, message: str):
        """Обработка сообщения от сервера"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')

            if msg_type == 'signals':
                # Обработка сигналов
                await self.handle_signals(data)

            elif msg_type == 'pong':
                # Ответ на ping
                logger.debug("Received pong")

            elif msg_type == 'stats':
                # Статистика сервера
                logger.info(f"Server stats: {data}")

            elif msg_type == 'error':
                logger.error(f"Server error: {data.get('message')}")
                if self.on_error_callback:
                    await self.on_error_callback(data.get('message'))

            elif msg_type in ['auth_required', 'auth_success', 'auth_failed']:
                # Сообщения аутентификации - игнорируем, т.к. обрабатываются в authenticate()
                logger.debug(f"Auth message: {msg_type}")

            else:
                logger.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON: {message[:100]}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def handle_signals(self, data: dict):
        """Обработка полученных сигналов"""
        signals = data.get('data', [])
        count = data.get('count', 0)

        logger.info(f"Received {count} signals")

        # Обновляем статистику
        self.stats['signals_received'] += count
        self.stats['last_signal_time'] = datetime.now()

        # ✅ PROTECTIVE SORT: Ensure signals are sorted DESC by (score_week + score_month)
        # Even though server sends sorted data, we add this as safety measure
        sorted_signals = sorted(
            signals,
            key=lambda s: s.get('score_week', 0) + s.get('score_month', 0),
            reverse=True
        )
        
        # Take FIRST N signals (best scores) - was [-N:] (last N)
        self.signal_buffer = sorted_signals[:self.buffer_size]
        
        logger.debug(f"Buffer updated: {len(self.signal_buffer)}/{self.buffer_size} signals (top score: week={sorted_signals[0].get('score_week') if sorted_signals else 'N/A'})")

        # Вызываем callback если установлен
        if self.on_signals_callback:
            await self.on_signals_callback(signals)

    async def reconnect(self):
        """
        Полное переподключение к серверу с очисткой state

        Changes:
        1. Полностью закрываем старое connection
        2. Очищаем все buffers и state
        3. Проверяем работоспособность после reconnect
        """
        if not self.auto_reconnect:
            logger.info("Auto-reconnect disabled")
            return False

        if self.max_reconnect_attempts > 0 and self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(f"Max reconnect attempts ({self.max_reconnect_attempts}) reached")
            return False

        self.state = ConnectionState.RECONNECTING
        self.reconnect_attempts += 1
        self.stats['reconnections'] += 1

        # ✅ NEW: Полная очистка старого connection
        await self._cleanup_connection()

        base_delay = self.reconnect_interval
        max_delay = 60
        delay = min(base_delay * (2 ** (self.reconnect_attempts - 1)), max_delay)

        logger.warning(
            f"🔄 Full reconnect (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts or '∞'}), "
            f"waiting {delay}s (exponential backoff)..."
        )

        await asyncio.sleep(delay)

        # Подключаемся
        success = await self.connect()

        if not success:
            return False

        # ✅ NEW: Verify connection health after reconnect
        health_ok = await self._verify_connection_health(timeout=60)

        if not health_ok:
            logger.error("❌ Connection health check FAILED after reconnect!")
            self.state = ConnectionState.DISCONNECTED
            return False

        logger.info("✅ Reconnect successful and verified!")
        return True

    async def run(self):
        """
        Основной цикл работы клиента с health monitoring

        Changes:
        1. Добавлен periodic health check
        2. Детекция "silent failure"
        3. Автоматический reconnect при timeout
        """
        self.running = True
        last_health_check = datetime.now()

        while self.running:
            try:
                # Подключаемся если не подключены
                if self.state in [ConnectionState.DISCONNECTED, ConnectionState.RECONNECTING]:
                    success = await self.connect()
                    if not success:
                        if self.auto_reconnect:
                            await self.reconnect()
                        else:
                            break
                        continue

                # ✅ NEW: Periodic health check
                now = datetime.now()
                if (now - last_health_check).total_seconds() >= self.health_check_interval:
                    if not self._check_signal_timeout():
                        logger.error("🔴 Health check FAILED - initiating reconnect")
                        self.state = ConnectionState.DISCONNECTED

                        if self.on_disconnect_callback:
                            await self.on_disconnect_callback()

                        if self.auto_reconnect:
                            await self.reconnect()
                        else:
                            break
                        continue

                    last_health_check = now

                # Читаем сообщения с timeout
                try:
                    # ✅ NEW: Read with timeout to allow health checks
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=self.health_check_interval
                    )

                    self.stats['total_bytes_received'] += len(message)
                    await self.handle_message(message)

                except asyncio.TimeoutError:
                    # Timeout is OK - просто делаем health check на следующей итерации
                    continue

            except websockets.exceptions.ConnectionClosed:
                logger.warning("Connection closed")
                self.state = ConnectionState.DISCONNECTED

                if self.on_disconnect_callback:
                    await self.on_disconnect_callback()

                if self.auto_reconnect:
                    await self.reconnect()
                else:
                    break

            except Exception as e:
                logger.error(f"Error in client loop: {e}")
                self.state = ConnectionState.DISCONNECTED

                if self.on_error_callback:
                    await self.on_error_callback(e)

                if self.auto_reconnect:
                    await self.reconnect()
                else:
                    break

    async def request_signals(self):
        """Запрос немедленной отправки сигналов"""
        if self.state == ConnectionState.AUTHENTICATED:
            try:
                await self.websocket.send(json.dumps({
                    'type': 'get_signals'
                }))
                logger.debug("Requested immediate signals")
                return True
            except (websockets.exceptions.ConnectionClosed, Exception) as e:
                logger.error(f"Failed to request signals: {e}")
                self.state = ConnectionState.DISCONNECTED
                if self.on_disconnect_callback:
                    await self.on_disconnect_callback()
                return False
        return False

    async def request_stats(self):
        """Запрос статистики сервера"""
        if self.state == ConnectionState.AUTHENTICATED:
            try:
                await self.websocket.send(json.dumps({
                    'type': 'get_stats'
                }))
                logger.debug("Requested server stats")
                return True
            except (websockets.exceptions.ConnectionClosed, Exception) as e:
                logger.error(f"Failed to request stats: {e}")
                self.state = ConnectionState.DISCONNECTED
                if self.on_disconnect_callback:
                    await self.on_disconnect_callback()
                return False
        return False

    async def ping(self) -> bool:
        """Отправка ping для проверки соединения"""
        if self.state == ConnectionState.AUTHENTICATED:
            try:
                await self.websocket.send(json.dumps({
                    'type': 'ping'
                }))
                return True
            except (ConnectionError, websockets.exceptions.WebSocketException, Exception) as e:
                logger.warning(f"Ping failed: {e}")
                self.state = ConnectionState.DISCONNECTED
                return False
        return False

    def get_stats(self) -> dict:
        """Получение статистики клиента"""
        now = datetime.now()

        # Calculate time since last signal
        time_since_last_signal = None
        if self.stats['last_signal_time']:
            time_since_last_signal = (now - self.stats['last_signal_time']).total_seconds()

        # Calculate uptime
        uptime = None
        if self.stats['connected_at']:
            uptime = (now - self.stats['connected_at']).total_seconds()

        return {
            'state': self.state.value,
            'reconnect_attempts': self.reconnect_attempts,
            'buffered_signals': len(self.signal_buffer),
            'time_since_last_signal': time_since_last_signal,  # ✅ NEW
            'uptime': uptime,  # ✅ NEW
            'health_status': 'OK' if self._check_signal_timeout() else 'TIMEOUT',  # ✅ NEW
            **self.stats
        }

    def get_last_signals(self, limit: int = 10) -> List[dict]:
        """Получение последних сигналов из буфера"""
        return self.signal_buffer[-limit:]
    
    def get_signals_by_timestamp(self, timestamp: str) -> List[Dict]:
        """
        Получить сигналы с конкретным timestamp из буфера
        
        Args:
            timestamp: ISO timestamp волны (например, '2025-10-08 15:30:00+00:00')
        
        Returns:
            List of signals matching the timestamp
        """
        matching = []
        
        # Normalize timestamp for comparison (убираем миллисекунды и timezone offset если есть)
        # Ищем совпадение по первым 19 символам (YYYY-MM-DDTHH:MM:SS)
        # timestamp может быть с 'T' или с пробелом, приводим к единому формату с 'T'
        search_ts = timestamp[:19] if len(timestamp) >= 19 else timestamp
        # Если в search_ts пробел вместо 'T', заменяем
        search_ts = search_ts.replace(' ', 'T')
        
        logger.info(f"[DEBUG] Searching for timestamp: '{search_ts}' in buffer of {len(self.signal_buffer)} signals")
        
        for idx, signal in enumerate(self.signal_buffer[:5]):  # Log first 5 for debugging
            signal_ts = signal.get('timestamp') or signal.get('created_at')
            logger.info(f"[DEBUG] Signal {idx}: timestamp='{signal_ts}', first_19='{str(signal_ts)[:19] if signal_ts else None}'")
        
        for signal in self.signal_buffer:
            # Check both 'timestamp' and 'created_at' fields
            signal_ts = signal.get('timestamp') or signal.get('created_at')
            if signal_ts:
                signal_ts_str = str(signal_ts)[:19]
                if signal_ts_str == search_ts:
                    matching.append(signal)
        
        logger.info(f"[DEBUG] Found {len(matching)} signals for timestamp {timestamp} in buffer of {len(self.signal_buffer)}")
        return matching

    async def stop(self):
        """Остановка клиента"""
        logger.info("Stopping signal client...")
        self.running = False
        self.auto_reconnect = False

        if self.websocket:
            await self.websocket.close()

        self.state = ConnectionState.DISCONNECTED
        logger.info("Signal client stopped")


class SignalProcessor:
    """
    Обработчик сигналов для интеграции в бота
    """

    def __init__(self, trading_bot):
        self.bot = trading_bot
        self.config = trading_bot.config

        # Создаем клиент
        self.client = SignalWebSocketClient(self.config)

        # Фильтры сигналов
        self.min_score = float(self.config.get('MIN_SIGNAL_SCORE', 0.7))
        self.max_signals = int(self.config.get('MAX_SIGNALS_TO_PROCESS', 5))
        self.allowed_exchanges = self.config.get('ALLOWED_EXCHANGES', '').split(',')

        # Статистика обработки
        self.processing_stats = {
            'total_received': 0,
            'filtered_out': 0,
            'processed': 0,
            'errors': 0
        }

        # Устанавливаем callbacks
        self.client.set_callbacks(
            on_signals=self.process_signals,
            on_connect=self.on_connect,
            on_disconnect=self.on_disconnect,
            on_error=self.on_error
        )

    async def process_signals(self, signals: List[dict]):
        """Обработка полученных сигналов"""
        logger.info(f"Processing {len(signals)} signals")
        self.processing_stats['total_received'] += len(signals)

        try:
            # Фильтрация сигналов
            filtered_signals = await self.filter_signals(signals)
            self.processing_stats['filtered_out'] += (len(signals) - len(filtered_signals))

            logger.info(f"Filtered to {len(filtered_signals)} signals")

            # Обработка топовых сигналов
            for signal in filtered_signals[:self.max_signals]:
                try:
                    await self.bot.strategy.process_signal(signal)
                    self.processing_stats['processed'] += 1
                except Exception as e:
                    logger.error(f"Error processing signal {signal.get('id')}: {e}")
                    self.processing_stats['errors'] += 1

        except Exception as e:
            logger.error(f"Error in signal processing: {e}")
            self.processing_stats['errors'] += 1

    async def filter_signals(self, signals: List[dict]) -> List[dict]:
        """Фильтрация сигналов по критериям"""
        filtered = []

        for signal in signals:
            # Проверка score
            if signal.get('score', 0) < self.min_score:
                continue

            # Проверка биржи
            if self.allowed_exchanges and signal.get('exchange') not in self.allowed_exchanges:
                continue

            # Дополнительные проверки
            if not signal.get('entry_price'):
                continue

            filtered.append(signal)

        # Сортировка по score
        filtered.sort(key=lambda x: x.get('score', 0), reverse=True)

        return filtered

    async def on_connect(self):
        """Обработчик подключения"""
        logger.info("Signal processor connected to server")
        await self.bot.notify("Signal stream connected")

    async def on_disconnect(self):
        """Обработчик отключения"""
        logger.warning("Signal processor disconnected from server")
        await self.bot.notify("Signal stream disconnected")

    async def on_error(self, error):
        """Обработчик ошибок"""
        logger.error(f"Signal processor error: {error}")
        await self.bot.notify(f"Signal stream error: {error}")

    async def start(self):
        """Запуск получения сигналов"""
        logger.info("Starting signal processor...")
        await self.client.run()

    async def stop(self):
        """Остановка обработки"""
        logger.info("Stopping signal processor...")
        await self.client.stop()

    def get_stats(self) -> dict:
        """Получение статистики"""
        return {
            'client': self.client.get_stats(),
            'processing': self.processing_stats
        }