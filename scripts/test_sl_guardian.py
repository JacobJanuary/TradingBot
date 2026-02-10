
import asyncio
import logging
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestGuardian")

# Import the class (ensure path is correct)
try:
    from core.stop_loss_manager import StopLossManager
    print("IMPORTED StopLossManager")
except ImportError:
    print("FAILED to import StopLossManager. Check path.")
    sys.exit(1)

class BrokenExchange:
    """Mock exchange that raises AttributeError on Algo methods"""
    def __init__(self):
        self.options = {}
    
    @property
    def fapiPrivatePostAlgoOrder(self):
        print(">> Accessing fapiPrivatePostAlgoOrder... RAISING AttributeError")
        raise AttributeError("'binance' object has no attribute 'fapiPrivatePostAlgoOrder'")

    @property
    def fapiprivate_post_algoorder(self):
         print(">> Accessing snake_case... RAISING AttributeError")
         raise AttributeError("Snake case missing too")

    def milliseconds(self):
        return 1000
    
    def price_to_precision(self, symbol, price):
        return float(price) # Mock return

    def amount_to_precision(self, symbol, amount):
        return float(amount)

class TestStopLossGuardian(unittest.IsolatedAsyncioTestCase):
    async def test_protection_logic(self):
        print("\n--- TESTING STOP LOSS GUARDIAN ---")
        
        # 1. Create broken exchange
        exchange = BrokenExchange()
        
        # 2. Init Manager
        # core.stop_loss_manager.StopLossManager(exchange, exchange_name, position_exchange_object=None)
        # Note: arg names might differ, checking init signature... 
        # def __init__(self, exchange, exchange_name='binance', position_exchange=None, position_manager=None):
        manager = StopLossManager(exchange, 'binance')
        
        # 3. Call _set_binance_stop_loss_algo
        # It's internal, but we can call it.
        # Arguments: symbol, stop_price, side, quantity
        print("Calling _set_binance_stop_loss_algo...")
        
        try:
            await manager._set_binance_stop_loss_algo(
                symbol="BTCUSDT",
                stop_price=50000,
                side="short", 
                amount=0.1
            )
            print("Did not raise exception (handled internals)")
        except AttributeError as e:
            print(f"CRITICAL FAILURE: AttributeError leaked! {e}")
            if str(e) == "CCXT_MISSING_ALGO_METHOD_V2":
                print("SUCCESS: Leaked custom error 'CCXT_MISSING_ALGO_METHOD_V2' -> Logic works (caught and re-raised)")
            elif "fapiPrivatePostAlgoOrder" in str(e):
                print("FAILURE: Original AttributeError leaked! Logic is broken.")
                self.fail("Original AttributeError leaked")
        except Exception as e:
            print(f"Caught generic exception: {e}")
            if "CCXT_MISSING_ALGO_METHOD_V2" in str(e):
                print("SUCCESS: Logic correctly identified missing method.")
            else:
                print(f"Unknown exception: {e}")

if __name__ == "__main__":
    unittest.main()
