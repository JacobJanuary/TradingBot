#!/usr/bin/env python3
"""
Deep Research: Bybit Price Fetching Issue
Проверяет различные методы получения цен для проблемных Bybit символов
"""

import asyncio
import ccxt
import os
from dotenv import load_dotenv
from decimal import Decimal

# Загружаем .env
load_dotenv()

# Проблемные символы (все с Bybit)
PROBLEM_SYMBOLS = [
    '1000NEIROCTOUSDT', 'AGIUSDT', 'BOBAUSDT', 'CLOUDUSDT',
    'DOGUSDT', 'ETHBTCUSDT', 'GLMRUSDT', 'HNTUSDT',
    'IDEXUSDT', 'NODEUSDT', 'OKBUSDT', 'ORBSUSDT',
    'OSMOUSDT', 'PYRUSDT', 'RADUSDT', 'SAROSUSDT',
    'SCAUSDT', 'XDCUSDT'
]

class BybitPriceResearcher:
    def __init__(self):
        self.exchange = None
        self.results = {
            'method_1_fetch_ticker': {},
            'method_2_fetch_tickers': {},
            'method_3_fetch_order_book': {},
            'method_4_fetch_trades': {},
            'method_5_market_info': {},
            'errors': []
        }

    async def initialize_exchange(self):
        """Инициализация Bybit TESTNET"""
        print("🔧 Initializing Bybit TESTNET...")

        self.exchange = ccxt.bybit({
            'apiKey': os.getenv('BYBIT_API_KEY_TESTNET'),
            'secret': os.getenv('BYBIT_SECRET_TESTNET'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',  # Futures
                'testnet': True,
            }
        })

        self.exchange.set_sandbox_mode(True)

        # Загрузим markets (sync method in ccxt)
        self.exchange.load_markets()
        print(f"✅ Loaded {len(self.exchange.markets)} markets")

    async def method_1_fetch_ticker(self, symbol: str):
        """Метод 1: fetch_ticker() - стандартный способ"""
        try:
            # Конвертируем формат символа
            ccxt_symbol = symbol.replace('USDT', '/USDT:USDT')
            ticker = await self.exchange.fetch_ticker(ccxt_symbol)

            price = ticker.get('last') or ticker.get('close')
            self.results['method_1_fetch_ticker'][symbol] = {
                'success': True,
                'price': price,
                'ticker': ticker
            }
            return price
        except Exception as e:
            error_detail = f"{type(e).__name__}: {str(e)}"
            self.results['method_1_fetch_ticker'][symbol] = {
                'success': False,
                'error': error_detail
            }
            self.results['errors'].append(f"Method 1 ({symbol}): {error_detail}")
            print(f"  DEBUG: {symbol} error - {error_detail}")
            return None

    async def method_2_fetch_tickers(self, symbols: list):
        """Метод 2: fetch_tickers() - массовое получение"""
        try:
            ccxt_symbols = [s.replace('USDT', '/USDT:USDT') for s in symbols]
            tickers = await self.exchange.fetch_tickers(ccxt_symbols)

            for symbol in symbols:
                ccxt_symbol = symbol.replace('USDT', '/USDT:USDT')
                ticker = tickers.get(ccxt_symbol)

                if ticker:
                    price = ticker.get('last') or ticker.get('close')
                    self.results['method_2_fetch_tickers'][symbol] = {
                        'success': True,
                        'price': price
                    }
                else:
                    self.results['method_2_fetch_tickers'][symbol] = {
                        'success': False,
                        'error': 'Ticker not in response'
                    }
        except Exception as e:
            self.results['errors'].append(f"Method 2 (batch): {e}")
            for symbol in symbols:
                self.results['method_2_fetch_tickers'][symbol] = {
                    'success': False,
                    'error': str(e)
                }

    async def method_3_fetch_order_book(self, symbol: str):
        """Метод 3: fetch_order_book() - через стакан"""
        try:
            ccxt_symbol = symbol.replace('USDT', '/USDT:USDT')
            orderbook = await self.exchange.fetch_order_book(ccxt_symbol)

            if orderbook['asks'] and orderbook['bids']:
                price = (orderbook['asks'][0][0] + orderbook['bids'][0][0]) / 2
                self.results['method_3_fetch_order_book'][symbol] = {
                    'success': True,
                    'price': price,
                    'spread': orderbook['asks'][0][0] - orderbook['bids'][0][0]
                }
                return price
            else:
                self.results['method_3_fetch_order_book'][symbol] = {
                    'success': False,
                    'error': 'Empty orderbook'
                }
                return None
        except Exception as e:
            self.results['method_3_fetch_order_book'][symbol] = {
                'success': False,
                'error': str(e)
            }
            self.results['errors'].append(f"Method 3 ({symbol}): {e}")
            return None

    async def method_4_fetch_trades(self, symbol: str):
        """Метод 4: fetch_trades() - через последние сделки"""
        try:
            ccxt_symbol = symbol.replace('USDT', '/USDT:USDT')
            trades = await self.exchange.fetch_trades(ccxt_symbol, limit=1)

            if trades and len(trades) > 0:
                price = trades[0]['price']
                self.results['method_4_fetch_trades'][symbol] = {
                    'success': True,
                    'price': price,
                    'timestamp': trades[0]['timestamp']
                }
                return price
            else:
                self.results['method_4_fetch_trades'][symbol] = {
                    'success': False,
                    'error': 'No trades'
                }
                return None
        except Exception as e:
            self.results['method_4_fetch_trades'][symbol] = {
                'success': False,
                'error': str(e)
            }
            self.results['errors'].append(f"Method 4 ({symbol}): {e}")
            return None

    async def method_5_market_info(self, symbol: str):
        """Метод 5: Проверка market info"""
        try:
            ccxt_symbol = symbol.replace('USDT', '/USDT:USDT')

            if ccxt_symbol in self.exchange.markets:
                market = self.exchange.markets[ccxt_symbol]
                self.results['method_5_market_info'][symbol] = {
                    'success': True,
                    'exists': True,
                    'active': market.get('active'),
                    'type': market.get('type'),
                    'settle': market.get('settle'),
                    'quote': market.get('quote'),
                    'info': {
                        'status': market.get('info', {}).get('status'),
                        'contractType': market.get('info', {}).get('contractType')
                    }
                }
                return True
            else:
                self.results['method_5_market_info'][symbol] = {
                    'success': False,
                    'exists': False,
                    'error': 'Market not found'
                }
                return False
        except Exception as e:
            self.results['method_5_market_info'][symbol] = {
                'success': False,
                'error': str(e)
            }
            self.results['errors'].append(f"Method 5 ({symbol}): {e}")
            return False

    async def test_aged_manager_method(self, symbol: str):
        """Точная копия метода из aged_position_manager"""
        print(f"\n🔬 Testing EXACT aged_position_manager method for {symbol}")

        try:
            # Это точная копия кода из aged_position_manager._get_current_price()
            ccxt_symbol = symbol.replace('USDT', '/USDT:USDT')
            ticker = await self.exchange.fetch_ticker(ccxt_symbol)

            # CRITICAL: это строка, которая падает с NoneType error
            price = ticker['last'] if ticker['last'] else ticker['close']

            print(f"  ✅ SUCCESS: {symbol} = ${price}")
            return price

        except Exception as e:
            print(f"  ❌ ERROR: {symbol} - {type(e).__name__}: {e}")

            # Проверим, что именно None
            try:
                ticker = await self.exchange.fetch_ticker(ccxt_symbol)
                print(f"  🔍 Ticker keys: {ticker.keys() if ticker else 'None'}")
                print(f"  🔍 ticker['last'] = {ticker.get('last') if ticker else 'N/A'}")
                print(f"  🔍 ticker['close'] = {ticker.get('close') if ticker else 'N/A'}")
            except:
                pass

            return None

    async def run_full_research(self):
        """Запуск полного исследования"""
        print("=" * 80)
        print("🔬 BYBIT PRICE FETCHING DEEP RESEARCH")
        print("=" * 80)

        await self.initialize_exchange()

        print(f"\n📋 Testing {len(PROBLEM_SYMBOLS)} problematic symbols...")
        print(f"Symbols: {', '.join(PROBLEM_SYMBOLS[:5])}... (+{len(PROBLEM_SYMBOLS)-5} more)")

        # Метод 5: Сначала проверим, существуют ли markets
        print("\n" + "=" * 80)
        print("METHOD 5: Market Information Check")
        print("=" * 80)
        for symbol in PROBLEM_SYMBOLS:
            await self.method_5_market_info(symbol)

        # Метод 1: fetch_ticker для каждого
        print("\n" + "=" * 80)
        print("METHOD 1: fetch_ticker() - Individual")
        print("=" * 80)
        for symbol in PROBLEM_SYMBOLS[:3]:  # Тестируем первые 3
            price = await self.method_1_fetch_ticker(symbol)
            if price:
                print(f"  ✅ {symbol}: ${price}")
            else:
                print(f"  ❌ {symbol}: FAILED")
            await asyncio.sleep(0.5)

        # Метод 2: fetch_tickers batch
        print("\n" + "=" * 80)
        print("METHOD 2: fetch_tickers() - Batch")
        print("=" * 80)
        await self.method_2_fetch_tickers(PROBLEM_SYMBOLS[:5])

        # Метод 3: orderbook
        print("\n" + "=" * 80)
        print("METHOD 3: fetch_order_book()")
        print("=" * 80)
        for symbol in PROBLEM_SYMBOLS[:3]:
            price = await self.method_3_fetch_order_book(symbol)
            if price:
                print(f"  ✅ {symbol}: ${price}")
            else:
                print(f"  ❌ {symbol}: FAILED")
            await asyncio.sleep(0.5)

        # Метод 4: trades
        print("\n" + "=" * 80)
        print("METHOD 4: fetch_trades()")
        print("=" * 80)
        for symbol in PROBLEM_SYMBOLS[:3]:
            price = await self.method_4_fetch_trades(symbol)
            if price:
                print(f"  ✅ {symbol}: ${price}")
            else:
                print(f"  ❌ {symbol}: FAILED")
            await asyncio.sleep(0.5)

        # Тестируем ТОЧНЫЙ метод из aged_position_manager
        print("\n" + "=" * 80)
        print("EXACT METHOD: Aged Position Manager Code")
        print("=" * 80)
        for symbol in PROBLEM_SYMBOLS[:5]:
            await self.test_aged_manager_method(symbol)
            await asyncio.sleep(0.5)

        await self.generate_report()

    async def generate_report(self):
        """Генерация детального отчёта"""
        print("\n" + "=" * 80)
        print("📊 RESEARCH RESULTS SUMMARY")
        print("=" * 80)

        # Market existence
        exists = sum(1 for r in self.results['method_5_market_info'].values() if r.get('exists'))
        print(f"\n✅ Markets exist: {exists}/{len(PROBLEM_SYMBOLS)}")

        # Success rates
        methods = [
            ('fetch_ticker', 'method_1_fetch_ticker'),
            ('fetch_tickers', 'method_2_fetch_tickers'),
            ('orderbook', 'method_3_fetch_order_book'),
            ('trades', 'method_4_fetch_trades'),
        ]

        print("\n📈 Success Rates by Method:")
        for name, key in methods:
            total = len(self.results[key])
            if total > 0:
                success = sum(1 for r in self.results[key].values() if r.get('success'))
                rate = (success / total) * 100
                print(f"  {name:20s}: {success}/{total} ({rate:.1f}%)")

        # Errors summary
        if self.results['errors']:
            print(f"\n❌ Total Errors: {len(self.results['errors'])}")
            print("\nUnique Error Types:")
            error_types = {}
            for err in self.results['errors']:
                error_type = err.split(':')[0] if ':' in err else err
                error_types[error_type] = error_types.get(error_type, 0) + 1

            for err_type, count in sorted(error_types.items(), key=lambda x: -x[1]):
                print(f"  • {err_type}: {count} occurrences")

        print("\n" + "=" * 80)
        print("💡 RECOMMENDATIONS")
        print("=" * 80)

        # Analyze which method works best
        best_method = None
        best_rate = 0
        for name, key in methods:
            total = len(self.results[key])
            if total > 0:
                success = sum(1 for r in self.results[key].values() if r.get('success'))
                rate = (success / total) * 100
                if rate > best_rate:
                    best_rate = rate
                    best_method = name

        if best_method and best_rate > 50:
            print(f"✅ BEST METHOD: {best_method} ({best_rate:.1f}% success)")
            print(f"   Recommendation: Use {best_method} as primary method")
        elif best_method:
            print(f"⚠️ PARTIAL SUCCESS: {best_method} ({best_rate:.1f}% success)")
            print(f"   Recommendation: Implement fallback chain")
        else:
            print(f"❌ NO RELIABLE METHOD FOUND")
            print(f"   This is likely a TESTNET limitation")

        print("\n" + "=" * 80)

async def main():
    researcher = BybitPriceResearcher()
    await researcher.run_full_research()
    await researcher.exchange.close()

if __name__ == '__main__':
    asyncio.run(main())
