#!/usr/bin/env python3
"""Stress test for trading bot - testing multiple connections and high load"""

import asyncio
import random
import time
from datetime import datetime, timedelta
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import os
import psycopg2
from decimal import Decimal
import json

load_dotenv()

class StressTester:
    def __init__(self):
        self.results = {
            'connections_test': {},
            'signals_test': {},
            'orders_test': {},
            'database_test': {},
            'memory_test': {},
            'performance_metrics': {}
        }
        self.start_time = time.time()
        
    async def test_multiple_connections(self):
        """Test multiple simultaneous exchange connections"""
        print("\n=== STRESS TEST: MULTIPLE CONNECTIONS ===\n")
        
        connections = []
        max_connections = 5
        
        print(f"Creating {max_connections} simultaneous connections...")
        
        for i in range(max_connections):
            try:
                exchange = ccxt.binance({
                    'apiKey': os.getenv('BINANCE_API_KEY'),
                    'secret': os.getenv('BINANCE_API_SECRET'),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future',
                        'fetchPositions': 'positionRisk'
                    }
                })
                exchange.set_sandbox_mode(True)
                connections.append(exchange)
                print(f"  ✅ Connection {i+1} established")
            except Exception as e:
                print(f"  ❌ Connection {i+1} failed: {e}")
        
        # Test simultaneous operations
        print("\nTesting simultaneous operations...")
        tasks = []
        
        for i, exchange in enumerate(connections):
            async def fetch_data(ex, idx):
                try:
                    start = time.time()
                    await ex.load_markets()
                    ticker = await ex.fetch_ticker('BTC/USDT:USDT')
                    duration = time.time() - start
                    return idx, True, duration, ticker['last']
                except Exception as e:
                    return idx, False, 0, str(e)
            
            tasks.append(fetch_data(exchange, i))
        
        results = await asyncio.gather(*tasks)
        
        success_count = sum(1 for _, success, _, _ in results if success)
        avg_time = sum(duration for _, _, duration, _ in results) / len(results)
        
        print(f"\n  Successful operations: {success_count}/{len(connections)}")
        print(f"  Average response time: {avg_time:.2f}s")
        
        # Cleanup
        print("\nCleaning up connections...")
        for exchange in connections:
            await exchange.close()
        
        self.results['connections_test'] = {
            'max_connections': max_connections,
            'successful': success_count,
            'avg_response_time': avg_time
        }
        
        return success_count == max_connections
        
    async def test_rapid_signal_processing(self):
        """Test rapid signal generation and processing"""
        print("\n=== STRESS TEST: RAPID SIGNAL PROCESSING ===\n")
        
        # Connect to database
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5433'),
            database=os.getenv('DB_NAME', 'fox_crypto'),
            user=os.getenv('DB_USER', 'elcrypto'),
            password=os.getenv('DB_PASSWORD', 'LohNeMamont@!21')
        )
        cur = conn.cursor()
        
        print("Generating 100 rapid signals...")
        
        symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 
                  'SOL/USDT:USDT', 'XRP/USDT:USDT']
        
        signal_count = 0
        start_time = time.time()
        
        for i in range(100):
            symbol = random.choice(symbols)
            action = random.choice(['buy', 'sell'])
            score = random.randint(70, 95)
            
            try:
                cur.execute("""
                    INSERT INTO trading_bot.signals 
                    (source, symbol, action, score, entry_price, stop_loss, take_profit, processed, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    'stress_test', symbol, action, score,
                    Decimal('100'), Decimal('98'), Decimal('103'),
                    False, datetime.now()
                ))
                signal_count += 1
                
                if i % 10 == 0:
                    print(f"  Generated {i+1} signals...")
                    
            except Exception as e:
                print(f"  ❌ Signal {i+1} failed: {e}")
        
        conn.commit()
        duration = time.time() - start_time
        
        print(f"\n  ✅ Generated {signal_count} signals in {duration:.2f}s")
        print(f"  Rate: {signal_count/duration:.1f} signals/second")
        
        # Cleanup test signals
        cur.execute("DELETE FROM trading_bot.signals WHERE source = 'stress_test'")
        conn.commit()
        
        cur.close()
        conn.close()
        
        self.results['signals_test'] = {
            'total_signals': signal_count,
            'duration': duration,
            'rate': signal_count/duration
        }
        
        return signal_count == 100
        
    async def test_order_placement_simulation(self):
        """Simulate rapid order placement"""
        print("\n=== STRESS TEST: ORDER PLACEMENT SIMULATION ===\n")
        
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'fetchPositions': 'positionRisk'
            }
        })
        exchange.set_sandbox_mode(True)
        
        print("Simulating 50 order placements...")
        
        await exchange.load_markets()
        
        order_types = ['market', 'limit', 'stop_loss']
        symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT']
        
        simulated_orders = []
        start_time = time.time()
        
        for i in range(50):
            symbol = random.choice(symbols)
            order_type = random.choice(order_types)
            side = random.choice(['buy', 'sell'])
            
            # Simulate order (don't actually place)
            try:
                ticker = await exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                
                order = {
                    'id': f'SIM_{i:06d}',
                    'symbol': symbol,
                    'type': order_type,
                    'side': side,
                    'price': current_price,
                    'amount': 0.001,
                    'timestamp': datetime.now().isoformat()
                }
                
                simulated_orders.append(order)
                
                # Small delay to simulate real conditions
                await asyncio.sleep(0.1)
                
                if (i+1) % 10 == 0:
                    print(f"  Simulated {i+1} orders...")
                    
            except Exception as e:
                print(f"  ❌ Order {i+1} simulation failed: {e}")
        
        duration = time.time() - start_time
        
        print(f"\n  ✅ Simulated {len(simulated_orders)} orders in {duration:.2f}s")
        print(f"  Rate: {len(simulated_orders)/duration:.1f} orders/second")
        
        await exchange.close()
        
        self.results['orders_test'] = {
            'total_orders': len(simulated_orders),
            'duration': duration,
            'rate': len(simulated_orders)/duration
        }
        
        return len(simulated_orders) == 50
        
    async def test_database_performance(self):
        """Test database operations under load"""
        print("\n=== STRESS TEST: DATABASE PERFORMANCE ===\n")
        
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5433'),
            database=os.getenv('DB_NAME', 'fox_crypto'),
            user=os.getenv('DB_USER', 'elcrypto'),
            password=os.getenv('DB_PASSWORD', 'LohNeMamont@!21')
        )
        cur = conn.cursor()
        
        print("Testing database operations...")
        
        operations = {
            'inserts': 0,
            'selects': 0,
            'updates': 0,
            'deletes': 0
        }
        
        start_time = time.time()
        
        # Test INSERTs
        print("  1. Testing 100 INSERTs...")
        for i in range(100):
            cur.execute("""
                INSERT INTO trading_bot.risk_metrics 
                (open_positions, total_exposure, portfolio_value, daily_pnl, risk_score)
                VALUES (%s, %s, %s, %s, %s)
            """, (i, Decimal('1000'), Decimal('10000'), Decimal('100'), 50))
            operations['inserts'] += 1
        
        # Test SELECTs
        print("  2. Testing 100 SELECTs...")
        for i in range(100):
            cur.execute("SELECT * FROM trading_bot.risk_metrics ORDER BY id DESC LIMIT 10")
            cur.fetchall()
            operations['selects'] += 1
        
        # Test UPDATEs
        print("  3. Testing 50 UPDATEs...")
        for i in range(50):
            cur.execute("""
                UPDATE trading_bot.risk_metrics 
                SET daily_pnl = daily_pnl + 10 
                WHERE id = (SELECT id FROM trading_bot.risk_metrics ORDER BY id DESC LIMIT 1)
            """)
            operations['updates'] += 1
        
        # Cleanup
        print("  4. Cleaning up test data...")
        cur.execute("DELETE FROM trading_bot.risk_metrics WHERE portfolio_value = 10000")
        operations['deletes'] = cur.rowcount
        
        conn.commit()
        duration = time.time() - start_time
        
        total_ops = sum(operations.values())
        print(f"\n  ✅ Completed {total_ops} operations in {duration:.2f}s")
        print(f"  Rate: {total_ops/duration:.1f} ops/second")
        
        cur.close()
        conn.close()
        
        self.results['database_test'] = {
            'operations': operations,
            'total': total_ops,
            'duration': duration,
            'rate': total_ops/duration
        }
        
        return True
        
    def check_memory_usage(self):
        """Check memory usage"""
        import psutil
        
        process = psutil.Process()
        memory_info = process.memory_info()
        
        self.results['memory_test'] = {
            'rss_mb': memory_info.rss / 1024 / 1024,
            'vms_mb': memory_info.vms / 1024 / 1024,
            'cpu_percent': process.cpu_percent()
        }
        
        return True

async def main():
    print("🚀 COMPREHENSIVE STRESS TEST\n")
    print("=" * 60)
    
    tester = StressTester()
    
    # Run all tests
    tests = [
        ("Multiple Connections", tester.test_multiple_connections),
        ("Rapid Signals", tester.test_rapid_signal_processing),
        ("Order Simulation", tester.test_order_placement_simulation),
        ("Database Performance", tester.test_database_performance),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            print(f"\nRunning: {test_name}")
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with error: {e}")
            results.append((test_name, False))
    
    # Check memory
    tester.check_memory_usage()
    
    # Calculate metrics
    total_duration = time.time() - tester.start_time
    tester.results['performance_metrics'] = {
        'total_duration': total_duration,
        'tests_run': len(tests),
        'tests_passed': sum(1 for _, passed in results if passed)
    }
    
    # Summary
    print("\n" + "=" * 60)
    print("STRESS TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:25} {status}")
    
    print("\nPerformance Metrics:")
    print(f"  Connections/sec: {tester.results['connections_test'].get('avg_response_time', 0):.2f}")
    print(f"  Signals/sec: {tester.results['signals_test'].get('rate', 0):.1f}")
    print(f"  Orders/sec: {tester.results['orders_test'].get('rate', 0):.1f}")
    print(f"  DB ops/sec: {tester.results['database_test'].get('rate', 0):.1f}")
    print(f"  Memory usage: {tester.results['memory_test'].get('rss_mb', 0):.1f} MB")
    print(f"  Total duration: {total_duration:.2f}s")
    
    # Save results
    with open('stress_test_results.json', 'w') as f:
        json.dump(tester.results, f, indent=2, default=str)
    
    print("\n📄 Detailed results saved to stress_test_results.json")
    
    all_passed = all(passed for _, passed in results)
    if all_passed:
        print("\n✅ ALL STRESS TESTS PASSED")
    else:
        print("\n⚠️ SOME STRESS TESTS FAILED")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)