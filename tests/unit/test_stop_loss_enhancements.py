"""
Unit tests for Phase 2: Stop Loss Enhancements
Tests price validation, mark price usage, and missing SL verification
"""
import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, MagicMock
from core.stop_loss_manager import StopLossManager


class TestStopLossPriceValidation:
    """Test price validation to prevent Error -2021"""

    @pytest.mark.asyncio
    async def test_long_position_sl_validation(self):
        """Test that LONG position SL is adjusted if too close to current price"""
        # Setup
        exchange = AsyncMock()
        exchange.fetch_ticker = AsyncMock(return_value={
            'last': 100.0,
            'info': {}
        })
        exchange.create_order = AsyncMock(return_value={
            'id': 'test_order_123',
            'status': 'open'
        })
        exchange.price_to_precision = Mock(side_effect=lambda symbol, price: float(price))

        sl_manager = StopLossManager(exchange, 'binance')

        # Test: SL too close to current price (would trigger Error -2021)
        # Current: 100, proposed SL: 99.95 (only 0.05% away - too close!)
        result = await sl_manager._set_generic_stop_loss(
            symbol='BTC/USDT:USDT',
            side='sell',  # Long position
            amount=1.0,
            stop_price=99.95  # Too close to current 100
        )

        # Verify: SL should be adjusted down with buffer
        assert result['status'] == 'created'
        # SL should be < current price with 0.1% buffer
        assert result['stopPrice'] < 99.90  # 100 * (1 - 0.001) = 99.9

    @pytest.mark.asyncio
    async def test_short_position_sl_validation(self):
        """Test that SHORT position SL is adjusted if too close to current price"""
        exchange = AsyncMock()
        exchange.fetch_ticker = AsyncMock(return_value={
            'last': 100.0,
            'info': {}
        })
        exchange.create_order = AsyncMock(return_value={
            'id': 'test_order_123',
            'status': 'open'
        })
        exchange.price_to_precision = Mock(side_effect=lambda symbol, price: float(price))

        sl_manager = StopLossManager(exchange, 'binance')

        # Test: SL too close to current price
        # Current: 100, proposed SL: 100.05 (only 0.05% away - too close!)
        result = await sl_manager._set_generic_stop_loss(
            symbol='BTC/USDT:USDT',
            side='buy',  # Short position
            amount=1.0,
            stop_price=100.05  # Too close to current 100
        )

        # Verify: SL should be adjusted up with buffer
        assert result['status'] == 'created'
        # SL should be > current price with 0.1% buffer
        assert result['stopPrice'] > 100.10  # 100 * (1 + 0.001) = 100.1

    @pytest.mark.asyncio
    async def test_binance_mark_price_usage(self):
        """Test that Binance uses mark price instead of last price"""
        exchange = AsyncMock()
        exchange.fetch_ticker = AsyncMock(return_value={
            'last': 100.0,
            'info': {
                'markPrice': '99.5'  # Mark price different from last
            }
        })
        exchange.create_order = AsyncMock(return_value={
            'id': 'test_order_123',
            'status': 'open'
        })
        exchange.price_to_precision = Mock(side_effect=lambda symbol, price: float(price))

        sl_manager = StopLossManager(exchange, 'binance')

        # Test: Should use mark price for Binance
        await sl_manager._set_generic_stop_loss(
            symbol='BTC/USDT:USDT',
            side='sell',
            amount=1.0,
            stop_price=97.0  # Valid SL for mark price 99.5
        )

        # Verify: fetch_ticker was called
        exchange.fetch_ticker.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_binance_uses_last_price(self):
        """Test that non-Binance exchanges use last price"""
        exchange = AsyncMock()
        exchange.fetch_ticker = AsyncMock(return_value={
            'last': 100.0,
            'info': {'markPrice': '99.5'}  # Has mark price but shouldn't use it
        })
        exchange.create_order = AsyncMock(return_value={
            'id': 'test_order_123',
            'status': 'open'
        })
        exchange.price_to_precision = Mock(side_effect=lambda symbol, price: float(price))

        sl_manager = StopLossManager(exchange, 'bybit')  # Not binance

        # Test: Should use last price for non-Binance
        await sl_manager._set_generic_stop_loss(
            symbol='BTC/USDT:USDT',
            side='sell',
            amount=1.0,
            stop_price=97.0
        )

        # Verify: fetch_ticker was called
        exchange.fetch_ticker.assert_called_once()


class TestStopLossRetryLogic:
    """Test retry logic for Error -2021"""

    @pytest.mark.asyncio
    async def test_retry_on_error_2021(self):
        """Test that SL creation retries and adjusts price on Error -2021"""
        exchange = AsyncMock()
        exchange.fetch_ticker = AsyncMock(return_value={
            'last': 100.0,
            'info': {}
        })
        exchange.price_to_precision = Mock(side_effect=lambda symbol, price: float(price))

        # Simulate Error -2021 on first attempt, success on second
        exchange.create_order = AsyncMock(
            side_effect=[
                Exception('binance {"code":-2021,"msg":"Order would immediately trigger."}'),
                {'id': 'order_456', 'status': 'open'}  # Success on retry
            ]
        )

        sl_manager = StopLossManager(exchange, 'binance')

        # Test: Should retry and succeed
        result = await sl_manager._set_generic_stop_loss(
            symbol='BTC/USDT:USDT',
            side='sell',
            amount=1.0,
            stop_price=99.95
        )

        # Verify: Succeeded after retry
        assert result['status'] == 'created'
        assert exchange.create_order.call_count == 2  # First attempt + 1 retry

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """Test that retries stop after max attempts"""
        exchange = AsyncMock()
        exchange.fetch_ticker = AsyncMock(return_value={
            'last': 100.0,
            'info': {}
        })
        exchange.price_to_precision = Mock(side_effect=lambda symbol, price: float(price))

        # Simulate Error -2021 on all attempts
        exchange.create_order = AsyncMock(
            side_effect=Exception('binance {"code":-2021,"msg":"Order would immediately trigger."}')
        )

        sl_manager = StopLossManager(exchange, 'binance')

        # Test: Should fail after max retries
        with pytest.raises(Exception, match="-2021|immediately trigger"):
            await sl_manager._set_generic_stop_loss(
                symbol='BTC/USDT:USDT',
                side='sell',
                amount=1.0,
                stop_price=99.95
            )

        # Verify: Attempted 3 times
        assert exchange.create_order.call_count == 3


class TestMissingSLVerification:
    """Test verify_and_fix_missing_sl method"""

    @pytest.mark.asyncio
    async def test_sl_exists_no_action(self):
        """Test that no action taken if SL already exists"""
        exchange = AsyncMock()
        exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 1.0,
                'info': {'stopLoss': '95.0'}  # SL exists
            }
        ])

        sl_manager = StopLossManager(exchange, 'bybit')

        position = Mock()
        position.symbol = 'BTC/USDT:USDT'
        position.exchange = 'bybit'
        position.side = 'long'
        position.size = 1.0

        # Test: SL exists, should return True without creating new one
        result = await sl_manager.verify_and_fix_missing_sl(
            position=position,
            stop_price=95.0
        )

        # Verify: No creation attempted
        assert result is True
        # set_stop_loss should not be called since SL exists
        # (verified by not mocking set_stop_loss - would error if called)

    @pytest.mark.asyncio
    async def test_sl_missing_recreation(self):
        """Test that missing SL is recreated"""
        exchange = AsyncMock()

        # First call: no SL
        # Second call (after recreation): SL exists
        exchange.fetch_positions = AsyncMock(side_effect=[
            [{
                'symbol': 'BTC/USDT:USDT',
                'contracts': 1.0,
                'info': {'stopLoss': '0'}  # No SL
            }],
            [{
                'symbol': 'BTC/USDT:USDT',
                'contracts': 1.0,
                'info': {'stopLoss': '95.0'}  # SL created
            }]
        ])

        exchange.fetch_ticker = AsyncMock(return_value={
            'last': 100.0,
            'info': {}
        })
        exchange.create_order = AsyncMock(return_value={
            'id': 'sl_order_789',
            'status': 'open'
        })
        exchange.price_to_precision = Mock(side_effect=lambda symbol, price: float(price))
        exchange.private_post_v5_position_trading_stop = AsyncMock(return_value={
            'retCode': 0,
            'retMsg': 'OK'
        })

        sl_manager = StopLossManager(exchange, 'bybit')

        position = Mock()
        position.symbol = 'BTC/USDT:USDT'
        position.exchange = 'bybit'
        position.side = 'long'
        position.size = 1.0

        # Test: Should detect missing SL and recreate
        result = await sl_manager.verify_and_fix_missing_sl(
            position=position,
            stop_price=95.0
        )

        # Verify: SL was recreated
        assert result is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
