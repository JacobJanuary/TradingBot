#!/usr/bin/env python3
"""
Integration tests for monitoring.params repository operations
"""
import pytest
import asyncio
from database.repository import Repository
from config.settings import Config


class TestRepositoryParams:
    """Test params table operations"""

    @pytest.fixture
    async def repository(self):
        """Create repository instance"""
        config = Config()
        db_config = {
            'host': config.db_host,
            'port': config.db_port,
            'database': config.db_name,
            'user': config.db_user,
            'password': config.db_password
        }

        repo = Repository(db_config)
        await repo.initialize()

        yield repo

        await repo.close()

    @pytest.mark.asyncio
    async def test_get_params_binance(self, repository):
        """Test retrieving Binance params"""
        params = await repository.get_params(exchange_id=1)

        assert params is not None
        assert params['exchange_id'] == 1
        assert 'max_trades_filter' in params
        assert 'stop_loss_filter' in params
        assert 'updated_at' in params

    @pytest.mark.asyncio
    async def test_get_params_bybit(self, repository):
        """Test retrieving Bybit params"""
        params = await repository.get_params(exchange_id=2)

        assert params is not None
        assert params['exchange_id'] == 2

    @pytest.mark.asyncio
    async def test_update_all_params(self, repository):
        """Test updating all parameters"""
        success = await repository.update_params(
            exchange_id=1,
            max_trades_filter=12,
            stop_loss_filter=2.8,
            trailing_activation_filter=3.2,
            trailing_distance_filter=1.6
        )

        assert success is True

        # Verify update
        params = await repository.get_params(exchange_id=1)
        assert params['max_trades_filter'] == 12
        assert float(params['stop_loss_filter']) == 2.8
        assert float(params['trailing_activation_filter']) == 3.2
        assert float(params['trailing_distance_filter']) == 1.6

    @pytest.mark.asyncio
    async def test_update_partial_params(self, repository):
        """Test updating only some parameters"""
        # First, set initial values
        await repository.update_params(
            exchange_id=2,
            max_trades_filter=10,
            stop_loss_filter=2.5
        )

        # Update only max_trades
        success = await repository.update_params(
            exchange_id=2,
            max_trades_filter=15
        )

        assert success is True

        # Verify only max_trades changed
        params = await repository.get_params(exchange_id=2)
        assert params['max_trades_filter'] == 15
        assert float(params['stop_loss_filter']) == 2.5  # Unchanged

    @pytest.mark.asyncio
    async def test_get_all_params(self, repository):
        """Test retrieving all exchange params"""
        all_params = await repository.get_all_params()

        assert isinstance(all_params, dict)
        assert 1 in all_params  # Binance
        assert 2 in all_params  # Bybit

        assert all_params[1]['exchange_id'] == 1
        assert all_params[2]['exchange_id'] == 2

    @pytest.mark.asyncio
    async def test_update_invalid_exchange(self, repository):
        """Test updating non-existent exchange"""
        success = await repository.update_params(
            exchange_id=999,  # Invalid
            max_trades_filter=10
        )

        assert success is False
