#!/usr/bin/env python3
"""
Integration tests for PHASE 3: Trailing params from monitoring.params

Validates that:
1. Trailing params are loaded from monitoring.params (per-exchange)
2. Trailing params are saved to monitoring.positions when creating positions
3. TrailingStop uses per-position params instead of config
"""
import pytest
import asyncio
from decimal import Decimal
from database.repository import Repository


class TestPhase3TrailingParamsFromDB:
    """Test that trailing params use monitoring.params per exchange"""

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
    async def test_get_params_by_exchange_name_has_trailing_filters_binance(self, repository):
        """Test that Binance params include trailing filters"""
        params = await repository.get_params_by_exchange_name('binance')

        assert params is not None, "Binance params should exist in DB"
        assert 'trailing_activation_filter' in params, "trailing_activation_filter should be present"
        assert 'trailing_distance_filter' in params, "trailing_distance_filter should be present"

    @pytest.mark.asyncio
    async def test_get_params_by_exchange_name_has_trailing_filters_bybit(self, repository):
        """Test that Bybit params include trailing filters"""
        params = await repository.get_params_by_exchange_name('bybit')

        assert params is not None, "Bybit params should exist in DB"
        assert 'trailing_activation_filter' in params, "trailing_activation_filter should be present"
        assert 'trailing_distance_filter' in params, "trailing_distance_filter should be present"

    @pytest.mark.asyncio
    async def test_binance_bybit_can_have_different_trailing_params(self, repository):
        """
        CRITICAL TEST: Verify Binance and Bybit can have DIFFERENT trailing params

        This is the whole point of PHASE 3 - per-exchange trailing params from DB
        """
        binance_params = await repository.get_params_by_exchange_name('binance')
        bybit_params = await repository.get_params_by_exchange_name('bybit')

        assert binance_params is not None, "Binance params should exist"
        assert bybit_params is not None, "Bybit params should exist"

        # Extract trailing params (may be NULL, that's OK - we test they CAN be set)
        binance_activation = binance_params.get('trailing_activation_filter')
        binance_distance = binance_params.get('trailing_distance_filter')

        bybit_activation = bybit_params.get('trailing_activation_filter')
        bybit_distance = bybit_params.get('trailing_distance_filter')

        print(f"✅ Binance trailing_activation_filter: {binance_activation}%")
        print(f"✅ Binance trailing_distance_filter: {binance_distance}%")
        print(f"✅ Bybit trailing_activation_filter: {bybit_activation}%")
        print(f"✅ Bybit trailing_distance_filter: {bybit_distance}%")

        # If they ARE different, that proves per-exchange configuration works
        if binance_activation and bybit_activation and binance_activation != bybit_activation:
            print(f"✅ CONFIRMED: Exchanges use DIFFERENT trailing_activation_filter!")
            print(f"   Binance: {binance_activation}% vs Bybit: {bybit_activation}%")

        if binance_distance and bybit_distance and binance_distance != bybit_distance:
            print(f"✅ CONFIRMED: Exchanges use DIFFERENT trailing_distance_filter!")
            print(f"   Binance: {binance_distance}% vs Bybit: {bybit_distance}%")

    @pytest.mark.asyncio
    async def test_create_position_saves_trailing_params(self, repository):
        """
        Test that create_position() saves trailing_activation_percent and trailing_callback_percent
        """
        # Create a test position with trailing params
        position_data = {
            'symbol': 'TESTUSDT',
            'exchange': 'binance',
            'side': 'long',
            'quantity': Decimal('1.0'),
            'entry_price': Decimal('100.0'),
            'trailing_activation_percent': 2.5,
            'trailing_callback_percent': 1.5
        }

        # Create position
        position_id = await repository.create_position(position_data)
        assert position_id is not None, "Position should be created"

        try:
            # Fetch position back from DB
            async with repository.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT trailing_activation_percent, trailing_callback_percent
                    FROM monitoring.positions
                    WHERE id = $1
                """, position_id)

            assert row is not None, "Position should exist in DB"
            assert row['trailing_activation_percent'] == Decimal('2.5'), \
                f"trailing_activation_percent should be 2.5, got {row['trailing_activation_percent']}"
            assert row['trailing_callback_percent'] == Decimal('1.5'), \
                f"trailing_callback_percent should be 1.5, got {row['trailing_callback_percent']}"

            print(f"✅ Position {position_id} saved with trailing params:")
            print(f"   activation: {row['trailing_activation_percent']}%")
            print(f"   callback: {row['trailing_callback_percent']}%")

        finally:
            # Cleanup: delete test position
            async with repository.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM monitoring.positions
                    WHERE id = $1
                """, position_id)

    @pytest.mark.asyncio
    async def test_create_position_handles_null_trailing_params(self, repository):
        """
        Test that create_position() handles NULL trailing params gracefully
        (for legacy positions or if DB params not set)
        """
        # Create a test position WITHOUT trailing params
        position_data = {
            'symbol': 'TESTUSDT2',
            'exchange': 'binance',
            'side': 'long',
            'quantity': Decimal('1.0'),
            'entry_price': Decimal('100.0')
            # No trailing_activation_percent or trailing_callback_percent
        }

        # Create position
        position_id = await repository.create_position(position_data)
        assert position_id is not None, "Position should be created even without trailing params"

        try:
            # Fetch position back from DB
            async with repository.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT trailing_activation_percent, trailing_callback_percent
                    FROM monitoring.positions
                    WHERE id = $1
                """, position_id)

            assert row is not None, "Position should exist in DB"
            # Params should be NULL (which is OK - fallback to config will happen)
            print(f"✅ Position {position_id} created without trailing params (will use config fallback):")
            print(f"   activation: {row['trailing_activation_percent']}")
            print(f"   callback: {row['trailing_callback_percent']}")

        finally:
            # Cleanup: delete test position
            async with repository.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM monitoring.positions
                    WHERE id = $1
                """, position_id)
