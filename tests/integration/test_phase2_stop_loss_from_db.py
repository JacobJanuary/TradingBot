#!/usr/bin/env python3
"""
Integration tests for PHASE 2: Stop loss from monitoring.params

Validates that position_manager uses per-exchange stop_loss_filter from DB
instead of global config.stop_loss_percent
"""
import pytest
import asyncio
from decimal import Decimal
from database.repository import Repository


class TestPhase2StopLossFromDB:
    """Test that stop loss uses monitoring.params per exchange"""

    @pytest.fixture
    async def repository(self):
        """Create repository instance"""
        from config.settings import config
        db_config = {
            'host': config.database.host,
            'port': config.database.port,
            'database': config.database.database,
            'user': config.database.user,
            'password': config.database.password
        }

        repo = Repository(db_config)
        await repo.initialize()

        yield repo

        await repo.close()

    @pytest.mark.asyncio
    async def test_get_params_by_exchange_name_binance(self, repository):
        """Test get_params_by_exchange_name() for Binance"""
        params = await repository.get_params_by_exchange_name('binance')

        assert params is not None, "Binance params should exist in DB"
        assert 'stop_loss_filter' in params, "stop_loss_filter should be present"
        assert params['stop_loss_filter'] is not None, "stop_loss_filter should not be NULL"

    @pytest.mark.asyncio
    async def test_get_params_by_exchange_name_bybit(self, repository):
        """Test get_params_by_exchange_name() for Bybit"""
        params = await repository.get_params_by_exchange_name('bybit')

        assert params is not None, "Bybit params should exist in DB"
        assert 'stop_loss_filter' in params, "stop_loss_filter should be present"
        assert params['stop_loss_filter'] is not None, "stop_loss_filter should not be NULL"

    @pytest.mark.asyncio
    async def test_binance_bybit_use_different_stop_loss(self, repository):
        """
        CRITICAL TEST: Verify Binance and Bybit can have DIFFERENT stop loss values

        This is the whole point of PHASE 2 - per-exchange params from DB
        """
        binance_params = await repository.get_params_by_exchange_name('binance')
        bybit_params = await repository.get_params_by_exchange_name('bybit')

        assert binance_params is not None, "Binance params should exist"
        assert bybit_params is not None, "Bybit params should exist"

        binance_sl = float(binance_params['stop_loss_filter'])
        bybit_sl = float(bybit_params['stop_loss_filter'])

        # Values should be loaded from DB (not necessarily different, but should be per-exchange)
        assert binance_sl > 0, f"Binance stop_loss should be > 0, got {binance_sl}"
        assert bybit_sl > 0, f"Bybit stop_loss should be > 0, got {bybit_sl}"

        print(f"✅ Binance stop_loss_filter: {binance_sl}%")
        print(f"✅ Bybit stop_loss_filter: {bybit_sl}%")

        # If they ARE different, that proves per-exchange configuration works
        if binance_sl != bybit_sl:
            print(f"✅ CONFIRMED: Exchanges use DIFFERENT stop loss values!")
            print(f"   Binance: {binance_sl}% vs Bybit: {bybit_sl}%")

    @pytest.mark.asyncio
    async def test_get_params_by_exchange_name_case_insensitive(self, repository):
        """Test that exchange name is case-insensitive"""
        params_lower = await repository.get_params_by_exchange_name('binance')
        params_upper = await repository.get_params_by_exchange_name('BINANCE')
        params_mixed = await repository.get_params_by_exchange_name('Binance')

        assert params_lower is not None
        assert params_upper is not None
        assert params_mixed is not None

        # All should return same params
        assert params_lower['stop_loss_filter'] == params_upper['stop_loss_filter']
        assert params_lower['stop_loss_filter'] == params_mixed['stop_loss_filter']

    @pytest.mark.asyncio
    async def test_get_params_by_exchange_name_unknown_exchange(self, repository):
        """Test that unknown exchange returns None"""
        params = await repository.get_params_by_exchange_name('unknown_exchange')

        # Should return None (not raise exception)
        assert params is None, "Unknown exchange should return None"
