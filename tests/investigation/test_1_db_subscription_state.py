#!/usr/bin/env python3
"""
ТЕСТ #1: Анализ состояния подписок - БД vs Реальность
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

from database.repository import Repository
from config.settings import Settings

settings = Settings()
db_config = {
    'host': settings.db_host,
    'port': settings.db_port,
    'database': settings.db_name,
    'user': settings.db_user,
    'password': settings.db_password,
    'min_size': 2,
    'max_size': 10,
}


async def analyze_db_state():
    """Analyze database state"""

    print("="*80)
    print("ТЕСТ #1: АНАЛИЗ СОСТОЯНИЯ ПОДПИСОК В БД")
    print("="*80)
    print(f"Дата: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"БД: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    print("="*80 + "\n")

    repo = Repository(db_config)
    try:
        await repo.initialize()
        print("✅ Подключение к PostgreSQL успешно\n")
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        import traceback
        traceback.print_exc()
        return

    try:
        async with repo.pool.acquire() as conn:
            # 1. Total open positions
            total_open = await conn.fetchval(
                "SELECT COUNT(*) FROM positions WHERE status = 'open'"
            )
            print(f"📊 Всего открытых позиций: {total_open}\n")

            if total_open == 0:
                print("⚠️  Нет открытых позиций для анализа")
                return

            # 2. Positions with recent updates (last 5 min)
            five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
            recent_updates = await conn.fetch("""
                SELECT symbol, current_price, updated_at,
                       EXTRACT(EPOCH FROM (NOW() - updated_at))/60 as minutes_since_update
                FROM positions
                WHERE status = 'open'
                AND updated_at > $1
                ORDER BY updated_at DESC
            """, five_min_ago)

            print(f"✅ Позиции с обновлениями за последние 5 минут: {len(recent_updates)}")
            if recent_updates and len(recent_updates) <= 10:
                print("   Список:")
                for pos in recent_updates:
                    print(f"   - {pos['symbol']}: ${pos['current_price']:.6f} "
                          f"({pos['minutes_since_update']:.1f} мин назад)")
            elif recent_updates:
                print(f"   Примеры (первые 5 из {len(recent_updates)}):")
                for pos in recent_updates[:5]:
                    print(f"   - {pos['symbol']}: ${pos['current_price']:.6f} "
                          f"({pos['minutes_since_update']:.1f} мин назад)")
            print()

            # 3. Stale positions
            stale = await conn.fetch("""
                SELECT symbol, current_price, updated_at, opened_at,
                       EXTRACT(EPOCH FROM (NOW() - updated_at))/60 as update_age_min,
                       EXTRACT(EPOCH FROM (NOW() - opened_at))/60 as position_age_min
                FROM positions
                WHERE status = 'open'
                AND (updated_at < $1 OR updated_at IS NULL OR current_price IS NULL OR current_price = 0)
                ORDER BY updated_at ASC NULLS FIRST
            """, five_min_ago)

            print(f"⚠️  Позиции БЕЗ обновлений >5 мин: {len(stale)}")
            if stale:
                print("\n   ДЕТАЛИ:")
                print("   " + "-"*78)
                print(f"   {'Символ':<12} {'Цена':<12} {'Откр.':<8} {'Послед.обн.':<12} {'Возраст'}")
                print("   " + "-"*78)

                for pos in stale[:20]:  # Limit to first 20
                    age = f"{pos['position_age_min']/60:.1f}h" if pos['position_age_min'] > 60 else f"{pos['position_age_min']:.0f}m"
                    
                    if pos['updated_at']:
                        upd = f"{pos['update_age_min']:.0f}m ago"
                    else:
                        upd = "НИКОГДА"
                    
                    price = f"${pos['current_price']:.6f}" if pos['current_price'] else "NULL"
                    
                    opened = pos['opened_at'].strftime('%H:%M') if pos['opened_at'] else "N/A"
                    
                    print(f"   {pos['symbol']:<12} {price:<12} {opened:<8} {upd:<12} {age}")
                
                if len(stale) > 20:
                    print(f"   ... и еще {len(stale) - 20} позиций")
            print()

            # 4. Summary
            print("="*80)
            print("ИТОГО:")
            print("="*80)
            
            healthy_pct = (len(recent_updates) / total_open * 100) if total_open else 0
            dead_pct = (len(stale) / total_open * 100) if total_open else 0
            
            print(f"   Всего позиций: {total_open}")
            print(f"   ✅ Здоровые (обновления <5 мин): {len(recent_updates)} ({healthy_pct:.1f}%)")
            print(f"   ❌ Мертвые (нет обновлений >5 мин): {len(stale)} ({dead_pct:.1f}%)")
            
            if dead_pct > 50:
                print(f"\n   🔴 КРИТИЧНО: {dead_pct:.1f}% позиций мертвы!")
            elif dead_pct > 10:
                print(f"\n   ⚠️  ПРОБЛЕМА: {dead_pct:.1f}% позиций без обновлений")
            elif dead_pct > 0:
                print(f"\n   ⚠️  {len(stale)} позиций требуют внимания")
            else:
                print(f"\n   ✅ Все позиции получают обновления")
            
            print("="*80)

    except Exception as e:
        print(f"\n❌ Ошибка при анализе: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await repo.pool.close()
        print("\n✅ Соединение закрыто")


if __name__ == "__main__":
    asyncio.run(analyze_db_state())
