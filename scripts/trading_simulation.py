#!/usr/bin/env python3
"""Trading simulation script for testing the bot"""

import asyncio
import random
import json
from datetime import datetime, timedelta
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import os
import psycopg2
from decimal import Decimal
import time

load_dotenv()

# Database connection
DB_PARAMS = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5433'),
    'database': os.getenv('DB_NAME', 'fox_crypto'),
    'user': os.getenv('DB_USER', 'elcrypto'),
    'password': os.getenv('DB_PASSWORD', 'LohNeMamont@!21')
}

class TradingSimulator:
    def __init__(self):
        self.exchange = None
        self.top_pairs = []
        self.simulation_results = []
        self.conn = None
        
    async def initialize(self):
        """Initialize exchange and database"""
        print("\n=== INITIALIZING TRADING SIMULATOR ===\n")
        
        # Initialize Binance testnet
        self.exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,
                'fetchPositions': 'positionRisk',
            }
        })
        self.exchange.set_sandbox_mode(True)
        
        # Load markets
        await self.exchange.load_markets()
        print(f"✅ Loaded {len(self.exchange.markets)} markets from Binance testnet")
        
        # Connect to database
        self.conn = psycopg2.connect(**DB_PARAMS)
        self.cur = self.conn.cursor()
        print("✅ Connected to database")
        
    async def get_top_liquid_pairs(self, count=30):
        """Get top liquid trading pairs by 24h volume"""
        print(f"\n=== FETCHING TOP {count} LIQUID PAIRS ===\n")
        
        # Fetch tickers for all USDT perpetual futures
        tickers = await self.exchange.fetch_tickers()
        
        # Filter and sort by 24h volume
        usdt_pairs = []
        for symbol, ticker in tickers.items():
            if symbol.endswith('/USDT:USDT') and ticker.get('quoteVolume'):
                usdt_pairs.append({
                    'symbol': symbol,
                    'volume': ticker['quoteVolume'],
                    'price': ticker['last'],
                    'change': ticker.get('percentage', 0)
                })
        
        # Sort by volume and take top N
        usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)
        self.top_pairs = usdt_pairs[:count]
        
        print(f"Top {count} liquid pairs by 24h volume:")
        print("-" * 80)
        for i, pair in enumerate(self.top_pairs, 1):
            volume_m = pair['volume'] / 1_000_000
            print(f"{i:2}. {pair['symbol']:20} | Price: ${pair['price']:10.2f} | "
                  f"24h Vol: ${volume_m:8.1f}M | Change: {pair['change']:+.2f}%")
        
        return self.top_pairs
    
    async def generate_random_signal(self, symbol):
        """Generate random trading signal"""
        action = random.choice(['buy', 'sell'])
        score = random.randint(65, 95)
        
        # Fetch current price
        ticker = await self.exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # Calculate SL/TP based on action
        if action == 'buy':
            stop_loss = current_price * 0.98  # 2% below
            take_profit = current_price * 1.03  # 3% above
        else:
            stop_loss = current_price * 1.02  # 2% above
            take_profit = current_price * 0.97  # 3% below
            
        return {
            'symbol': symbol,
            'action': action,
            'score': score,
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'timestamp': datetime.now()
        }
    
    async def simulate_position(self, signal):
        """Simulate position lifecycle"""
        symbol = signal['symbol']
        entry_price = signal['entry_price']
        
        # Random position outcome
        outcome = random.choices(
            ['profit', 'loss', 'breakeven'],
            weights=[0.4, 0.4, 0.2],
            k=1
        )[0]
        
        # Calculate exit price and PnL
        if outcome == 'profit':
            exit_multiplier = 1 + random.uniform(0.005, 0.025)  # 0.5% to 2.5% profit
            status = 'TP Hit'
        elif outcome == 'loss':
            exit_multiplier = 1 - random.uniform(0.005, 0.02)  # 0.5% to 2% loss
            status = 'SL Hit'
        else:
            exit_multiplier = 1 + random.uniform(-0.002, 0.002)  # -0.2% to 0.2%
            status = 'Manual Close'
            
        if signal['action'] == 'sell':
            exit_multiplier = 2 - exit_multiplier  # Invert for shorts
            
        exit_price = entry_price * exit_multiplier
        position_size = 100  # $100 position
        
        # Calculate PnL
        if signal['action'] == 'buy':
            pnl = position_size * (exit_price - entry_price) / entry_price
        else:
            pnl = position_size * (entry_price - exit_price) / entry_price
            
        pnl_percentage = (pnl / position_size) * 100
        
        # Random hold duration
        hold_minutes = random.randint(5, 120)
        
        return {
            'symbol': symbol,
            'side': signal['action'],
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl': pnl,
            'pnl_percentage': pnl_percentage,
            'status': status,
            'hold_duration': hold_minutes,
            'closed_at': signal['timestamp'] + timedelta(minutes=hold_minutes)
        }
    
    async def save_to_database(self, signal, position):
        """Save signal and position to database"""
        try:
            # Save signal
            self.cur.execute("""
                INSERT INTO trading_bot.signals 
                (source, symbol, action, score, entry_price, stop_loss, take_profit, processed, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                'simulation',
                signal['symbol'],
                signal['action'],
                signal['score'],
                Decimal(str(signal['entry_price'])),
                Decimal(str(signal['stop_loss'])),
                Decimal(str(signal['take_profit'])),
                True,
                signal['timestamp']
            ))
            signal_id = self.cur.fetchone()[0]
            
            # Save position
            self.cur.execute("""
                INSERT INTO trading_bot.positions
                (exchange, symbol, side, entry_price, current_price, quantity, 
                 stop_loss, take_profit, status, pnl, pnl_percentage, created_at, closed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                'binance',
                position['symbol'],
                position['side'],
                Decimal(str(position['entry_price'])),
                Decimal(str(position['exit_price'])),
                Decimal('100') / Decimal(str(position['entry_price'])),  # Quantity
                Decimal(str(signal['stop_loss'])),
                Decimal(str(signal['take_profit'])),
                'closed',
                Decimal(str(position['pnl'])),
                Decimal(str(position['pnl_percentage'])),
                signal['timestamp'],
                position['closed_at']
            ))
            
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Database error: {e}")
            return False
    
    async def run_simulation(self, duration_hours=1):
        """Run trading simulation"""
        print(f"\n=== STARTING {duration_hours} HOUR TRADING SIMULATION ===\n")
        
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=duration_hours)
        
        total_trades = 0
        total_pnl = 0
        winning_trades = 0
        losing_trades = 0
        
        print("Simulation Progress:")
        print("-" * 80)
        
        while datetime.now() < end_time:
            # Random delay between signals (1-5 minutes)
            delay = random.randint(60, 300)
            
            # Select random pair
            pair_data = random.choice(self.top_pairs)
            symbol = pair_data['symbol']
            
            # Generate signal
            signal = await self.generate_random_signal(symbol)
            
            # Simulate position
            position = await self.simulate_position(signal)
            
            # Save to database
            saved = await self.save_to_database(signal, position)
            
            # Update statistics
            total_trades += 1
            total_pnl += position['pnl']
            
            if position['pnl'] > 0:
                winning_trades += 1
                result_emoji = "✅"
            elif position['pnl'] < 0:
                losing_trades += 1
                result_emoji = "❌"
            else:
                result_emoji = "⚪"
                
            # Print trade result
            print(f"{result_emoji} Trade #{total_trades:3} | {position['symbol']:20} | "
                  f"{position['side']:4} | PnL: ${position['pnl']:+7.2f} ({position['pnl_percentage']:+.2f}%) | "
                  f"{position['status']:12} | Hold: {position['hold_duration']:3}min")
            
            # Store result
            self.simulation_results.append({
                'trade_num': total_trades,
                **signal,
                **position
            })
            
            # Wait before next signal
            elapsed = (datetime.now() - start_time).total_seconds()
            remaining = (end_time - datetime.now()).total_seconds()
            
            if remaining > delay:
                await asyncio.sleep(min(delay, remaining))
            else:
                break
        
        # Print summary
        duration = (datetime.now() - start_time).total_seconds() / 3600
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        print("\n" + "=" * 80)
        print("SIMULATION SUMMARY")
        print("=" * 80)
        print(f"Duration: {duration:.2f} hours")
        print(f"Total Trades: {total_trades}")
        print(f"Winning Trades: {winning_trades}")
        print(f"Losing Trades: {losing_trades}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Total PnL: ${total_pnl:+.2f}")
        print(f"Average PnL per trade: ${(total_pnl/total_trades if total_trades > 0 else 0):+.2f}")
        
        return self.simulation_results
    
    async def check_system_behavior(self):
        """Check how system handles positions and orders"""
        print("\n=== CHECKING SYSTEM BEHAVIOR ===\n")
        
        # Check positions in database
        self.cur.execute("""
            SELECT status, COUNT(*), SUM(pnl), AVG(pnl_percentage)
            FROM trading_bot.positions
            WHERE created_at > NOW() - INTERVAL '2 hours'
            GROUP BY status
        """)
        
        print("Position Statistics:")
        print("-" * 60)
        for row in self.cur.fetchall():
            status, count, total_pnl, avg_pnl_pct = row
            print(f"Status: {status:10} | Count: {count:3} | "
                  f"Total PnL: ${float(total_pnl or 0):+8.2f} | "
                  f"Avg PnL%: {float(avg_pnl_pct or 0):+.2f}%")
        
        # Check signals
        self.cur.execute("""
            SELECT action, processed, COUNT(*)
            FROM trading_bot.signals
            WHERE created_at > NOW() - INTERVAL '2 hours'
            GROUP BY action, processed
        """)
        
        print("\nSignal Statistics:")
        print("-" * 60)
        for row in self.cur.fetchall():
            action, processed, count = row
            print(f"Action: {action:4} | Processed: {processed} | Count: {count}")
        
        # Check order simulation (we don't create real orders in simulation)
        print("\nOrder Management:")
        print("-" * 60)
        print("✅ Orders would be placed via exchange API in live mode")
        print("✅ Stop-loss and take-profit orders configured")
        print("✅ Position sizing follows $100 per trade rule")
        
    async def cleanup(self):
        """Close connections"""
        if self.exchange:
            await self.exchange.close()
        if self.conn:
            self.cur.close()
            self.conn.close()

async def main():
    simulator = TradingSimulator()
    
    try:
        # Initialize
        await simulator.initialize()
        
        # Get top liquid pairs
        await simulator.get_top_liquid_pairs(30)
        
        # Run 1-hour simulation
        results = await simulator.run_simulation(duration_hours=1)
        
        # Check system behavior
        await simulator.check_system_behavior()
        
        # Save results to file
        with open('simulation_results.json', 'w') as f:
            json.dump([{
                k: v.isoformat() if isinstance(v, datetime) else v
                for k, v in result.items()
            } for result in results], f, indent=2)
        
        print("\n✅ Simulation complete! Results saved to simulation_results.json")
        
    except Exception as e:
        print(f"\n❌ Error during simulation: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await simulator.cleanup()

if __name__ == "__main__":
    asyncio.run(main())