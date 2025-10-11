#!/usr/bin/env python3
"""
Test Exchange Response Adapter
Ensures correct normalization of exchange responses
"""
import pytest
from core.exchange_response_adapter import ExchangeResponseAdapter, NormalizedOrder


class TestExchangeAdapter:
    """Test exchange response normalization"""

    def test_bybit_market_order_normalization(self):
        """Test Bybit market order response normalization"""
        # Typical Bybit response with missing fields
        bybit_response = {
            'id': 'abc123',
            'status': None,  # Often missing
            'side': None,  # Often missing for market orders
            'amount': None,
            'filled': None,
            'info': {
                'orderId': 'abc123',
                'orderStatus': 'Filled',
                'side': 'Buy',
                'qty': '0.001',
                'cumExecQty': '0.001',
                'avgPrice': '60000',
                'symbol': 'BTCUSDT'
            }
        }

        order = ExchangeResponseAdapter.normalize_order(bybit_response, 'bybit')

        assert order.id == 'abc123'
        assert order.status == 'closed'  # 'Filled' maps to 'closed'
        assert order.side == 'buy'
        assert order.amount == 0.001
        assert order.filled == 0.001
        assert order.average == 60000
        assert ExchangeResponseAdapter.is_order_filled(order) is True

    def test_binance_order_normalization(self):
        """Test Binance order response normalization"""
        binance_response = {
            'id': '12345',
            'status': 'closed',
            'side': 'sell',
            'amount': 0.002,
            'filled': 0.002,
            'average': 59500,
            'symbol': 'BTC/USDT',
            'info': {
                'orderId': '12345',
                'status': 'FILLED',
                'side': 'SELL',
                'origQty': '0.002',
                'executedQty': '0.002',
                'avgPrice': '59500'
            }
        }

        order = ExchangeResponseAdapter.normalize_order(binance_response, 'binance')

        assert order.id == '12345'
        assert order.status == 'closed'
        assert order.side == 'sell'
        assert order.amount == 0.002
        assert order.filled == 0.002
        assert order.average == 59500
        assert ExchangeResponseAdapter.is_order_filled(order) is True

    def test_partial_fill_detection(self):
        """Test partial fill detection"""
        partial_order = NormalizedOrder(
            id='123',
            status='open',
            side='buy',
            amount=1.0,
            filled=0.5,  # Only half filled
            price=50000,
            average=50000,
            symbol='BTC/USDT',
            type='limit',
            raw_data={}
        )

        assert ExchangeResponseAdapter.is_order_filled(partial_order) is False

    def test_market_order_fill_detection(self):
        """Test market order fill detection with small discrepancy"""
        market_order = NormalizedOrder(
            id='456',
            status='open',  # Status might not be updated yet
            side='sell',
            amount=1.0,
            filled=0.9995,  # Slight slippage
            price=None,
            average=60000,
            symbol='BTC/USDT',
            type='market',
            raw_data={}
        )

        # Should consider filled despite small discrepancy
        assert ExchangeResponseAdapter.is_order_filled(market_order) is True

    def test_extract_execution_price(self):
        """Test execution price extraction"""
        # Order with average price
        order1 = NormalizedOrder(
            id='1', status='closed', side='buy',
            amount=1.0, filled=1.0,
            price=50000, average=50100,  # Average takes priority
            symbol='BTC/USDT', type='market', raw_data={}
        )
        assert ExchangeResponseAdapter.extract_execution_price(order1) == 50100

        # Order without average, use price
        order2 = NormalizedOrder(
            id='2', status='closed', side='buy',
            amount=1.0, filled=1.0,
            price=50000, average=None,
            symbol='BTC/USDT', type='limit', raw_data={}
        )
        assert ExchangeResponseAdapter.extract_execution_price(order2) == 50000

        # Order with data in raw_data only
        order3 = NormalizedOrder(
            id='3', status='closed', side='buy',
            amount=1.0, filled=1.0,
            price=None, average=None,
            symbol='BTC/USDT', type='market',
            raw_data={'info': {'avgPrice': '51000'}}
        )
        assert ExchangeResponseAdapter.extract_execution_price(order3) == 51000

    def test_empty_response_handling(self):
        """Test handling of empty or malformed responses"""
        empty_response = {}
        order = ExchangeResponseAdapter.normalize_order(empty_response, 'unknown')

        assert order.id == 'unknown'
        assert order.status == 'unknown'
        assert order.amount == 0
        assert ExchangeResponseAdapter.is_order_filled(order) is False


if __name__ == "__main__":
    pytest.main([__file__, '-v'])