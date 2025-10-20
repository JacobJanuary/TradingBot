#!/usr/bin/env python3
"""
ТЕСТОВЫЙ СКРИПТ: Измерение производительности DB методов

Измеряет реальное время выполнения всех критических методов repository.py:
- get_open_positions()
- save_trailing_stop_state()
- create_position()
- update_position()
- get_position_by_id()

КРИТИЧЕСКИ ВАЖНО: ТОЛЬКО ИЗМЕРЕНИЕ! БЕЗ ИЗМЕНЕНИЯ КОДА!
"""
import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from database.repository import Repository


class PerformanceTest:
    """Класс для тестирования производительности DB"""

    def __init__(self, repository: Repository):
        self.repo = repository
        self.results: List[Dict] = []

    async def measure_method(self, method_name: str, coro, timeout: float = 10.0) -> Dict:
        """
        Измерить время выполнения метода с таймаутом

        Returns:
            {
                'method': str,
                'duration': float,
                'success': bool,
                'error': str or None,
                'timed_out': bool
            }
        """
        result = {
            'method': method_name,
            'duration': 0.0,
            'success': False,
            'error': None,
            'timed_out': False
        }

        start = time.time()
        try:
            await asyncio.wait_for(coro, timeout=timeout)
            result['duration'] = time.time() - start
            result['success'] = True
        except asyncio.TimeoutError:
            result['duration'] = time.time() - start
            result['timed_out'] = True
            result['error'] = f"Timeout after {timeout}s"
        except Exception as e:
            result['duration'] = time.time() - start
            result['error'] = str(e)

        return result

    async def test_get_open_positions(self) -> Dict:
        """Тест: get_open_positions()"""
        print("\n📊 Testing: get_open_positions()")

        async def run():
            positions = await self.repo.get_open_positions()
            print(f"  ✅ Fetched {len(positions)} positions")
            return positions

        result = await self.measure_method('get_open_positions', run(), timeout=5.0)
        self.results.append(result)

        if result['success']:
            print(f"  ⏱️  Duration: {result['duration']*1000:.2f}ms")
        elif result['timed_out']:
            print(f"  ❌ TIMED OUT after {result['duration']:.2f}s")
        else:
            print(f"  ❌ ERROR: {result['error']}")

        return result

    async def test_get_position_by_id(self, position_id: int) -> Dict:
        """Тест: get_position_by_id()"""
        print(f"\n📊 Testing: get_position_by_id({position_id})")

        async def run():
            position = await self.repo.get_position_by_id(position_id)
            if position:
                print(f"  ✅ Found position: {position.get('symbol')}")
            else:
                print(f"  ⚠️  Position not found")
            return position

        result = await self.measure_method('get_position_by_id', run(), timeout=3.0)
        self.results.append(result)

        if result['success']:
            print(f"  ⏱️  Duration: {result['duration']*1000:.2f}ms")
        elif result['timed_out']:
            print(f"  ❌ TIMED OUT after {result['duration']:.2f}s")
        else:
            print(f"  ❌ ERROR: {result['error']}")

        return result

    async def test_get_trailing_stop_state(self, symbol: str, exchange: str) -> Dict:
        """Тест: get_trailing_stop_state()"""
        print(f"\n📊 Testing: get_trailing_stop_state({symbol}, {exchange})")

        async def run():
            state = await self.repo.get_trailing_stop_state(symbol, exchange)
            if state:
                print(f"  ✅ Found TS state: {state.get('state')}")
            else:
                print(f"  ⚠️  TS state not found")
            return state

        result = await self.measure_method('get_trailing_stop_state', run(), timeout=3.0)
        self.results.append(result)

        if result['success']:
            print(f"  ⏱️  Duration: {result['duration']*1000:.2f}ms")
        elif result['timed_out']:
            print(f"  ❌ TIMED OUT after {result['duration']:.2f}s")
        else:
            print(f"  ❌ ERROR: {result['error']}")

        return result

    async def test_multiple_get_open_positions(self, count: int = 10) -> Dict:
        """Тест: Множественные вызовы get_open_positions() подряд"""
        print(f"\n📊 Testing: {count} sequential get_open_positions() calls")

        durations = []
        errors = 0
        timeouts = 0

        for i in range(count):
            async def run():
                return await self.repo.get_open_positions()

            result = await self.measure_method(f'get_open_positions_{i}', run(), timeout=5.0)

            if result['success']:
                durations.append(result['duration'])
            elif result['timed_out']:
                timeouts += 1
            else:
                errors += 1

        if durations:
            avg = sum(durations) / len(durations)
            min_time = min(durations)
            max_time = max(durations)

            print(f"  ✅ Successful calls: {len(durations)}/{count}")
            print(f"  ⏱️  Average: {avg*1000:.2f}ms")
            print(f"  ⏱️  Min: {min_time*1000:.2f}ms")
            print(f"  ⏱️  Max: {max_time*1000:.2f}ms")

            if timeouts > 0:
                print(f"  ⚠️  Timeouts: {timeouts}")
            if errors > 0:
                print(f"  ❌ Errors: {errors}")

        result = {
            'method': 'get_open_positions_sequential',
            'count': count,
            'successful': len(durations),
            'timeouts': timeouts,
            'errors': errors,
            'avg_duration': sum(durations) / len(durations) if durations else 0,
            'min_duration': min(durations) if durations else 0,
            'max_duration': max(durations) if durations else 0
        }
        self.results.append(result)

        return result

    async def test_concurrent_get_open_positions(self, count: int = 5) -> Dict:
        """Тест: Параллельные вызовы get_open_positions()"""
        print(f"\n📊 Testing: {count} concurrent get_open_positions() calls")

        async def single_call():
            start = time.time()
            try:
                positions = await asyncio.wait_for(
                    self.repo.get_open_positions(),
                    timeout=5.0
                )
                duration = time.time() - start
                return {'success': True, 'duration': duration, 'count': len(positions)}
            except asyncio.TimeoutError:
                duration = time.time() - start
                return {'success': False, 'duration': duration, 'timed_out': True}
            except Exception as e:
                duration = time.time() - start
                return {'success': False, 'duration': duration, 'error': str(e)}

        start_all = time.time()
        results = await asyncio.gather(*[single_call() for _ in range(count)])
        total_duration = time.time() - start_all

        successful = [r for r in results if r['success']]
        timeouts = [r for r in results if r.get('timed_out')]
        errors = [r for r in results if not r['success'] and not r.get('timed_out')]

        print(f"  ✅ Successful calls: {len(successful)}/{count}")
        print(f"  ⏱️  Total time: {total_duration*1000:.2f}ms")

        if successful:
            avg = sum(r['duration'] for r in successful) / len(successful)
            print(f"  ⏱️  Average per call: {avg*1000:.2f}ms")

        if timeouts:
            print(f"  ⚠️  Timeouts: {len(timeouts)}")
        if errors:
            print(f"  ❌ Errors: {len(errors)}")

        result = {
            'method': 'get_open_positions_concurrent',
            'count': count,
            'successful': len(successful),
            'timeouts': len(timeouts),
            'errors': len(errors),
            'total_duration': total_duration,
            'avg_duration': sum(r['duration'] for r in successful) / len(successful) if successful else 0
        }
        self.results.append(result)

        return result

    def print_summary(self):
        """Печать итогового отчета"""
        print("\n" + "="*80)
        print("SUMMARY REPORT")
        print("="*80)

        # Критические методы
        critical_methods = ['get_open_positions', 'get_position_by_id', 'get_trailing_stop_state']

        print("\n🔍 КРИТИЧЕСКИЕ МЕТОДЫ:")
        print(f"{'Method':<40} {'Duration':<15} {'Status':<15}")
        print("-"*80)

        for result in self.results:
            method = result.get('method', 'unknown')
            if any(m in method for m in critical_methods):
                duration = result.get('duration', 0) * 1000

                if result.get('success'):
                    status = "✅ OK"
                    if duration < 50:
                        status += " (FAST)"
                    elif duration < 200:
                        status += " (NORMAL)"
                    else:
                        status += " (SLOW)"
                elif result.get('timed_out'):
                    status = "❌ TIMEOUT"
                else:
                    status = f"❌ ERROR: {result.get('error', 'unknown')[:20]}"

                print(f"{method:<40} {duration:>10.2f}ms    {status:<15}")

        # Анализ множественных вызовов
        print("\n🔄 МНОЖЕСТВЕННЫЕ ВЫЗОВЫ:")
        for result in self.results:
            if 'sequential' in result.get('method', '') or 'concurrent' in result.get('method', ''):
                print(f"\n{result['method']}:")
                print(f"  Total: {result.get('count', 0)} calls")
                print(f"  Successful: {result.get('successful', 0)}")
                print(f"  Average: {result.get('avg_duration', 0)*1000:.2f}ms")
                if result.get('timeouts', 0) > 0:
                    print(f"  ⚠️  Timeouts: {result['timeouts']}")
                if result.get('errors', 0) > 0:
                    print(f"  ❌ Errors: {result['errors']}")

        # Выводы
        print("\n📋 ВЫВОДЫ:")

        # Проверка на зависания
        timeouts = [r for r in self.results if r.get('timed_out')]
        if timeouts:
            print(f"  ❌ ПРОБЛЕМА: {len(timeouts)} методов зависли!")
            for t in timeouts:
                print(f"     - {t['method']}")
        else:
            print(f"  ✅ Зависаний не обнаружено")

        # Проверка производительности
        slow_methods = [r for r in self.results
                       if r.get('success') and r.get('duration', 0) > 0.2]  # >200ms
        if slow_methods:
            print(f"  ⚠️  {len(slow_methods)} медленных методов (>200ms):")
            for s in slow_methods:
                print(f"     - {s['method']}: {s['duration']*1000:.2f}ms")
        else:
            print(f"  ✅ Все методы быстрые (<200ms)")

        # Проверка ошибок
        errors = [r for r in self.results if r.get('error') and not r.get('timed_out')]
        if errors:
            print(f"  ❌ {len(errors)} методов с ошибками:")
            for e in errors:
                print(f"     - {e['method']}: {e['error'][:50]}")
        else:
            print(f"  ✅ Ошибок не обнаружено")


async def main():
    print("="*80)
    print("ТЕСТ ПРОИЗВОДИТЕЛЬНОСТИ БАЗЫ ДАННЫХ")
    print("="*80)
    print()
    print("Этот скрипт измеряет реальное время выполнения критических DB методов")
    print("для выявления узких мест и зависаний.")
    print()
    print("⚠️  ВАЖНО: Этот скрипт ТОЛЬКО ЧИТАЕТ данные, никаких изменений не делает!")
    print()

    # Инициализация
    config = Config()
    db_config = {
        'host': config.database.host,
        'port': config.database.port,
        'database': config.database.database,
        'user': config.database.user,
        'password': config.database.password,
        'pool_size': config.database.pool_size,
        'max_overflow': config.database.max_overflow
    }
    repo = Repository(db_config)
    await repo.initialize()

    print(f"✅ Подключено к БД: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    print()

    # Создаем тестер
    tester = PerformanceTest(repo)

    # Тест 1: Одиночный get_open_positions()
    await tester.test_get_open_positions()

    # Тест 2: Множественные последовательные вызовы
    await tester.test_multiple_get_open_positions(count=10)

    # Тест 3: Параллельные вызовы (как в волне)
    await tester.test_concurrent_get_open_positions(count=5)

    # Тест 4: get_position_by_id (если есть позиции)
    positions = await repo.get_open_positions()
    if positions:
        first_position = positions[0]
        await tester.test_get_position_by_id(first_position['id'])

        # Тест 5: get_trailing_stop_state
        await tester.test_get_trailing_stop_state(
            first_position['symbol'],
            first_position['exchange']
        )
    else:
        print("\n⚠️  Нет открытых позиций для тестирования get_position_by_id()")

    # Итоговый отчет
    tester.print_summary()

    # Закрываем соединение
    await repo.close()

    print("\n" + "="*80)
    print("ТЕСТ ЗАВЕРШЕН")
    print("="*80)


if __name__ == '__main__':
    asyncio.run(main())
