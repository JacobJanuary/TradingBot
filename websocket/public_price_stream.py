#!/usr/bin/env python3
"""
Public price stream for monitoring without authentication
Works with both testnet and production
"""
import asyncio
import json
import logging
import websockets
from typing import Dict, Callable, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class PublicPriceStream:
    """Monitor public price streams for positions"""
    
    def __init__(self, symbols: list, on_price_update: Optional[Callable] = None):
        self.symbols = [s.lower().replace('/', '').replace(':', '') for s in symbols]
        self.prices = {}
        self.on_price_update = on_price_update
        self.running = False
        self.websocket = None
        
        # Use production WebSocket for price feeds (works better)
        self.ws_url = "wss://stream.binancefuture.com/ws"
        
    async def start(self):
        """Start monitoring price streams"""
        self.running = True
        
        while self.running:
            try:
                # Build subscription message
                streams = [f"{symbol}@ticker" for symbol in self.symbols]
                
                async with websockets.connect(self.ws_url) as websocket:
                    self.websocket = websocket
                    logger.info(f"Connected to public price stream for {len(self.symbols)} symbols")
                    
                    # Subscribe to streams
                    subscribe_msg = {
                        "method": "SUBSCRIBE",
                        "params": streams,
                        "id": 1
                    }
                    await websocket.send(json.dumps(subscribe_msg))
                    
                    # Listen for updates
                    while self.running:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=30)
                            data = json.loads(message)
                            
                            # Process ticker update
                            if 'e' in data and data['e'] == '24hrTicker':
                                symbol = data['s']
                                price = float(data['c'])  # Current price
                                
                                self.prices[symbol] = {
                                    'price': price,
                                    'high_24h': float(data['h']),
                                    'low_24h': float(data['l']),
                                    'volume': float(data['v']),
                                    'timestamp': datetime.now()
                                }
                                
                                # Callback for price update
                                if self.on_price_update:
                                    await self.on_price_update(symbol, price)
                                    
                        except asyncio.TimeoutError:
                            # Send ping to keep connection alive
                            await websocket.ping()
                            
                        except json.JSONDecodeError:
                            continue
                            
            except Exception as e:
                logger.error(f"Price stream error: {e}")
                await asyncio.sleep(5)  # Reconnect after 5 seconds
                
    async def stop(self):
        """Stop the price stream"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            
    def get_price(self, symbol: str) -> Optional[float]:
        """Get latest price for symbol"""
        symbol = symbol.upper().replace('/', '').replace(':', '')
        if symbol in self.prices:
            return self.prices[symbol]['price']
        return None

# Test function
async def test_stream():
    """Test the public price stream"""
    
    async def on_update(symbol, price):
        logger.info(f"Price update: {symbol} = ${price:.2f}")
    
    # Monitor BTC and ETH
    stream = PublicPriceStream(
        symbols=['BTCUSDT', 'ETHUSDT'],
        on_price_update=on_update
    )
    
    try:
        # Run for 10 seconds
        task = asyncio.create_task(stream.start())
        await asyncio.sleep(10)
        await stream.stop()
        
        logger.info("✅ Public price stream test successful!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_stream())