"""
Real-time мониторинг Wave Detection и Position Opening
"""

import asyncio
import asyncpg
from datetime import datetime, timedelta
import json
from collections import defaultdict
from typing import Dict, List, Optional
import logging

from log_parser import LogParser
import db_queries


class WaveMonitor:
    """
    Мониторит:
    1. Timing wave detection
    2. Signal processing
    3. Position creation
    4. Database changes
    5. Errors and anomalies
    """

    def __init__(self, db_config: Dict):
        self.db_config = db_config
        self.conn = None
        self.snapshots = []
        self.events_log = []
        self.wave_detections = []
        self.position_creations = []
        self.errors = []
        self.parser = LogParser()

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    async def connect(self):
        """Подключение к БД"""
        self.conn = await asyncpg.connect(**self.db_config)
        self.logger.info("Connected to database")

    async def close(self):
        """Закрытие подключения"""
        if self.conn:
            await self.conn.close()
            self.logger.info("Database connection closed")

    # === CORE MONITORING METHODS ===

    async def monitor_wave_cycle(self, expected_time: datetime, wave_num: int, duration_seconds: int = 180):
        """
        Мониторит один цикл wave detection

        Отслеживает:
        - Когда началась проверка
        - Какой timestamp ожидается
        - Когда волна обнаружена
        - Сколько сигналов получено
        - Какие сигналы прошли валидацию
        - Какие позиции были открыты
        - Timing каждого шага
        """
        self.logger.info(f"Starting wave cycle monitoring #{wave_num} at {expected_time}")

        start_monitoring = datetime.now()

        # Snapshot до волны
        snapshot_before = await self.snapshot_database_state()

        wave_data = {
            'wave_num': wave_num,
            'expected_time': expected_time.isoformat(),
            'start_monitoring': start_monitoring.isoformat(),
            'snapshot_before': snapshot_before,
            'db_events': [],
            'positions_created': [],
            'errors': []
        }

        # Мониторим в течение duration_seconds
        end_time = start_monitoring + timedelta(seconds=duration_seconds)

        while datetime.now() < end_time:
            # Проверяем новые события в БД
            events = await self.get_new_events(start_monitoring)
            wave_data['db_events'].extend(events)

            # Проверяем новые позиции
            positions = await self.get_new_positions(start_monitoring)
            wave_data['positions_created'].extend(positions)

            await asyncio.sleep(5)  # Polling каждые 5 секунд

        # Snapshot после волны
        snapshot_after = await self.snapshot_database_state()
        wave_data['snapshot_after'] = snapshot_after
        wave_data['end_monitoring'] = datetime.now().isoformat()

        self.logger.info(f"Wave cycle #{wave_num} monitoring completed")
        return wave_data

    async def snapshot_database_state(self) -> Dict:
        """
        Создает snapshot текущего состояния БД

        Собирает:
        - Все позиции (активные, pending, closed)
        - Последние 100 событий
        - Trailing stop состояния
        - Статистику (открыто за последний час, PnL и т.д.)
        """
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'all_positions': [],
            'active_positions': [],
            'recent_events': [],
            'trailing_states': [],
            'statistics': {}
        }

        try:
            # Все позиции
            all_positions = await self.conn.fetch(db_queries.GET_ALL_POSITIONS)
            snapshot['all_positions'] = [dict(row) for row in all_positions]

            # Активные позиции
            active_positions = await self.conn.fetch(db_queries.GET_ACTIVE_POSITIONS)
            snapshot['active_positions'] = [dict(row) for row in active_positions]

            # Последние события
            recent_events = await self.conn.fetch(db_queries.GET_RECENT_EVENTS, 100)
            snapshot['recent_events'] = [dict(row) for row in recent_events]

            # Trailing stop состояния для активных позиций
            if active_positions:
                position_ids = [pos['id'] for pos in active_positions]
                trailing_states = await self.conn.fetch(db_queries.GET_TRAILING_STATES, position_ids)
                snapshot['trailing_states'] = [dict(row) for row in trailing_states]

            # Статистика за последний час
            one_hour_ago = datetime.now() - timedelta(hours=1)
            stats = await self.conn.fetchrow(db_queries.GET_PERIOD_STATISTICS, one_hour_ago)
            snapshot['statistics'] = dict(stats) if stats else {}

        except Exception as e:
            self.logger.error(f"Error creating snapshot: {e}")
            snapshot['error'] = str(e)

        return snapshot

    async def get_new_events(self, since: datetime) -> List[Dict]:
        """Получить новые события с момента since"""
        try:
            events = await self.conn.fetch(
                db_queries.GET_EVENTS_BY_TIMERANGE,
                since,
                datetime.now()
            )
            return [dict(row) for row in events]
        except Exception as e:
            self.logger.error(f"Error fetching new events: {e}")
            return []

    async def get_new_positions(self, since: datetime) -> List[Dict]:
        """Получить новые позиции с момента since"""
        try:
            positions = await self.conn.fetch(
                db_queries.GET_POSITIONS_BY_TIMERANGE,
                since,
                datetime.now()
            )
            return [dict(row) for row in positions]
        except Exception as e:
            self.logger.error(f"Error fetching new positions: {e}")
            return []

    async def monitor_logs_realtime(self, log_file: str, duration_seconds: int = 180) -> List[str]:
        """
        Tail логов в реальном времени

        Ищет паттерны:
        - "Wave detection started"
        - "Expected timestamp: ..."
        - "Wave found with N signals"
        - "Signal validation"
        - "Opening position"
        - "Position created"
        - ERROR, WARNING
        """
        lines = []
        try:
            # Используем tail для чтения новых строк
            process = await asyncio.create_subprocess_exec(
                'tail', '-f', log_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            start_time = datetime.now()
            end_time = start_time + timedelta(seconds=duration_seconds)

            while datetime.now() < end_time:
                try:
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=1.0
                    )
                    if line:
                        decoded_line = line.decode('utf-8', errors='ignore').strip()
                        lines.append(decoded_line)

                        # Парсим события в реальном времени
                        event = self.parser.parse_line(decoded_line)
                        if event:
                            self.logger.info(f"Detected event: {event['type']}")

                            if event['type'] == 'error':
                                self.errors.append(event)

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self.logger.error(f"Error reading log line: {e}")
                    break

            process.terminate()
            await process.wait()

        except Exception as e:
            self.logger.error(f"Error monitoring logs: {e}")

        return lines

    async def detect_anomalies(self, wave_data: Dict) -> List[Dict]:
        """
        Обнаруживает аномалии:
        - Задержки больше expected
        - Пропущенные волны
        - Failed position creations
        - Rollbacks
        - Timing issues
        """
        anomalies = []

        # Проверка timing
        snapshot_before = wave_data.get('snapshot_before', {})
        snapshot_after = wave_data.get('snapshot_after', {})

        positions_before = len(snapshot_before.get('all_positions', []))
        positions_after = len(snapshot_after.get('all_positions', []))
        new_positions_count = positions_after - positions_before

        # Проверка: были ли созданы позиции?
        if new_positions_count == 0:
            anomalies.append({
                'type': 'NO_POSITIONS_CREATED',
                'severity': 'HIGH',
                'description': 'No new positions created during wave cycle'
            })

        # Проверка на ошибки
        errors = wave_data.get('errors', [])
        if errors:
            anomalies.append({
                'type': 'ERRORS_DETECTED',
                'severity': 'MEDIUM',
                'count': len(errors),
                'description': f'{len(errors)} errors detected during wave cycle'
            })

        # Проверка на rollbacks
        db_events = wave_data.get('db_events', [])
        rollbacks = [e for e in db_events if e.get('event_type') == 'position_rollback']
        if rollbacks:
            anomalies.append({
                'type': 'ROLLBACKS_DETECTED',
                'severity': 'HIGH',
                'count': len(rollbacks),
                'description': f'{len(rollbacks)} position rollbacks detected'
            })

        return anomalies

    # === ANALYSIS METHODS ===

    def analyze_wave_timing(self, wave_data: Dict) -> Dict:
        """
        Анализирует timing волн:
        - От проверки до обнаружения
        - От обнаружения до обработки
        - От обработки до открытия позиций
        - Outliers и задержки
        """
        # Этот метод будет дополнен после получения реальных логов
        return {
            'status': 'pending_implementation',
            'note': 'Will be implemented based on actual log data'
        }

    def analyze_signal_processing(self, wave_data: Dict) -> Dict:
        """
        Анализирует обработку сигналов:
        - Сколько получено vs обработано
        - Причины отклонения (stoplist, score, spread)
        - Эффективность buffer logic
        - Достижение target (MAX_TRADES_PER_15MIN)
        """
        return {
            'status': 'pending_implementation',
            'note': 'Will be implemented based on actual log data'
        }

    def analyze_position_creation(self, wave_data: Dict) -> Dict:
        """
        Анализирует создание позиций:
        - Success rate
        - Rollback cases
        - Time to create (от сигнала до active)
        - Stop-loss placement success
        - Errors and retries
        """
        positions = wave_data.get('positions_created', [])

        analysis = {
            'total_positions': len(positions),
            'positions_by_status': defaultdict(int),
            'positions_with_sl': 0,
            'positions_without_sl': 0
        }

        for pos in positions:
            status = pos.get('status', 'unknown')
            analysis['positions_by_status'][status] += 1

            if pos.get('stop_loss_price'):
                analysis['positions_with_sl'] += 1
            else:
                analysis['positions_without_sl'] += 1

        return analysis

    def compare_snapshots(self, before: Dict, after: Dict) -> Dict:
        """
        Сравнивает snapshot'ы до и после волны

        Показывает:
        - Какие позиции появились
        - Изменения в существующих позициях
        - Новые события
        - Delta в статистике
        """
        comparison = {
            'new_positions': [],
            'updated_positions': [],
            'statistics_delta': {}
        }

        # Находим новые позиции
        before_ids = set(pos['id'] for pos in before.get('all_positions', []))
        after_positions = after.get('all_positions', [])

        for pos in after_positions:
            if pos['id'] not in before_ids:
                comparison['new_positions'].append(pos)

        # Сравниваем статистику
        stats_before = before.get('statistics', {})
        stats_after = after.get('statistics', {})

        for key in stats_after:
            if key in stats_before:
                delta = stats_after[key] - stats_before[key] if isinstance(stats_after[key], (int, float)) else None
                if delta is not None:
                    comparison['statistics_delta'][key] = delta

        return comparison

    # === REPORTING ===

    def generate_wave_report(self, wave_data: Dict, wave_num: int) -> str:
        """
        Генерирует отчет по одной волне
        """
        report = f"\n{'='*80}\n"
        report += f"WAVE #{wave_num} REPORT\n"
        report += f"{'='*80}\n\n"

        report += f"Expected time: {wave_data.get('expected_time')}\n"
        report += f"Monitoring started: {wave_data.get('start_monitoring')}\n"
        report += f"Monitoring ended: {wave_data.get('end_monitoring')}\n\n"

        # Позиции
        positions = wave_data.get('positions_created', [])
        report += f"Positions created: {len(positions)}\n"

        if positions:
            report += "\nPositions detail:\n"
            for pos in positions[:10]:  # Первые 10
                report += f"  - {pos.get('symbol')} {pos.get('side')} @ {pos.get('entry_price')} | SL: {pos.get('stop_loss_price')} | Status: {pos.get('status')}\n"

        # События
        events = wave_data.get('db_events', [])
        report += f"\nDatabase events: {len(events)}\n"

        # Ошибки
        errors = wave_data.get('errors', [])
        if errors:
            report += f"\n⚠️  Errors detected: {len(errors)}\n"

        # Сравнение snapshots
        if 'snapshot_before' in wave_data and 'snapshot_after' in wave_data:
            comparison = self.compare_snapshots(
                wave_data['snapshot_before'],
                wave_data['snapshot_after']
            )

            report += f"\nNew positions: {len(comparison['new_positions'])}\n"

            if comparison['statistics_delta']:
                report += "\nStatistics delta:\n"
                for key, value in comparison['statistics_delta'].items():
                    report += f"  {key}: {value:+.2f}\n"

        report += f"\n{'='*80}\n"
        return report

    def generate_final_report(self, all_waves_data: List[Dict]) -> str:
        """
        Итоговый отчет по всем волнам
        """
        report = f"\n{'='*80}\n"
        report += "FINAL WAVE DETECTION TEST REPORT\n"
        report += f"{'='*80}\n\n"

        report += f"Total waves monitored: {len(all_waves_data)}\n\n"

        total_positions = sum(len(w.get('positions_created', [])) for w in all_waves_data)
        total_errors = sum(len(w.get('errors', [])) for w in all_waves_data)

        report += f"Total positions created: {total_positions}\n"
        report += f"Total errors: {total_errors}\n\n"

        # Отчет по каждой волне
        for i, wave_data in enumerate(all_waves_data, 1):
            report += self.generate_wave_report(wave_data, i)

        report += "\n" + "="*80 + "\n"
        report += "END OF REPORT\n"
        report += "="*80 + "\n"

        return report
