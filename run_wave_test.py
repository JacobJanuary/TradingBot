"""
Orchestrates the full 30-minute wave detection test
"""

import asyncio
import json
from datetime import datetime, timedelta
import sys
from pathlib import Path
from typing import Dict, List

from wave_monitor import WaveMonitor
from log_parser import LogParser


class WaveTestOrchestrator:
    """
    Управляет полным тестом:
    1. Pre-test snapshot
    2. Start monitoring
    3. Wait for 2 waves
    4. Collect all data
    5. Post-test analysis
    """

    def __init__(self, config_path: str):
        with open(config_path) as f:
            self.config = json.load(f)

        self.test_id = f"wave_test_{datetime.now():%Y%m%d_%H%M%S}"
        self.output_dir = Path(self.config['monitoring']['output_dir']) / self.test_id
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.monitor = None
        self.parser = LogParser()
        self.data_collected = []

        print(f"Test ID: {self.test_id}")
        print(f"Output directory: {self.output_dir}")

    def _calculate_next_wave_times(self, count: int) -> list:
        """Вычисляет времена следующих N волн"""
        now = datetime.now()
        check_minutes = [6, 20, 35, 50]
        current_minute = now.minute

        next_checks = []

        # Находим следующие проверки в текущем часе
        for minute in check_minutes:
            if minute > current_minute:
                next_time = now.replace(minute=minute, second=0, microsecond=0)
                next_checks.append(next_time)

        # Если нужно больше, добавляем из следующего часа
        if len(next_checks) < count:
            next_hour = now + timedelta(hours=1)
            for minute in check_minutes[:count - len(next_checks)]:
                next_time = next_hour.replace(minute=minute, second=0, microsecond=0)
                next_checks.append(next_time)

        return next_checks[:count]

    def _calculate_expected_timestamp(self, check_time: datetime) -> str:
        """
        Вычисляет expected timestamp по формуле из документации

        0-15 минут → timestamp :45 (предыдущий час)
        16-30 минут → timestamp :00
        31-45 минут → timestamp :15
        46-59 минут → timestamp :30
        """
        minute = check_time.minute

        if 0 <= minute < 15:
            # Предыдущий час :45
            expected = (check_time - timedelta(hours=1)).replace(minute=45, second=0, microsecond=0)
        elif 15 <= minute < 30:
            # Текущий час :00
            expected = check_time.replace(minute=0, second=0, microsecond=0)
        elif 30 <= minute < 45:
            # Текущий час :15
            expected = check_time.replace(minute=15, second=0, microsecond=0)
        else:  # 45-59
            # Текущий час :30
            expected = check_time.replace(minute=30, second=0, microsecond=0)

        return expected.strftime('%Y-%m-%dT%H:%M:%S')

    async def run_full_test(self):
        """
        Главный метод - запускает весь тест
        """
        print("=" * 80)
        print(f"WAVE DETECTION TEST - {self.test_id}")
        print("=" * 80)

        # 1. Calculate wave times
        wave_times = self._calculate_next_wave_times(2)
        print(f"\nNext 2 waves:")
        for i, t in enumerate(wave_times, 1):
            expected_ts = self._calculate_expected_timestamp(t)
            print(f"  Wave {i}: {t:%H:%M:%S}")
            print(f"    Expected timestamp by formula: {expected_ts}")

        total_duration = (wave_times[-1] - datetime.now()).total_seconds() / 60 + 5
        print(f"\nTotal test duration: ~{total_duration:.0f} minutes")

        # 2. Pre-test checks
        print("\n[1/6] Pre-test checks...")
        await self._pre_test_checks()

        # 3. Connect to database
        print("\n[2/6] Connecting to database...")
        db_config = self.config['database']
        self.monitor = WaveMonitor(db_config)
        await self.monitor.connect()

        # 4. Take initial snapshot
        print("\n[3/6] Taking initial snapshot...")
        initial_snapshot = await self.monitor.snapshot_database_state()
        self._save_snapshot(initial_snapshot, "initial")
        print(f"  Active positions: {len(initial_snapshot.get('active_positions', []))}")

        # 5. Start monitoring
        print(f"\n[4/6] Starting monitoring...")
        print(f"  Wave 1: {wave_times[0]:%H:%M:%S}")
        print(f"  Wave 2: {wave_times[1]:%H:%M:%S}")

        # Monitor waves
        await self._monitor_waves(wave_times)

        # 6. Take final snapshot
        print("\n[5/6] Taking final snapshot...")
        final_snapshot = await self.monitor.snapshot_database_state()
        self._save_snapshot(final_snapshot, "final")

        # 7. Generate reports
        print("\n[6/6] Generating analysis reports...")
        await self._generate_reports(initial_snapshot, final_snapshot)

        # Cleanup
        await self.monitor.close()

        print(f"\n{'=' * 80}")
        print(f"TEST COMPLETED")
        print(f"Results saved to: {self.output_dir}")
        print(f"{'=' * 80}\n")

    async def _pre_test_checks(self):
        """Pre-flight проверки"""
        log_file = self.config['monitoring']['log_file']

        # Проверяем что лог файл существует
        if not Path(log_file).exists():
            print(f"  ⚠️  Warning: Log file not found: {log_file}")
        else:
            print(f"  ✅ Log file found: {log_file}")

    async def _monitor_waves(self, wave_times: list):
        """
        Мониторит каждую волну
        """
        log_file = self.config['monitoring']['log_file']

        for i, wave_time in enumerate(wave_times, 1):
            print(f"\n--- Monitoring Wave {i} at {wave_time:%H:%M:%S} ---")

            # Ждем до 30 секунд перед wave check
            wait_until = wave_time - timedelta(seconds=30)
            now = datetime.now()

            if now < wait_until:
                wait_seconds = (wait_until - now).total_seconds()
                print(f"  Waiting {wait_seconds:.0f}s until wave window...")
                await asyncio.sleep(wait_seconds)

            # Запускаем параллельный мониторинг логов и БД
            print(f"  Starting monitoring (180 seconds)...")
            start_time = datetime.now()

            # Мониторим БД
            db_task = asyncio.create_task(
                self.monitor.monitor_wave_cycle(
                    wave_time,
                    wave_num=i,
                    duration_seconds=180
                )
            )

            # Мониторим логи
            log_task = asyncio.create_task(
                self.monitor.monitor_logs_realtime(
                    log_file,
                    duration_seconds=180
                )
            )

            # Ждем завершения
            wave_data, log_lines = await asyncio.gather(db_task, log_task)

            # Парсим логи
            wave_cycle = self.parser.extract_wave_cycle(log_lines)
            timing_metrics = self.parser.calculate_timing_metrics(wave_cycle)

            # Объединяем данные
            wave_data['log_analysis'] = wave_cycle
            wave_data['timing_metrics'] = timing_metrics

            # Обнаруживаем аномалии
            anomalies = await self.monitor.detect_anomalies(wave_data)
            wave_data['anomalies'] = anomalies

            self.data_collected.append(wave_data)

            # Быстрый анализ
            self._print_wave_summary(wave_data, i)

            # Сохраняем данные волны
            self._save_wave_data(wave_data, i)

    def _print_wave_summary(self, wave_data: Dict, wave_num: int):
        """Печатает краткую сводку по волне"""
        print(f"\n  Wave {wave_num} Summary:")

        positions = wave_data.get('positions_created', [])
        print(f"    Positions created: {len(positions)}")

        log_analysis = wave_data.get('log_analysis', {})
        signals_count = log_analysis.get('signals_count', 0)
        print(f"    Signals detected: {signals_count}")

        timing = wave_data.get('timing_metrics', {})
        detection_time = timing.get('check_to_detection_ms')
        if detection_time:
            print(f"    Detection time: {detection_time}ms")

        anomalies = wave_data.get('anomalies', [])
        if anomalies:
            print(f"    ⚠️  Anomalies: {len(anomalies)}")
            for anomaly in anomalies:
                print(f"      - {anomaly.get('type')}: {anomaly.get('description')}")

    def _save_snapshot(self, snapshot: dict, name: str):
        """Сохраняет snapshot в файл"""
        filepath = self.output_dir / f"snapshot_{name}.json"
        with open(filepath, 'w') as f:
            json.dump(snapshot, f, indent=2, default=str)
        print(f"  Saved: {filepath.name}")

    def _save_wave_data(self, wave_data: dict, wave_num: int):
        """Сохраняет данные волны"""
        filepath = self.output_dir / f"wave_{wave_num}_data.json"
        with open(filepath, 'w') as f:
            json.dump(wave_data, f, indent=2, default=str)
        print(f"  Saved: {filepath.name}")

    async def _generate_reports(self, initial_snapshot: dict, final_snapshot: dict):
        """Генерирует финальные отчеты"""

        # 1. Текстовый отчет от монитора
        report = self.monitor.generate_final_report(self.data_collected)

        report_file = self.output_dir / "final_report.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        print(f"  Saved: {report_file.name}")

        # 2. Сравнение snapshots
        comparison = self.monitor.compare_snapshots(initial_snapshot, final_snapshot)

        comparison_file = self.output_dir / "snapshots_comparison.json"
        with open(comparison_file, 'w') as f:
            json.dump(comparison, f, indent=2, default=str)
        print(f"  Saved: {comparison_file.name}")

        # 3. Сводка по всем волнам
        summary = {
            'test_id': self.test_id,
            'waves_count': len(self.data_collected),
            'total_positions': sum(len(w.get('positions_created', [])) for w in self.data_collected),
            'total_errors': sum(len(w.get('errors', [])) for w in self.data_collected),
            'total_anomalies': sum(len(w.get('anomalies', [])) for w in self.data_collected),
            'waves': []
        }

        for i, wave_data in enumerate(self.data_collected, 1):
            wave_summary = {
                'wave_num': i,
                'expected_time': wave_data.get('expected_time'),
                'positions_created': len(wave_data.get('positions_created', [])),
                'signals_detected': wave_data.get('log_analysis', {}).get('signals_count', 0),
                'timing_metrics': wave_data.get('timing_metrics', {}),
                'anomalies_count': len(wave_data.get('anomalies', []))
            }
            summary['waves'].append(wave_summary)

        summary_file = self.output_dir / "test_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"  Saved: {summary_file.name}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python run_wave_test.py <config_file>")
        sys.exit(1)

    config_path = sys.argv[1]

    if not Path(config_path).exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    orchestrator = WaveTestOrchestrator(config_path)

    try:
        await orchestrator.run_full_test()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
