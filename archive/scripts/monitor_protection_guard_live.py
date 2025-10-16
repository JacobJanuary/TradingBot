#!/usr/bin/env python3
"""
Live monitoring of Protection Guard activity during bot run
Monitors SL checks, creations, and validates the new fixes work correctly
"""

import asyncio
import sys
from datetime import datetime, timezone
from collections import defaultdict
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from config.settings import config

class ProtectionGuardMonitor:
    def __init__(self):
        db = config.database
        # URL-encode password to handle special characters
        password_encoded = quote_plus(db.password)
        database_url = f"postgresql://{db.user}:{password_encoded}@{db.host}:{db.port}/{db.database}"
        self.engine = create_engine(database_url)
        self.start_time = datetime.now(timezone.utc)
        self.last_check_time = self.start_time

    def get_recent_events(self, since_seconds=30):
        """Get Protection Guard events from last N seconds"""
        query = text("""
            SELECT
                event_type,
                event_data,
                created_at
            FROM event_logs
            WHERE created_at >= NOW() - INTERVAL ':seconds seconds'
              AND (
                  event_type LIKE '%stop_loss%'
                  OR event_type LIKE '%protection%'
                  OR event_type LIKE '%position_check%'
              )
            ORDER BY created_at DESC
            LIMIT 100
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query, {"seconds": since_seconds})
            return [dict(row._mapping) for row in result]

    def get_positions_without_sl(self):
        """Get open positions without SL right now"""
        query = text("""
            SELECT
                symbol,
                exchange,
                side,
                entry_price,
                quantity,
                opened_at
            FROM positions
            WHERE status = 'open'
              AND closed_at IS NULL
            ORDER BY opened_at DESC
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query)
            return [dict(row._mapping) for row in result]

    async def check_positions_have_sl(self):
        """Check which positions have SL on exchange"""
        from core.exchange_manager import ExchangeManager

        exchange_manager = ExchangeManager()
        await exchange_manager.initialize()

        positions = self.get_positions_without_sl()
        positions_status = []

        for pos in positions:
            exchange = exchange_manager.get_exchange(pos['exchange'])
            if not exchange:
                continue

            try:
                # Check for position-attached SL (Bybit)
                if pos['exchange'] == 'bybit':
                    positions_data = await exchange.fetch_positions([pos['symbol']])
                    for p in positions_data:
                        if p['symbol'] == pos['symbol']:
                            sl_price = p.get('info', {}).get('stopLoss', '0')
                            has_sl = float(sl_price) > 0
                            positions_status.append({
                                'symbol': pos['symbol'],
                                'exchange': pos['exchange'],
                                'side': pos['side'],
                                'has_sl': has_sl,
                                'sl_price': sl_price if has_sl else None,
                                'entry_price': pos['entry_price']
                            })
                            break

                # Check for stop orders
                orders = await exchange.fetch_open_orders(pos['symbol'])
                stop_orders = [o for o in orders if o.get('type') in ['stop', 'stop_market', 'stop_limit']]

                if stop_orders and pos['exchange'] != 'bybit':
                    positions_status.append({
                        'symbol': pos['symbol'],
                        'exchange': pos['exchange'],
                        'side': pos['side'],
                        'has_sl': True,
                        'sl_price': stop_orders[0].get('stopPrice'),
                        'entry_price': pos['entry_price']
                    })
                elif pos['exchange'] != 'bybit':
                    positions_status.append({
                        'symbol': pos['symbol'],
                        'exchange': pos['exchange'],
                        'side': pos['side'],
                        'has_sl': False,
                        'sl_price': None,
                        'entry_price': pos['entry_price']
                    })

            except Exception as e:
                print(f"❌ Error checking {pos['symbol']}: {e}")

        await exchange_manager.close()
        return positions_status

    def analyze_events(self, events):
        """Analyze Protection Guard events"""
        stats = {
            'sl_checks': 0,
            'sl_created': 0,
            'sl_errors': 0,
            'sl_exists': 0,
            'positions_checked': 0,
            'side_validation_triggered': 0,
            'price_validation_triggered': 0,
        }

        recent_actions = []

        for event in events:
            event_type = event['event_type']
            event_data = event['event_data'] or {}
            timestamp = event['created_at']

            if 'position_check' in event_type:
                stats['positions_checked'] += 1

            if 'stop_loss' in event_type:
                stats['sl_checks'] += 1

                if 'created' in event_type or 'set' in event_type:
                    stats['sl_created'] += 1
                    recent_actions.append({
                        'time': timestamp,
                        'action': 'SL CREATED',
                        'symbol': event_data.get('symbol', 'unknown'),
                        'price': event_data.get('stop_price', 'N/A')
                    })

                if 'error' in event_type:
                    stats['sl_errors'] += 1
                    recent_actions.append({
                        'time': timestamp,
                        'action': 'SL ERROR',
                        'symbol': event_data.get('symbol', 'unknown'),
                        'error': event_data.get('error', 'unknown')
                    })

                if 'exists' in event_type or 'valid' in event_type:
                    stats['sl_exists'] += 1

                # Check for validation messages
                message = event_data.get('message', '').lower()
                if 'side' in message and ('wrong' in message or 'skip' in message):
                    stats['side_validation_triggered'] += 1
                    recent_actions.append({
                        'time': timestamp,
                        'action': '🔧 SIDE VALIDATION',
                        'symbol': event_data.get('symbol', 'unknown'),
                        'details': message
                    })

                if 'price' in message and ('old position' in message or 'too close' in message):
                    stats['price_validation_triggered'] += 1
                    recent_actions.append({
                        'time': timestamp,
                        'action': '🔧 PRICE VALIDATION',
                        'symbol': event_data.get('symbol', 'unknown'),
                        'details': message
                    })

        return stats, recent_actions

async def main():
    monitor = ProtectionGuardMonitor()

    print("=" * 80)
    print("🔍 LIVE PROTECTION GUARD MONITORING")
    print(f"Начало: {monitor.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Длительность: 10 минут")
    print("=" * 80)
    print()

    iteration = 0

    # Run for 10 minutes (20 iterations * 30 seconds)
    for i in range(20):
        iteration += 1
        elapsed = (datetime.now(timezone.utc) - monitor.start_time).total_seconds()

        print(f"\n{'=' * 80}")
        print(f"⏱️  ПРОВЕРКА #{iteration} | Прошло: {int(elapsed)}с / 600с")
        print(f"{'=' * 80}")

        # Get recent events
        events = monitor.get_recent_events(since_seconds=35)
        stats, actions = monitor.analyze_events(events)

        # Print statistics
        print(f"\n📊 Статистика за последние 30 секунд:")
        print(f"   Позиций проверено:        {stats['positions_checked']}")
        print(f"   SL проверок:              {stats['sl_checks']}")
        print(f"   SL создано:               {stats['sl_created']}")
        print(f"   SL уже существует:        {stats['sl_exists']}")
        print(f"   Ошибок SL:                {stats['sl_errors']}")
        print(f"   🔧 Side validation:       {stats['side_validation_triggered']}")
        print(f"   🔧 Price validation:      {stats['price_validation_triggered']}")

        # Print recent actions
        if actions:
            print(f"\n🎯 Последние действия:")
            for action in actions[-5:]:  # Last 5 actions
                time_str = action['time'].strftime('%H:%M:%S')
                print(f"   [{time_str}] {action['action']}: {action['symbol']}")
                if 'price' in action:
                    print(f"                Price: {action['price']}")
                if 'error' in action:
                    print(f"                Error: {action['error']}")
                if 'details' in action:
                    print(f"                Details: {action['details'][:60]}")

        # Check positions status every 2 minutes
        if iteration % 4 == 0:
            print(f"\n🔎 Проверка позиций на биржах...")
            try:
                positions_status = await monitor.check_positions_have_sl()

                with_sl = [p for p in positions_status if p['has_sl']]
                without_sl = [p for p in positions_status if not p['has_sl']]

                print(f"\n📈 Статус позиций:")
                print(f"   Всего открытых:    {len(positions_status)}")
                print(f"   С SL:              {len(with_sl)} ✅")
                print(f"   БЕЗ SL:            {len(without_sl)} {'⚠️' if without_sl else '✅'}")

                if without_sl:
                    print(f"\n   ⚠️  Позиции БЕЗ SL:")
                    for p in without_sl:
                        print(f"      - {p['symbol']} ({p['exchange']}) {p['side'].upper()}")
                        print(f"        Entry: {p['entry_price']}")
            except Exception as e:
                print(f"   ❌ Ошибка при проверке позиций: {e}")

        # Wait 30 seconds before next check
        if i < 19:  # Don't wait after last iteration
            print(f"\n⏳ Ожидание 30 секунд до следующей проверки...")
            await asyncio.sleep(30)

    # Final summary
    print(f"\n{'=' * 80}")
    print("✅ МОНИТОРИНГ ЗАВЕРШЕН")
    print(f"{'=' * 80}")

    total_events = monitor.get_recent_events(since_seconds=600)
    total_stats, total_actions = monitor.analyze_events(total_events)

    print(f"\n📊 ИТОГОВАЯ СТАТИСТИКА (10 минут):")
    print(f"   Позиций проверено:        {total_stats['positions_checked']}")
    print(f"   SL проверок:              {total_stats['sl_checks']}")
    print(f"   SL создано:               {total_stats['sl_created']}")
    print(f"   SL уже существует:        {total_stats['sl_exists']}")
    print(f"   Ошибок SL:                {total_stats['sl_errors']}")
    print(f"   🔧 Side validation:       {total_stats['side_validation_triggered']}")
    print(f"   🔧 Price validation:      {total_stats['price_validation_triggered']}")

    # Final positions check
    print(f"\n🔎 Финальная проверка позиций на биржах...")
    try:
        positions_status = await monitor.check_positions_have_sl()

        with_sl = [p for p in positions_status if p['has_sl']]
        without_sl = [p for p in positions_status if not p['has_sl']]

        print(f"\n📈 ФИНАЛЬНЫЙ СТАТУС ПОЗИЦИЙ:")
        print(f"   Всего открытых:    {len(positions_status)}")
        print(f"   С SL:              {len(with_sl)} ✅")
        print(f"   БЕЗ SL:            {len(without_sl)} {'⚠️' if without_sl else '✅'}")

        if without_sl:
            print(f"\n   ⚠️  Позиции БЕЗ SL (требуют внимания):")
            for p in without_sl:
                print(f"      - {p['symbol']} ({p['exchange']}) {p['side'].upper()}")
                print(f"        Entry: {p['entry_price']}")
        else:
            print(f"\n   ✅ ВСЕ ПОЗИЦИИ ЗАЩИЩЕНЫ STOP LOSS!")
    except Exception as e:
        print(f"   ❌ Ошибка при проверке позиций: {e}")

    print(f"\n{'=' * 80}")
    print(f"Завершено: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'=' * 80}\n")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Мониторинг прерван пользователем")
        sys.exit(0)
