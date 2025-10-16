#!/usr/bin/env python3
"""
Диагностический скрипт для LIVE мониторинга работы Wave Detector модуля.
Запускает основного бота и анализирует его работу в течение 15+ минут.

КРИТИЧНЫЕ ПРОВЕРКИ:
1. Волны приходят каждые 15 минут
2. Сигналы обрабатываются корректно
3. Позиции открываются с SL
4. SL ордера имеют reduceOnly=True (Binance) или position-attached (Bybit)
"""

import subprocess
import time
import re
from datetime import datetime, timedelta
import json
import sys

# Конфигурация
BOT_COMMAND = ["python", "main.py", "--mode", "production"]
LOG_FILE = "wave_detector_live_diagnostic.log"
MONITOR_DURATION = 15 * 60 + 120  # 15 минут + 2 минуты буфер
CHECK_INTERVAL = 1  # Проверка каждую секунду


class WaveDetectorLiveMonitor:
    def __init__(self):
        self.start_time = datetime.now()
        self.waves_detected = 0
        self.signals_received = 0
        self.signals_selected = 0
        self.signals_filtered = 0
        self.positions_opened = 0
        self.sl_orders_placed = 0
        self.errors = []
        self.warnings = []

        # КРИТИЧНО: Отслеживание reduceOnly
        self.sl_with_reduce_only = 0
        self.sl_without_reduce_only = 0

        # Паттерны для парсинга логов
        self.patterns = {
            # Wave patterns
            'wave_detected': r'🌊 Wave detected|Looking for wave|Wave \d+ complete',
            'wave_timestamp': r'Looking for wave with timestamp:\s*([0-9T:\-\+]+)',
            'signal_count': r'(\d+)\s+total signals',

            # Signal processing
            'top_selected': r'processing top (\d+)',
            'duplicate_filtered': r'(\d+)\s+duplicates',
            'signal_executed': r'Signal.*executed successfully|✅.*executed',

            # Position opening
            'position_opened': r'Position opened|📈 Position opened',
            'position_symbol': r'Position opened.*?([A-Z]+/USDT)',

            # Stop Loss - КРИТИЧНО
            'sl_placed': r'Stop Loss (set|placed|created)|SL (set|placed|created)',
            'sl_price': r'Stop Loss.*?at\s+([0-9.]+)',
            'reduce_only_true': r'reduceOnly.*[Tt]rue|reduceOnly:\s*[Tt]rue',
            'position_attached': r'position-attached|position_attached|trading_stop',

            # Errors and warnings
            'error': r'ERROR|Error:|❌',
            'warning': r'WARNING|⚠️',

            # Exchange specific
            'binance_order': r'binance|Binance|BINANCE',
            'bybit_order': r'bybit|Bybit|BYBIT',
        }

        # Tracking
        self.last_wave_time = None
        self.wave_intervals = []

    def start_bot(self):
        """Запуск основного бота"""
        print("=" * 80)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 WAVE DETECTOR LIVE ДИАГНОСТИКА")
        print("=" * 80)
        print(f"Команда запуска: {' '.join(BOT_COMMAND)}")
        print(f"Длительность мониторинга: {MONITOR_DURATION // 60} минут")
        print(f"Логи сохраняются в: {LOG_FILE}\n")

        with open(LOG_FILE, 'w') as log_file:
            log_file.write(f"=== WAVE DETECTOR LIVE DIAGNOSTIC START: {datetime.now()} ===\n\n")

        self.bot_process = subprocess.Popen(
            BOT_COMMAND,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        return self.bot_process

    def analyze_log_line(self, line):
        """Анализ строки лога"""
        line_lower = line.lower()

        # === WAVE DETECTION ===
        if re.search(self.patterns['wave_detected'], line, re.IGNORECASE):
            # Извлекаем timestamp волны
            ts_match = re.search(self.patterns['wave_timestamp'], line)
            if ts_match:
                wave_ts = ts_match.group(1)
                self.waves_detected += 1

                # Отслеживаем интервалы
                now = datetime.now()
                if self.last_wave_time:
                    interval = (now - self.last_wave_time).total_seconds() / 60
                    self.wave_intervals.append(interval)
                    print(f"\n[{now.strftime('%H:%M:%S')}] 🌊 ВОЛНА #{self.waves_detected}")
                    print(f"  ├─ Timestamp: {wave_ts}")
                    print(f"  ├─ Интервал с предыдущей: {interval:.1f} минут")
                else:
                    print(f"\n[{now.strftime('%H:%M:%S')}] 🌊 ВОЛНА #{self.waves_detected} (первая)")
                    print(f"  └─ Timestamp: {wave_ts}")

                self.last_wave_time = now

        # === SIGNAL PROCESSING ===
        if re.search(r'total signals', line):
            match = re.search(self.patterns['signal_count'], line)
            if match:
                count = int(match.group(1))
                self.signals_received += count
                print(f"  ├─ Получено сигналов: {count}")

        if re.search(r'processing top', line):
            match = re.search(self.patterns['top_selected'], line)
            if match:
                count = int(match.group(1))
                self.signals_selected = count
                print(f"  ├─ Отобрано топ: {count}")

        if re.search(r'duplicate', line_lower):
            match = re.search(r'(\d+)', line)
            if match:
                count = int(match.group(1))
                self.signals_filtered += count
                print(f"  ├─ Отфильтровано дубликатов: {count}")

        # === POSITION OPENING ===
        if re.search(self.patterns['signal_executed'], line, re.IGNORECASE):
            self.positions_opened += 1

            # Извлекаем символ
            symbol_match = re.search(r'([A-Z]+/USDT|[A-Z]+USDT)', line)
            symbol = symbol_match.group(1) if symbol_match else 'UNKNOWN'

            # Определяем биржу
            exchange = 'UNKNOWN'
            if re.search(self.patterns['binance_order'], line):
                exchange = 'Binance'
            elif re.search(self.patterns['bybit_order'], line):
                exchange = 'Bybit'

            print(f"  ├─ ✅ Позиция #{self.positions_opened} открыта: {symbol} ({exchange})")

        # === STOP LOSS - КРИТИЧНАЯ ПРОВЕРКА ===
        if re.search(self.patterns['sl_placed'], line, re.IGNORECASE):
            self.sl_orders_placed += 1

            # Извлекаем цену SL
            price_match = re.search(self.patterns['sl_price'], line)
            sl_price = price_match.group(1) if price_match else 'N/A'

            # Определяем биржу
            exchange = 'UNKNOWN'
            if re.search(self.patterns['binance_order'], line):
                exchange = 'Binance'
            elif re.search(self.patterns['bybit_order'], line):
                exchange = 'Bybit'

            # КРИТИЧНО: Проверка reduceOnly
            has_reduce_only = bool(re.search(self.patterns['reduce_only_true'], line))
            is_position_attached = bool(re.search(self.patterns['position_attached'], line))

            if has_reduce_only or is_position_attached:
                self.sl_with_reduce_only += 1
                status = "✅ reduceOnly=True" if has_reduce_only else "✅ position-attached"
                print(f"  └─ 🛡️  SL #{self.sl_orders_placed} размещен: {sl_price} ({exchange}) - {status}")
            else:
                self.sl_without_reduce_only += 1
                warning = f"⚠️  WARNING: SL #{self.sl_orders_placed} БЕЗ reduceOnly! Exchange: {exchange}, Price: {sl_price}"
                print(f"  └─ {warning}")
                self.warnings.append(warning)

        # === ERRORS ===
        if re.search(self.patterns['error'], line):
            error_snippet = line.strip()[:150]
            self.errors.append(error_snippet)
            if len(self.errors) <= 5:  # Показываем первые 5
                print(f"  └─ ❌ ОШИБКА: {error_snippet}")

    def monitor(self):
        """Основной цикл мониторинга"""
        bot_process = self.start_bot()

        with open(LOG_FILE, 'a') as log_file:
            try:
                end_time = time.time() + MONITOR_DURATION

                while time.time() < end_time:
                    # Чтение вывода бота
                    line = bot_process.stdout.readline()
                    if line:
                        log_file.write(line)
                        log_file.flush()
                        self.analyze_log_line(line)

                    # Проверка что процесс жив
                    if bot_process.poll() is not None:
                        print(f"\n❌ БОТ ЗАВЕРШИЛСЯ ПРЕЖДЕВРЕМЕННО (код: {bot_process.returncode})")
                        break

                    time.sleep(0.1)

                # Завершение мониторинга
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ⏰ Время мониторинга истекло")

            except KeyboardInterrupt:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Мониторинг прерван пользователем")
            finally:
                bot_process.terminate()
                try:
                    bot_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    bot_process.kill()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 Бот остановлен")

    def generate_report(self):
        """Генерация итогового отчета"""
        duration = (datetime.now() - self.start_time).total_seconds() / 60

        print("\n" + "=" * 80)
        print("📊 LIVE ДИАГНОСТИЧЕСКИЙ ОТЧЕТ - WAVE DETECTOR MODULE")
        print("=" * 80)

        print(f"\n⏱️  ДЛИТЕЛЬНОСТЬ МОНИТОРИНГА: {duration:.1f} минут")
        print(f"   Старт: {self.start_time.strftime('%H:%M:%S')}")
        print(f"   Финиш: {datetime.now().strftime('%H:%M:%S')}")

        # === ВОЛНЫ ===
        print(f"\n🌊 ОБРАБОТКА ВОЛН:")
        print(f"   Волн обнаружено: {self.waves_detected}")
        expected_waves = max(1, int(duration / 15))
        print(f"   Ожидалось волн: ~{expected_waves} (каждые 15 мин)")

        if self.waves_detected == 0:
            print(f"   ❌ КРИТИЧНО: Ни одной волны не обнаружено!")
        elif self.waves_detected < expected_waves:
            print(f"   ⚠️  WARNING: Меньше волн чем ожидалось")
        else:
            print(f"   ✅ Количество волн соответствует ожиданиям")

        # Интервалы между волнами
        if self.wave_intervals:
            avg_interval = sum(self.wave_intervals) / len(self.wave_intervals)
            min_interval = min(self.wave_intervals)
            max_interval = max(self.wave_intervals)
            print(f"\n   Интервалы между волнами:")
            print(f"   ├─ Средний: {avg_interval:.1f} минут")
            print(f"   ├─ Минимум: {min_interval:.1f} минут")
            print(f"   └─ Максимум: {max_interval:.1f} минут")

            if abs(avg_interval - 15) > 2:
                print(f"   ⚠️  WARNING: Средний интервал отклоняется от 15 минут!")

        # === СИГНАЛЫ ===
        print(f"\n📡 СИГНАЛЫ:")
        print(f"   Всего получено: {self.signals_received}")
        print(f"   Отобрано (топ): {self.signals_selected}")
        print(f"   Отфильтровано (дубликаты): {self.signals_filtered}")

        if self.signals_received > 0:
            filter_rate = (self.signals_filtered / self.signals_received) * 100 if self.signals_received else 0
            print(f"   Процент фильтрации: {filter_rate:.1f}%")

        # === РАЗМЕЩЕНИЕ ОРДЕРОВ ===
        print(f"\n📝 РАЗМЕЩЕНИЕ ОРДЕРОВ:")
        print(f"   Позиций открыто: {self.positions_opened}")
        print(f"   SL ордеров размещено: {self.sl_orders_placed}")

        # === КРИТИЧНАЯ ПРОВЕРКА SL ===
        print(f"\n🔴 КРИТИЧНАЯ ПРОВЕРКА: Stop-Loss ордера")
        print(f"   SL с reduceOnly/position-attached: {self.sl_with_reduce_only}")
        print(f"   SL БЕЗ reduceOnly: {self.sl_without_reduce_only}")

        if self.positions_opened != self.sl_orders_placed:
            print(f"   ❌ КРИТИЧНО: Количество позиций и SL не совпадает!")
            print(f"      Разница: {abs(self.positions_opened - self.sl_orders_placed)}")
        else:
            print(f"   ✅ Каждая позиция имеет SL")

        if self.sl_without_reduce_only > 0:
            print(f"   ❌ КРИТИЧНО: Обнаружены SL БЕЗ reduceOnly!")
            print(f"      Количество: {self.sl_without_reduce_only}")
        else:
            print(f"   ✅ Все SL имеют reduceOnly или position-attached")

        # === ПРЕДУПРЕЖДЕНИЯ И ОШИБКИ ===
        print(f"\n⚠️  ПРЕДУПРЕЖДЕНИЯ: {len(self.warnings)}")
        for i, warning in enumerate(self.warnings[:10], 1):
            print(f"   {i}. {warning}")

        print(f"\n❌ ОШИБКИ: {len(self.errors)}")
        for i, error in enumerate(self.errors[:10], 1):
            print(f"   {i}. {error[:120]}")

        # === РЕКОМЕНДАЦИИ ===
        print(f"\n💡 РЕКОМЕНДАЦИИ:")

        if self.waves_detected == 0:
            print(f"   🔴 КРИТИЧНО: Проверь WebSocket подключение к {BOT_COMMAND}")

        if self.positions_opened == 0 and self.signals_received > 0:
            print(f"   🔴 КРИТИЧНО: Сигналы приходят, но позиции не открываются")

        if self.positions_opened != self.sl_orders_placed:
            print(f"   🔴 КРИТИЧНО: Не все позиции защищены SL - срочно исправить!")

        if self.sl_without_reduce_only > 0:
            print(f"   🔴 КРИТИЧНО: SL без reduceOnly БЛОКИРУЕТ МАРЖУ - срочно исправить!")

        if len(self.warnings) > 0:
            print(f"   🟡 Обнаружены предупреждения - проверь логи подробно")

        if len(self.errors) > 0:
            print(f"   🟡 Обнаружены ошибки - проверь логи подробно")

        if (self.waves_detected > 0 and self.positions_opened > 0 and
            self.positions_opened == self.sl_orders_placed and
            self.sl_without_reduce_only == 0):
            print(f"   🟢 Все проверки пройдены - система работает корректно!")

        print(f"\n📄 Полные логи сохранены в: {LOG_FILE}")
        print("=" * 80 + "\n")

        # === ИТОГОВАЯ ОЦЕНКА ===
        print("🎯 ИТОГОВАЯ ОЦЕНКА:")

        critical_issues = 0
        if self.waves_detected == 0:
            critical_issues += 1
        if self.positions_opened != self.sl_orders_placed:
            critical_issues += 1
        if self.sl_without_reduce_only > 0:
            critical_issues += 1

        if critical_issues == 0:
            print("   ✅ PASS - Система готова к production")
        elif critical_issues <= 2:
            print(f"   ⚠️  PARTIAL - Обнаружено {critical_issues} критичных проблем")
        else:
            print(f"   ❌ FAIL - Обнаружено {critical_issues} критичных проблем")

        print()


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════════╗
║  WAVE DETECTOR LIVE DIAGNOSTIC TOOL                          ║
║  Комплексный анализ работы Wave Detector модуля              ║
║  Длительность: 15+ минут                                     ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    monitor = WaveDetectorLiveMonitor()

    try:
        monitor.monitor()
    except Exception as e:
        print(f"\n❌ КРИТИЧНАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    finally:
        monitor.generate_report()
