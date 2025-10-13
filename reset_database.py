#!/usr/bin/env python3
"""
Database Reset Script
Очищает все таблицы для тестирования с чистого листа

Удаляет:
- Все позиции (monitoring.positions)
- Все ордера (monitoring.orders)
- Все сделки (monitoring.trades)
- Все события рисков (monitoring.risk_events, monitoring.risk_violations)
- Все метрики (monitoring.performance_metrics)
- Новые таблицы (monitoring.event_log, monitoring.sync_status - если существуют)

НЕ трогает:
- fas.scoring_history (сигналы приходят через websocket, таблица не используется)
"""

import asyncio
import asyncpg
from config.settings import Config
from datetime import datetime

async def check_tables_data(conn):
    """Проверяет сколько данных в каждой таблице"""

    tables_to_check = [
        ('monitoring', 'positions'),
        ('monitoring', 'orders'),
        ('monitoring', 'trades'),
        ('monitoring', 'risk_events'),
        ('monitoring', 'risk_violations'),
        ('monitoring', 'performance_metrics'),
        ('monitoring', 'event_log'),
        ('monitoring', 'sync_status'),
    ]

    print("\n" + "="*60)
    print("📊 ТЕКУЩЕЕ СОСТОЯНИЕ БАЗЫ ДАННЫХ")
    print("="*60 + "\n")

    total_records = 0
    table_counts = []

    for schema, table in tables_to_check:
        try:
            count = await conn.fetchval(
                f"SELECT COUNT(*) FROM {schema}.{table}"
            )
            if count > 0:
                print(f"  {schema}.{table:25} → {count:6} записей")
                table_counts.append((schema, table, count))
                total_records += count
        except Exception as e:
            # Таблица может не существовать (например новые таблицы из миграций)
            if "does not exist" not in str(e):
                print(f"  {schema}.{table:25} → ⚠️ Ошибка: {e}")

    print("\n" + "-"*60)
    print(f"  ВСЕГО ЗАПИСЕЙ: {total_records}")
    print("-"*60 + "\n")

    return table_counts, total_records


async def truncate_all_tables(conn):
    """Очищает все таблицы"""

    tables_to_truncate = [
        ('monitoring', 'positions'),
        ('monitoring', 'orders'),
        ('monitoring', 'trades'),
        ('monitoring', 'risk_events'),
        ('monitoring', 'risk_violations'),
        ('monitoring', 'performance_metrics'),
        ('monitoring', 'event_log'),
        ('monitoring', 'sync_status'),
    ]

    print("\n" + "="*60)
    print("🗑️  ОЧИСТКА ТАБЛИЦ")
    print("="*60 + "\n")

    truncated_count = 0

    for schema, table in tables_to_truncate:
        try:
            await conn.execute(
                f"TRUNCATE TABLE {schema}.{table} RESTART IDENTITY CASCADE"
            )
            print(f"  ✅ {schema}.{table:25} → очищена")
            truncated_count += 1
        except Exception as e:
            if "does not exist" not in str(e):
                print(f"  ⚠️  {schema}.{table:25} → Ошибка: {e}")
            # Если таблица не существует - просто пропускаем

    print("\n" + "-"*60)
    print(f"  Очищено таблиц: {truncated_count}")
    print("-"*60 + "\n")


async def verify_cleanup(conn):
    """Проверяет что все таблицы пустые"""

    tables_to_check = [
        ('monitoring', 'positions'),
        ('monitoring', 'orders'),
        ('monitoring', 'trades'),
        ('monitoring', 'risk_events'),
        ('monitoring', 'risk_violations'),
        ('monitoring', 'performance_metrics'),
        ('monitoring', 'event_log'),
        ('monitoring', 'sync_status'),
    ]

    print("\n" + "="*60)
    print("✅ ВЕРИФИКАЦИЯ")
    print("="*60 + "\n")

    all_clean = True

    for schema, table in tables_to_check:
        try:
            count = await conn.fetchval(
                f"SELECT COUNT(*) FROM {schema}.{table}"
            )
            if count == 0:
                print(f"  ✅ {schema}.{table:25} → пустая")
            else:
                print(f"  ❌ {schema}.{table:25} → {count} записей (НЕ ОЧИЩЕНА!)")
                all_clean = False
        except Exception as e:
            if "does not exist" not in str(e):
                print(f"  ⚠️  {schema}.{table:25} → Ошибка: {e}")

    print("\n" + "-"*60)
    if all_clean:
        print("  ✅ ВСЕ ТАБЛИЦЫ УСПЕШНО ОЧИЩЕНЫ")
    else:
        print("  ❌ НЕКОТОРЫЕ ТАБЛИЦЫ НЕ ОЧИЩЕНЫ")
    print("-"*60 + "\n")

    return all_clean


async def main():
    """Основная функция"""

    config = Config()
    db_config = config.database

    print("\n" + "="*60)
    print("🔄 СБРОС БАЗЫ ДАННЫХ")
    print("="*60)
    print(f"\nБаза данных: {db_config.database}")
    print(f"Хост: {db_config.host}")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Подключение к БД
    conn = await asyncpg.connect(
        host=db_config.host,
        port=db_config.port,
        user=db_config.user,
        password=db_config.password,
        database=db_config.database
    )

    try:
        # 1. Показать текущее состояние
        table_counts, total_records = await check_tables_data(conn)

        if total_records == 0:
            print("ℹ️  База данных уже пустая. Нечего удалять.\n")
            return

        # 2. Запросить подтверждение
        print("⚠️  ВНИМАНИЕ! ЭТА ОПЕРАЦИЯ НЕОБРАТИМА!")
        print("   Все данные будут удалены безвозвратно.\n")

        confirmation = input("Вы уверены что хотите УДАЛИТЬ ВСЕ ДАННЫЕ? (yes/no): ").strip().lower()

        if confirmation != 'yes':
            print("\n❌ Операция отменена пользователем.\n")
            return

        # Второе подтверждение для безопасности
        confirmation2 = input(f"\nПодтвердите удаление {total_records} записей (введите 'DELETE'): ").strip()

        if confirmation2 != 'DELETE':
            print("\n❌ Операция отменена пользователем.\n")
            return

        # 3. Очистить все таблицы
        await truncate_all_tables(conn)

        # 4. Проверить результат
        all_clean = await verify_cleanup(conn)

        # 5. Итог
        print("\n" + "="*60)
        if all_clean:
            print("🎉 БАЗА ДАННЫХ УСПЕШНО ОЧИЩЕНА")
            print("   Можно начинать тестирование с чистого листа!")
        else:
            print("⚠️  ОЧИСТКА ЗАВЕРШЕНА С ПРЕДУПРЕЖДЕНИЯМИ")
            print("   Проверьте логи выше")
        print("="*60 + "\n")

    finally:
        await conn.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Операция прервана пользователем (Ctrl+C)\n")
    except Exception as e:
        print(f"\n\n❌ ОШИБКА: {e}\n")
        raise
