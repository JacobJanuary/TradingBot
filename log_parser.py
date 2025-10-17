"""
Парсинг и анализ логов в реальном времени
"""

import re
from datetime import datetime
from typing import Dict, List, Optional
import json


class LogParser:
    """
    Извлекает структурированные данные из логов
    """

    # Regex паттерны для критичных событий
    PATTERNS = {
        'wave_check_start': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Wave check started.*expected_timestamp[:\s=]+(\S+)',
        'wave_found': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Wave found.*signals_count[:\s=]+(\d+)',
        'signal_validation': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Signal validation.*symbol[:\s=]+(\S+).*passed[:\s=]+(True|False).*reason[:\s=]+(.*)',
        'position_opening': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Opening position.*symbol[:\s=]+(\S+).*side[:\s=]+(\S+)',
        'position_created': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Position created.*id[:\s=]+(\d+).*symbol[:\s=]+(\S+)',
        'sl_set': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Stop[-\s]?loss set.*symbol[:\s=]+(\S+).*price[:\s=]+([\d.]+)',
        'error': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*ERROR',
        'rollback': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Rolling back position.*symbol[:\s=]+(\S+)',
        'wave_timestamp': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*expected_timestamp[:\s=]+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
    }

    def parse_line(self, line: str) -> Optional[Dict]:
        """
        Парсит строку лога и возвращает структурированное событие
        """
        for event_type, pattern in self.PATTERNS.items():
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                groups = match.groups()
                timestamp_str = groups[0]

                # Парсим timestamp
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                except ValueError:
                    timestamp = None

                event = {
                    'type': event_type,
                    'timestamp': timestamp,
                    'timestamp_str': timestamp_str,
                    'raw_line': line.strip()
                }

                # Добавляем специфичные для типа поля
                if event_type == 'wave_check_start' and len(groups) > 1:
                    event['expected_timestamp'] = groups[1]
                elif event_type == 'wave_found' and len(groups) > 1:
                    event['signals_count'] = int(groups[1])
                elif event_type == 'signal_validation' and len(groups) > 3:
                    event['symbol'] = groups[1]
                    event['passed'] = groups[2] == 'True'
                    event['reason'] = groups[3].strip()
                elif event_type == 'position_opening' and len(groups) > 2:
                    event['symbol'] = groups[1]
                    event['side'] = groups[2]
                elif event_type == 'position_created' and len(groups) > 2:
                    event['position_id'] = int(groups[1])
                    event['symbol'] = groups[2]
                elif event_type == 'sl_set' and len(groups) > 2:
                    event['symbol'] = groups[1]
                    event['price'] = float(groups[2])
                elif event_type == 'rollback' and len(groups) > 1:
                    event['symbol'] = groups[1]
                elif event_type == 'wave_timestamp' and len(groups) > 1:
                    event['expected_timestamp'] = groups[1]

                return event

        return None

    def extract_wave_cycle(self, lines: List[str]) -> Dict:
        """
        Извлекает полный цикл волны из логов

        Возвращает:
        {
            'start_time': ...,
            'expected_timestamp': ...,
            'wave_found_time': ...,
            'signals_count': ...,
            'validated_signals': [...],
            'positions_opened': [...],
            'errors': [...],
            'duration_ms': ...
        }
        """
        cycle = {
            'start_time': None,
            'expected_timestamp': None,
            'wave_found_time': None,
            'signals_count': 0,
            'validated_signals': [],
            'positions_opened': [],
            'sl_set': [],
            'errors': [],
            'rollbacks': [],
            'duration_ms': None,
            'all_events': []
        }

        for line in lines:
            event = self.parse_line(line)
            if not event:
                continue

            cycle['all_events'].append(event)

            if event['type'] == 'wave_check_start':
                cycle['start_time'] = event['timestamp']
                if 'expected_timestamp' in event:
                    cycle['expected_timestamp'] = event['expected_timestamp']

            elif event['type'] == 'wave_timestamp':
                if 'expected_timestamp' in event:
                    cycle['expected_timestamp'] = event['expected_timestamp']

            elif event['type'] == 'wave_found':
                cycle['wave_found_time'] = event['timestamp']
                cycle['signals_count'] = event.get('signals_count', 0)

            elif event['type'] == 'signal_validation':
                cycle['validated_signals'].append({
                    'symbol': event.get('symbol'),
                    'passed': event.get('passed'),
                    'reason': event.get('reason'),
                    'timestamp': event['timestamp']
                })

            elif event['type'] == 'position_opening':
                cycle['positions_opened'].append({
                    'symbol': event.get('symbol'),
                    'side': event.get('side'),
                    'timestamp': event['timestamp']
                })

            elif event['type'] == 'position_created':
                # Обновляем информацию о позиции если она уже есть
                for pos in cycle['positions_opened']:
                    if pos['symbol'] == event.get('symbol'):
                        pos['position_id'] = event.get('position_id')
                        pos['created_timestamp'] = event['timestamp']
                        break

            elif event['type'] == 'sl_set':
                cycle['sl_set'].append({
                    'symbol': event.get('symbol'),
                    'price': event.get('price'),
                    'timestamp': event['timestamp']
                })

            elif event['type'] == 'error':
                cycle['errors'].append({
                    'raw_line': event['raw_line'],
                    'timestamp': event['timestamp']
                })

            elif event['type'] == 'rollback':
                cycle['rollbacks'].append({
                    'symbol': event.get('symbol'),
                    'timestamp': event['timestamp']
                })

        # Вычисляем duration
        if cycle['start_time'] and cycle['wave_found_time']:
            delta = cycle['wave_found_time'] - cycle['start_time']
            cycle['duration_ms'] = int(delta.total_seconds() * 1000)

        return cycle

    def calculate_timing_metrics(self, wave_cycle: Dict) -> Dict:
        """
        Вычисляет timing метрики для цикла волны
        """
        metrics = {
            'check_to_detection_ms': None,
            'detection_to_first_position_ms': None,
            'first_to_last_position_ms': None,
            'total_processing_ms': None,
            'avg_position_creation_ms': None
        }

        start = wave_cycle.get('start_time')
        found = wave_cycle.get('wave_found_time')
        positions = wave_cycle.get('positions_opened', [])

        if start and found:
            metrics['check_to_detection_ms'] = int((found - start).total_seconds() * 1000)

        if found and positions:
            first_pos_time = positions[0]['timestamp']
            if first_pos_time:
                metrics['detection_to_first_position_ms'] = int((first_pos_time - found).total_seconds() * 1000)

            if len(positions) > 1:
                last_pos_time = positions[-1]['timestamp']
                if last_pos_time:
                    metrics['first_to_last_position_ms'] = int((last_pos_time - first_pos_time).total_seconds() * 1000)

        if start and positions:
            last_pos_time = positions[-1]['timestamp'] if positions else None
            if last_pos_time:
                metrics['total_processing_ms'] = int((last_pos_time - start).total_seconds() * 1000)

        # Средняя время создания позиций
        if positions:
            creation_times = []
            for i in range(len(positions) - 1):
                if positions[i]['timestamp'] and positions[i+1]['timestamp']:
                    delta = (positions[i+1]['timestamp'] - positions[i]['timestamp']).total_seconds() * 1000
                    creation_times.append(delta)

            if creation_times:
                metrics['avg_position_creation_ms'] = int(sum(creation_times) / len(creation_times))

        return metrics
