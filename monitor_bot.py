#!/usr/bin/env python3
"""
Production Monitoring Script for Trading Bot
Monitors logs, database, and system health in real-time
Adapted for the actual Trading Bot architecture
"""

import sys
import time
import asyncpg
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, deque
from typing import Dict, List, Set, Any
import re
import asyncio
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv(override=True)

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

class Config:
    # Пути (из анализа кода)
    LOG_FILE = "logs/trading_bot.log"

    # База данных из .env
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 5433))
    DB_NAME = os.getenv('DB_NAME', 'fox_crypto')
    DB_USER = os.getenv('DB_USER', 'elcrypto')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')

    # Интервалы
    REPORT_INTERVAL = 600  # 10 минут
    MONITORING_DURATION = 8 * 3600  # 8 часов
    LOG_CHECK_INTERVAL = 1  # проверка логов каждую секунду

    # Пороги для алертов
    MAX_ERROR_RATE = 5  # ошибок за 10 минут
    MAX_WARNING_RATE = 20  # предупреждений за 10 минут
    MIN_WAVE_INTERVAL = 60  # минимум между волнами (секунды)
    MAX_POSITION_OPEN_TIME = 30  # максимум для открытия позиции (секунды)

    # Регулярные выражения для парсинга логов (на основе реального формата)
    LOG_PATTERNS = {
        # Волны и сигналы
        'wave_received': r'Wave signals received.*count[:\s]+(\d+)',
        'wave_processed': r'Wave processed.*positions created[:\s]+(\d+)',
        'signal_received': r'Signal received.*symbol[:\s]+(\w+)',

        # Позиции
        'position_opening': r'Opening position.*symbol[:\s]+(\w+)',
        'position_opened': r'Position opened.*symbol[:\s]+(\w+).*order_id[:\s]+(\w+)',
        'position_closed': r'Position closed.*symbol[:\s]+(\w+).*pnl[:\s]+([-\d.]+)',
        'position_updated': r'position_updated.*symbol[:\s]+(\w+).*unrealized_pnl[:\s]+([-\d.]+)',

        # Stop Loss
        'sl_creating': r'Creating stop loss.*symbol[:\s]+(\w+)',
        'sl_created': r'Stop loss created.*symbol[:\s]+(\w+).*price[:\s]+([\d.]+)',
        'sl_moved': r'Stop loss moved.*symbol[:\s]+(\w+).*from[:\s]+([\d.]+).*to[:\s]+([\d.]+)',
        'sl_checking': r'Checking position (\w+).*has_sl=(True|False)',

        # Trailing Stop
        'ts_activated': r'Trailing stop ACTIVATED.*symbol[:\s]+(\w+).*stop at[:\s]+([\d.]+)',
        'ts_updated': r'Trailing stop updated.*symbol[:\s]+(\w+).*new stop[:\s]+([\d.]+)',

        # Protection & Management
        'protection_check': r'Protection check.*found (\d+) positions without SL',
        'zombie_found': r'Found zombie order.*symbol[:\s]+(\w+)',
        'zombie_killed': r'Zombie order cancelled.*symbol[:\s]+(\w+)',
        'aged_position': r'Found aged position.*symbol[:\s]+(\w+).*age[=:\s]+([\d.]+)h',
        'aged_processed': r'Aged position processed.*symbol[:\s]+(\w+)',

        # WebSocket
        'ws_connected': r'Connected to (signal|binance|bybit) (?:server|WebSocket)',
        'ws_disconnected': r'WebSocket disconnected|Connection lost',
        'ws_reconnecting': r'Reconnecting to WebSocket',
        'ws_authenticated': r'Authentication successful',

        # Errors and Warnings
        'error': r'ERROR\s+-\s+(.+)',
        'warning': r'WARNING\s+-\s+(.+)',
        'critical': r'CRITICAL\s+-\s+(.+)',

        # Exchange operations
        'order_created': r'Order created.*symbol[:\s]+(\w+).*order_id[:\s]+(\w+)',
        'order_cancelled': r'Order cancelled.*symbol[:\s]+(\w+).*order_id[:\s]+(\w+)',
        'balance_update': r'Balance.*USDT[:\s]+([\d.]+)',

        # System events
        'sync_started': r'Position synchronization started',
        'sync_completed': r'Position sync completed.*synced[:\s]+(\d+)',
        'health_check': r'Health check.*status[:\s]+(\w+)',
    }

# ============================================================================
# КЛАССЫ ДЛЯ ОТСЛЕЖИВАНИЯ СОСТОЯНИЯ
# ============================================================================

class EventTracker:
    """Отслеживание событий и их частоты"""

    def __init__(self):
        self.events = defaultdict(list)
        self.errors = []
        self.warnings = []
        self.critical = []

    def add_event(self, event_type: str, data: Dict[str, Any]):
        event = {
            'timestamp': datetime.now(),
            'type': event_type,
            'data': data
        }
        self.events[event_type].append(event)

    def add_error(self, message: str, context: Dict = None):
        self.errors.append({
            'timestamp': datetime.now(),
            'message': message,
            'context': context or {}
        })

    def add_warning(self, message: str, context: Dict = None):
        self.warnings.append({
            'timestamp': datetime.now(),
            'message': message,
            'context': context or {}
        })

    def add_critical(self, message: str, context: Dict = None):
        self.critical.append({
            'timestamp': datetime.now(),
            'message': message,
            'context': context or {}
        })

    def get_events_since(self, minutes: int) -> Dict[str, List]:
        cutoff = datetime.now() - timedelta(minutes=minutes)
        recent = defaultdict(list)

        for event_type, events in self.events.items():
            recent[event_type] = [e for e in events if e['timestamp'] > cutoff]

        return recent

    def get_errors_since(self, minutes: int) -> List:
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [e for e in self.errors if e['timestamp'] > cutoff]

    def get_warnings_since(self, minutes: int) -> List:
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [w for w in self.warnings if w['timestamp'] > cutoff]


class PositionTracker:
    """Отслеживание состояния позиций"""

    def __init__(self):
        self.positions = {}  # symbol -> position_data
        self.pending_sl = {}  # positions waiting for SL
        self.ts_active = set()  # symbols with activated TS
        self.aged_positions = set()  # symbols marked as aged

    def position_opening(self, symbol: str, timestamp: datetime):
        self.positions[symbol] = {
            'opening_at': timestamp,
            'opened_at': None,
            'sl_created': False,
            'sl_price': None,
            'ts_activated': False,
            'last_sl_move': None,
            'sl_moves_count': 0,
            'is_aged': False
        }
        self.pending_sl[symbol] = timestamp

    def position_opened(self, symbol: str, order_id: str, timestamp: datetime):
        if symbol in self.positions:
            self.positions[symbol]['opened_at'] = timestamp
            self.positions[symbol]['order_id'] = order_id
        else:
            # Позиция открылась без opening event
            self.positions[symbol] = {
                'opening_at': timestamp,
                'opened_at': timestamp,
                'order_id': order_id,
                'sl_created': False,
                'sl_price': None,
                'ts_activated': False,
                'last_sl_move': None,
                'sl_moves_count': 0,
                'is_aged': False
            }
            self.pending_sl[symbol] = timestamp

    def sl_created(self, symbol: str, sl_price: str, timestamp: datetime):
        if symbol in self.positions:
            self.positions[symbol]['sl_created'] = True
            self.positions[symbol]['sl_price'] = sl_price
        if symbol in self.pending_sl:
            del self.pending_sl[symbol]

    def ts_activated(self, symbol: str, timestamp: datetime):
        if symbol in self.positions:
            self.positions[symbol]['ts_activated'] = True
            self.ts_active.add(symbol)

    def sl_moved(self, symbol: str, from_price: float, to_price: float, timestamp: datetime):
        if symbol in self.positions:
            self.positions[symbol]['last_sl_move'] = timestamp
            self.positions[symbol]['sl_moves_count'] += 1
            self.positions[symbol]['sl_price'] = str(to_price)

    def mark_aged(self, symbol: str):
        if symbol in self.positions:
            self.positions[symbol]['is_aged'] = True
            self.aged_positions.add(symbol)

    def position_closed(self, symbol: str):
        if symbol in self.positions:
            del self.positions[symbol]
        if symbol in self.pending_sl:
            del self.pending_sl[symbol]
        if symbol in self.ts_active:
            self.ts_active.remove(symbol)
        if symbol in self.aged_positions:
            self.aged_positions.remove(symbol)

    def get_unprotected(self, max_wait_seconds: int = 60) -> List[str]:
        """Позиции без SL дольше max_wait_seconds"""
        cutoff = datetime.now() - timedelta(seconds=max_wait_seconds)
        return [
            symbol for symbol, timestamp in self.pending_sl.items()
            if timestamp < cutoff
        ]


class DatabaseChecker:
    """Проверка согласованности БД с логами"""

    def __init__(self, config: Config):
        self.config = config
        self.pool = None

    async def initialize(self):
        """Инициализация подключения к БД"""
        try:
            self.pool = await asyncpg.create_pool(
                host=self.config.DB_HOST,
                port=self.config.DB_PORT,
                database=self.config.DB_NAME,
                user=self.config.DB_USER,
                password=self.config.DB_PASSWORD,
                min_size=1,
                max_size=2
            )
            print(f"✅ Connected to database {self.config.DB_NAME}")
        except Exception as e:
            print(f"❌ Failed to connect to database: {e}")

    async def close(self):
        """Закрытие подключения к БД"""
        if self.pool:
            await self.pool.close()

    async def get_open_positions(self) -> List[Dict]:
        """Получить открытые позиции из БД"""
        if not self.pool:
            return []

        try:
            query = """
                SELECT
                    id, symbol, exchange, side, quantity,
                    entry_price, has_stop_loss, stop_loss_price,
                    trailing_activated, status, opened_at,
                    unrealized_pnl
                FROM monitoring.positions
                WHERE status = 'OPEN'
            """

            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
                positions = [dict(row) for row in rows]
                return positions

        except Exception as e:
            print(f"❌ Error querying positions: {e}")
            return []

    async def get_active_orders(self) -> List[Dict]:
        """Получить активные ордера из БД"""
        if not self.pool:
            return []

        try:
            query = """
                SELECT
                    id, symbol, exchange, type, side,
                    status, created_at
                FROM trading.orders
                WHERE status IN ('open', 'NEW', 'PARTIALLY_FILLED', 'PENDING')
            """

            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
                orders = [dict(row) for row in rows]
                return orders

        except Exception as e:
            print(f"❌ Error querying orders: {e}")
            return []

    async def check_consistency(self, position_tracker: PositionTracker) -> List[Dict]:
        """Проверить согласованность логов и БД"""
        issues = []

        db_positions = await self.get_open_positions()
        log_positions = position_tracker.positions

        # Позиции в БД, но не в логах
        db_symbols = {p.get('symbol') for p in db_positions}
        log_symbols = set(log_positions.keys())

        missing_in_logs = db_symbols - log_symbols
        if missing_in_logs:
            issues.append({
                'type': 'positions_missing_in_logs',
                'symbols': list(missing_in_logs),
                'severity': 'HIGH'
            })

        missing_in_db = log_symbols - db_symbols
        if missing_in_db:
            issues.append({
                'type': 'positions_missing_in_db',
                'symbols': list(missing_in_db),
                'severity': 'CRITICAL'
            })

        # Проверка SL для каждой позиции в БД
        for pos in db_positions:
            symbol = pos.get('symbol')
            has_sl = pos.get('has_stop_loss')

            if not has_sl:
                issues.append({
                    'type': 'position_without_sl_in_db',
                    'symbol': symbol,
                    'severity': 'CRITICAL'
                })

        return issues


# ============================================================================
# ОСНОВНОЙ МОНИТОР
# ============================================================================

class BotMonitor:
    """Главный класс мониторинга"""

    def __init__(self):
        self.config = Config()
        self.event_tracker = EventTracker()
        self.position_tracker = PositionTracker()
        self.db_checker = DatabaseChecker(self.config)

        self.start_time = datetime.now()
        self.last_report_time = datetime.now()
        self.last_log_position = 0

        self.report_count = 0

        # Tracking specific issues
        self.reduce_only_issues = []
        self.heartbeat_issues = []

    async def initialize(self):
        """Инициализация монитора"""
        await self.db_checker.initialize()

    async def cleanup(self):
        """Очистка ресурсов"""
        await self.db_checker.close()

    def parse_log_line(self, line: str):
        """Парсинг одной строки лога"""
        line = line.strip()
        if not line:
            return

        # Проверка на критические ошибки
        if re.search(self.config.LOG_PATTERNS['critical'], line):
            match = re.search(self.config.LOG_PATTERNS['critical'], line)
            if match:
                self.event_tracker.add_critical(match.group(1))
                print(f"🚨 CRITICAL: {match.group(1)[:100]}")
                return

        # Проверка на ошибки
        if re.search(self.config.LOG_PATTERNS['error'], line):
            match = re.search(self.config.LOG_PATTERNS['error'], line)
            if match:
                error_msg = match.group(1)
                self.event_tracker.add_error(error_msg)

                # Проверка специфичных проблем
                if 'reduceOnly' in error_msg:
                    self.reduce_only_issues.append({
                        'timestamp': datetime.now(),
                        'message': error_msg
                    })
                    print(f"⚠️ ReduceOnly issue detected!")

                print(f"❌ ERROR: {error_msg[:100]}")
                return

        # Проверка на предупреждения
        if re.search(self.config.LOG_PATTERNS['warning'], line):
            match = re.search(self.config.LOG_PATTERNS['warning'], line)
            if match:
                self.event_tracker.add_warning(match.group(1))
                return

        # Парсинг событий
        for event_type, pattern in self.config.LOG_PATTERNS.items():
            if event_type in ['error', 'warning', 'critical']:
                continue

            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                self.handle_event(event_type, match, line)
                break

    def handle_event(self, event_type: str, match, full_line: str):
        """Обработка распознанного события"""
        timestamp = datetime.now()

        # Волны и сигналы
        if event_type == 'wave_received':
            count = int(match.group(1))
            self.event_tracker.add_event('wave_received', {'count': count})
            print(f"🌊 Wave received: {count} signals")

        elif event_type == 'wave_processed':
            positions = int(match.group(1))
            self.event_tracker.add_event('wave_processed', {'positions': positions})
            print(f"✅ Wave processed: {positions} positions created")

        # Позиции
        elif event_type == 'position_opening':
            symbol = match.group(1)
            self.position_tracker.position_opening(symbol, timestamp)
            self.event_tracker.add_event('position_opening', {'symbol': symbol})
            print(f"🔄 Opening position: {symbol}")

        elif event_type == 'position_opened':
            symbol = match.group(1)
            order_id = match.group(2)
            self.position_tracker.position_opened(symbol, order_id, timestamp)
            self.event_tracker.add_event('position_opened', {'symbol': symbol, 'order_id': order_id})
            print(f"📈 Position opened: {symbol} (order: {order_id})")

        elif event_type == 'position_closed':
            symbol = match.group(1)
            pnl = float(match.group(2))
            self.position_tracker.position_closed(symbol)
            self.event_tracker.add_event('position_closed', {'symbol': symbol, 'pnl': pnl})
            emoji = "✅" if pnl > 0 else "❌"
            print(f"{emoji} Position closed: {symbol} PnL: ${pnl:.2f}")

        # Stop Loss
        elif event_type == 'sl_created':
            symbol = match.group(1)
            sl_price = match.group(2)
            self.position_tracker.sl_created(symbol, sl_price, timestamp)
            self.event_tracker.add_event('sl_created', {'symbol': symbol, 'sl_price': sl_price})
            print(f"🛡️ SL created: {symbol} at {sl_price}")

        elif event_type == 'sl_checking':
            symbol = match.group(1)
            has_sl = match.group(2) == 'True'
            self.event_tracker.add_event('sl_checking', {'symbol': symbol, 'has_sl': has_sl})
            if not has_sl:
                print(f"⚠️ Position {symbol} has no SL!")

        # Trailing Stop
        elif event_type == 'ts_activated':
            symbol = match.group(1)
            stop_price = match.group(2)
            self.position_tracker.ts_activated(symbol, timestamp)
            self.event_tracker.add_event('ts_activated', {'symbol': symbol, 'stop_price': stop_price})
            print(f"🎯 TS activated: {symbol} at {stop_price}")

        elif event_type == 'ts_updated':
            symbol = match.group(1)
            new_stop = match.group(2)
            self.event_tracker.add_event('ts_updated', {'symbol': symbol, 'new_stop': new_stop})
            print(f"↗️ TS updated: {symbol} to {new_stop}")

        # Aged positions
        elif event_type == 'aged_position':
            symbol = match.group(1)
            age = float(match.group(2))
            self.position_tracker.mark_aged(symbol)
            self.event_tracker.add_event('aged_position', {'symbol': symbol, 'age_hours': age})
            print(f"⏰ Aged position: {symbol} ({age:.1f}h old)")

        # Zombie orders
        elif event_type == 'zombie_found':
            symbol = match.group(1)
            self.event_tracker.add_event('zombie_found', {'symbol': symbol})
            print(f"🧟 Zombie order found: {symbol}")

        elif event_type == 'zombie_killed':
            symbol = match.group(1)
            self.event_tracker.add_event('zombie_killed', {'symbol': symbol})
            print(f"💀 Zombie killed: {symbol}")

        # WebSocket events
        elif event_type == 'ws_disconnected':
            self.event_tracker.add_event('ws_disconnected', {})
            print(f"🔌 WebSocket disconnected!")

        elif event_type == 'ws_reconnecting':
            self.event_tracker.add_event('ws_reconnecting', {})
            print(f"🔄 WebSocket reconnecting...")

        elif event_type == 'ws_connected':
            service = match.group(1)
            self.event_tracker.add_event('ws_connected', {'service': service})
            print(f"✅ WebSocket connected: {service}")

    def tail_log_file(self):
        """Чтение новых строк из лог-файла"""
        try:
            with open(self.config.LOG_FILE, 'r', encoding='utf-8') as f:
                f.seek(self.last_log_position)
                new_lines = f.readlines()
                self.last_log_position = f.tell()

                for line in new_lines:
                    self.parse_log_line(line)

        except FileNotFoundError:
            print(f"❌ Log file not found: {self.config.LOG_FILE}")
        except Exception as e:
            print(f"❌ Error reading log: {e}")

    async def check_anomalies(self):
        """Проверка аномалий и проблем"""
        anomalies = []

        # Проверка незащищенных позиций
        unprotected = self.position_tracker.get_unprotected(max_wait_seconds=60)
        if unprotected:
            anomalies.append({
                'type': 'UNPROTECTED_POSITIONS',
                'severity': 'CRITICAL',
                'data': {'symbols': unprotected},
                'message': f"Positions without SL for >60s: {', '.join(unprotected)}"
            })

        # Проверка согласованности с БД
        db_issues = await self.db_checker.check_consistency(self.position_tracker)
        for issue in db_issues:
            anomalies.append({
                'type': 'DB_INCONSISTENCY',
                'severity': issue['severity'],
                'data': issue,
                'message': f"DB inconsistency: {issue['type']}"
            })

        # Проверка частоты ошибок
        recent_errors = self.event_tracker.get_errors_since(10)
        if len(recent_errors) > self.config.MAX_ERROR_RATE:
            anomalies.append({
                'type': 'HIGH_ERROR_RATE',
                'severity': 'HIGH',
                'data': {'count': len(recent_errors)},
                'message': f"Too many errors: {len(recent_errors)} in last 10 min"
            })

        # Проверка критических ошибок
        if self.event_tracker.critical:
            anomalies.append({
                'type': 'CRITICAL_ERRORS',
                'severity': 'CRITICAL',
                'data': {'count': len(self.event_tracker.critical)},
                'message': f"CRITICAL errors detected: {len(self.event_tracker.critical)}"
            })

        # Проверка специфичных проблем
        if self.reduce_only_issues:
            anomalies.append({
                'type': 'REDUCE_ONLY_MISSING',
                'severity': 'CRITICAL',
                'data': {'count': len(self.reduce_only_issues)},
                'message': f"ReduceOnly parameter missing in {len(self.reduce_only_issues)} orders!"
            })

        return anomalies

    async def generate_report(self):
        """Генерация отчета за последние 10 минут"""
        self.report_count += 1
        print("\n" + "="*80)
        print(f"📊 REPORT #{self.report_count} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)

        # Статистика событий
        recent_events = self.event_tracker.get_events_since(10)

        print("\n📈 Events Summary (last 10 minutes):")
        print(f"  🌊 Waves received: {len(recent_events.get('wave_received', []))}")
        print(f"  🌊 Waves processed: {len(recent_events.get('wave_processed', []))}")
        print(f"  📊 Positions opened: {len(recent_events.get('position_opened', []))}")
        print(f"  🛡️ SL created: {len(recent_events.get('sl_created', []))}")
        print(f"  🎯 TS activated: {len(recent_events.get('ts_activated', []))}")
        print(f"  ↗️ TS updated: {len(recent_events.get('ts_updated', []))}")
        print(f"  ✅ Positions closed: {len(recent_events.get('position_closed', []))}")
        print(f"  🧟 Zombies found: {len(recent_events.get('zombie_found', []))}")
        print(f"  💀 Zombies killed: {len(recent_events.get('zombie_killed', []))}")
        print(f"  ⏰ Aged positions: {len(recent_events.get('aged_position', []))}")
        print(f"  🔌 WS disconnects: {len(recent_events.get('ws_disconnected', []))}")
        print(f"  🔄 WS reconnects: {len(recent_events.get('ws_reconnecting', []))}")

        # Текущие позиции
        print(f"\n📍 Current State:")
        print(f"  Open positions: {len(self.position_tracker.positions)}")
        print(f"  Positions with TS active: {len(self.position_tracker.ts_active)}")
        print(f"  Pending SL creation: {len(self.position_tracker.pending_sl)}")
        print(f"  Aged positions: {len(self.position_tracker.aged_positions)}")

        # Детали по позициям
        if self.position_tracker.positions:
            print(f"\n  Position details:")
            for symbol, pos_data in list(self.position_tracker.positions.items())[:10]:
                status = []
                if pos_data['sl_created']:
                    status.append(f"✅ SL@{pos_data.get('sl_price', 'N/A')}")
                else:
                    status.append("❌ NO SL")
                if pos_data['ts_activated']:
                    status.append("🎯 TS active")
                if pos_data.get('is_aged'):
                    status.append("⏰ AGED")
                if pos_data['sl_moves_count'] > 0:
                    status.append(f"↗️ {pos_data['sl_moves_count']} moves")

                print(f"    • {symbol}: {' | '.join(status)}")

        # Ошибки и предупреждения
        recent_errors = self.event_tracker.get_errors_since(10)
        recent_warnings = self.event_tracker.get_warnings_since(10)

        print(f"\n⚠️ Issues:")
        print(f"  Errors: {len(recent_errors)}")
        print(f"  Warnings: {len(recent_warnings)}")
        print(f"  Critical: {len(self.event_tracker.critical)}")

        if recent_errors:
            print(f"\n  Recent errors:")
            for err in recent_errors[-5:]:  # последние 5
                print(f"    [{err['timestamp'].strftime('%H:%M:%S')}] {err['message'][:80]}")

        if self.event_tracker.critical:
            print(f"\n  🚨 CRITICAL errors:")
            for crit in self.event_tracker.critical[-3:]:
                print(f"    [{crit['timestamp'].strftime('%H:%M:%S')}] {crit['message'][:80]}")

        # Проверка аномалий
        anomalies = await self.check_anomalies()
        if anomalies:
            print(f"\n🚨 ANOMALIES DETECTED:")
            for anomaly in anomalies:
                severity_icon = {
                    'CRITICAL': '🔴',
                    'HIGH': '🟠',
                    'MEDIUM': '🟡',
                    'LOW': '🟢'
                }.get(anomaly['severity'], '⚪')

                print(f"  {severity_icon} [{anomaly['severity']}] {anomaly['message']}")
        else:
            print(f"\n✅ No anomalies detected")

        # Согласованность с БД
        print(f"\n💾 Database Consistency:")
        db_positions = await self.db_checker.get_open_positions()
        db_orders = await self.db_checker.get_active_orders()
        print(f"  DB open positions: {len(db_positions)}")
        print(f"  DB active orders: {len(db_orders)}")
        print(f"  Log tracked positions: {len(self.position_tracker.positions)}")

        diff = abs(len(db_positions) - len(self.position_tracker.positions))
        if diff > 0:
            print(f"  ⚠️ Mismatch: {diff} positions difference between DB and logs!")
        else:
            print(f"  ✅ DB and logs are in sync")

        # Специфичные проблемы
        if self.reduce_only_issues:
            print(f"\n🔴 CRITICAL: ReduceOnly parameter issues found!")
            print(f"  Count: {len(self.reduce_only_issues)}")

        print("\n" + "="*80 + "\n")

        # Сохранение отчета в файл
        await self.save_report_to_file(recent_events, anomalies)

    async def save_report_to_file(self, events, anomalies):
        """Сохранение отчета в JSON для последующего анализа"""
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'report_number': self.report_count,
            'events': {k: len(v) for k, v in events.items()},
            'positions': len(self.position_tracker.positions),
            'errors_count': len(self.event_tracker.get_errors_since(10)),
            'warnings_count': len(self.event_tracker.get_warnings_since(10)),
            'critical_count': len(self.event_tracker.critical),
            'anomalies': anomalies,
            'specific_issues': {
                'reduce_only_missing': len(self.reduce_only_issues),
                'heartbeat_issues': len(self.heartbeat_issues)
            }
        }

        report_file = f"monitoring_report_{self.report_count:03d}.json"
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)

    async def run(self):
        """Основной цикл мониторинга"""
        print("="*80)
        print("🚀 PRODUCTION MONITORING STARTED")
        print("="*80)
        print(f"Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration: {self.config.MONITORING_DURATION / 3600} hours")
        print(f"Report interval: {self.config.REPORT_INTERVAL} seconds")
        print(f"Log file: {self.config.LOG_FILE}")
        print(f"Database: {self.config.DB_NAME} @ {self.config.DB_HOST}:{self.config.DB_PORT}")
        print("="*80 + "\n")

        try:
            while True:
                # Проверка времени работы
                elapsed = (datetime.now() - self.start_time).total_seconds()
                if elapsed >= self.config.MONITORING_DURATION:
                    print("\n⏰ Monitoring duration completed!")
                    break

                # Чтение логов
                self.tail_log_file()

                # Генерация отчета каждые 10 минут
                time_since_report = (datetime.now() - self.last_report_time).total_seconds()
                if time_since_report >= self.config.REPORT_INTERVAL:
                    await self.generate_report()
                    self.last_report_time = datetime.now()

                # Задержка перед следующей итерацией
                await asyncio.sleep(self.config.LOG_CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n⚠️ Monitoring interrupted by user")
        except Exception as e:
            print(f"\n\n❌ Fatal error in monitoring: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.generate_final_report()

    async def generate_final_report(self):
        """Финальный отчет по завершению мониторинга"""
        print("\n" + "="*80)
        print("📋 FINAL REPORT")
        print("="*80)

        total_duration = (datetime.now() - self.start_time).total_seconds() / 3600

        print(f"\n⏱️ Monitoring Duration: {total_duration:.2f} hours")
        print(f"📊 Reports Generated: {self.report_count}")

        # Общая статистика
        all_events = self.event_tracker.events
        print(f"\n📈 Total Events:")
        for event_type, events in all_events.items():
            print(f"  {event_type}: {len(events)}")

        # Ошибки и предупреждения
        print(f"\n⚠️ Total Issues:")
        print(f"  Errors: {len(self.event_tracker.errors)}")
        print(f"  Warnings: {len(self.event_tracker.warnings)}")
        print(f"  Critical: {len(self.event_tracker.critical)}")

        # Специфичные проблемы
        print(f"\n🔍 Specific Issues Found:")
        print(f"  ReduceOnly missing: {len(self.reduce_only_issues)} times")
        print(f"  Heartbeat issues: {len(self.heartbeat_issues)} times")

        # Текущее состояние
        print(f"\n📍 Final State:")
        print(f"  Open positions: {len(self.position_tracker.positions)}")
        print(f"  Unprotected positions: {len(self.position_tracker.pending_sl)}")
        print(f"  Aged positions: {len(self.position_tracker.aged_positions)}")

        # Критические ошибки
        if self.event_tracker.critical:
            print(f"\n🚨 CRITICAL ERRORS FOUND DURING MONITORING:")
            for i, crit in enumerate(self.event_tracker.critical[:10], 1):
                print(f"  {i}. [{crit['timestamp'].strftime('%H:%M:%S')}] {crit['message'][:100]}")

        # Сохранение финального отчета
        final_report = {
            'monitoring_start': self.start_time.isoformat(),
            'monitoring_end': datetime.now().isoformat(),
            'duration_hours': total_duration,
            'total_events': {k: len(v) for k, v in all_events.items()},
            'total_errors': len(self.event_tracker.errors),
            'total_warnings': len(self.event_tracker.warnings),
            'total_critical': len(self.event_tracker.critical),
            'final_positions': len(self.position_tracker.positions),
            'specific_issues': {
                'reduce_only_missing': len(self.reduce_only_issues),
                'heartbeat_issues': len(self.heartbeat_issues)
            },
            'critical_errors': [
                {'timestamp': e['timestamp'].isoformat(), 'message': e['message']}
                for e in self.event_tracker.critical[:50]
            ]
        }

        with open('monitoring_final_report.json', 'w') as f:
            json.dump(final_report, f, indent=2, default=str)

        print(f"\n💾 Final report saved to: monitoring_final_report.json")
        print("="*80 + "\n")


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

async def main():
    """Основная асинхронная функция"""
    print("Initializing Production Monitor...\n")

    # Проверка наличия файлов
    if not Path(Config.LOG_FILE).exists():
        print(f"❌ ERROR: Log file not found: {Config.LOG_FILE}")
        print("Please ensure the trading bot is running")
        sys.exit(1)

    monitor = BotMonitor()
    await monitor.initialize()

    try:
        await monitor.run()
    finally:
        await monitor.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)