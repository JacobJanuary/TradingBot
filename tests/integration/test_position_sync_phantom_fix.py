"""
Integration test for Position Synchronizer phantom fix

Tests the complete synchronization workflow with the 3-phase fix:
1. Fetch positions from exchange with stricter filtering
2. Extract exchange_order_id
3. Validate and reject positions without order_id

Simulates the real bug scenario: CCXT returning stale cached data
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.position_synchronizer import PositionSynchronizer


@pytest.fixture
async def mock_repository():
    """Mock repository that tracks operations"""

    class MockRepository:
        def __init__(self):
            self.positions_created = []
            self.positions_closed = []
            self.pool = MagicMock()
            self.pool.acquire = AsyncMock()

        async def get_open_positions(self):
            return []

        async def open_position(self, position_data):
            self.positions_created.append(position_data)
            return len(self.positions_created)

        async def close_position(self, position_id):
            self.positions_closed.append(position_id)

    return MockRepository()


@pytest.mark.asyncio
async def test_sync_prevents_phantom_positions_binance(mock_repository):
    """
    Integration test: Simulate the exact bug scenario that created 130 phantoms

    Scenario:
    - CCXT returns 38 positions with contracts>0 (cached)
    - But positionAmt=0 in raw info (real exchange state)
    - OLD CODE: Would create 38 phantom positions
    - NEW CODE: Should reject all 38 positions
    """

    # Create mock exchange returning stale CCXT data
    mock_exchange = MagicMock()

    # Simulate 38 stale positions (like in wave 17:09)
    stale_positions = []
    symbols = [
        'APEUSDT', 'B2USDT', 'VIRTUALUSDT', 'TRBUSDT', 'PTBUSDT',
        'GALAUSDT', 'AUSDT', 'GMTUSDT', 'SYSUSDT', 'CELRUSDT',
        'ICNTUSDT', 'PORT3USDT', 'ARBUSDT', 'LEVERUSDT', 'HIGHUSDT',
        'SUIUSDT', 'CAKESUSDT', 'COMBOUSDT', 'WLDUSDT', 'POLUSDT',
        'SANDUSDT', 'NEOUSDT', 'ATOMUSDT', 'KAVAUSDT', 'DOGEUSDT',
        'PENDLEUSDT', 'NEARUSDT', 'ZRXUSDT', 'ENSUSDT', 'FTMUSDT',
        'RENDERUSDT', 'ORBSUSDT', 'BLASTUSDT', 'IOTAUSDT', 'SOLUSDT',
        'AVAXUSDT', 'ADAUSDT', 'XLMUSDT'
    ]

    for i, symbol in enumerate(symbols):
        stale_positions.append({
            'symbol': f'{symbol[:-4]}/USDT:USDT',
            'contracts': 200.0,  # CCXT cached value
            'side': 'long',
            'markPrice': 1.0,
            'info': {
                'symbol': symbol,
                'positionAmt': '0',  # ✅ REAL EXCHANGE VALUE: Position closed!
                'avgPrice': '1.0'
                # ❌ NO positionId - stale data!
            }
        })

    mock_exchange.fetch_positions = AsyncMock(return_value=stale_positions)

    # Create synchronizer
    exchanges = {'binance': mock_exchange}
    synchronizer = PositionSynchronizer(mock_repository, exchanges)

    # Run synchronization
    result = await synchronizer.synchronize_exchange('binance', mock_exchange)

    # ✅ ASSERTION: NO positions should be created
    # OLD CODE: Would create 38 phantoms
    # NEW CODE: Should filter all based on positionAmt=0
    assert len(mock_repository.positions_created) == 0, \
        f"Created {len(mock_repository.positions_created)} positions, expected 0"

    assert len(result['added_missing']) == 0, \
        f"Added {len(result['added_missing'])} positions, expected 0"

    # Should have filtered them during fetch
    assert synchronizer.stats['added_missing'] == 0

    print(f"✅ PASS: Prevented {len(stale_positions)} phantom positions")


@pytest.mark.asyncio
async def test_sync_accepts_real_positions_with_order_id(mock_repository):
    """
    Integration test: Real positions with order_id should be accepted

    Scenario:
    - CCXT returns real positions
    - positionAmt > 0 AND positionId exists
    - Should create positions in database
    """

    mock_exchange = MagicMock()

    # Real positions with all required fields
    real_positions = [
        {
            'symbol': 'BTC/USDT:USDT',
            'contracts': 0.5,
            'side': 'long',
            'markPrice': 50000,
            'info': {
                'symbol': 'BTCUSDT',
                'positionAmt': '0.5',  # ✅ Real position
                'positionId': '12345',  # ✅ Has order ID
                'avgPrice': '50000'
            }
        },
        {
            'symbol': 'ETH/USDT:USDT',
            'contracts': 10,
            'side': 'long',
            'markPrice': 3000,
            'info': {
                'symbol': 'ETHUSDT',
                'positionAmt': '10',  # ✅ Real position
                'positionId': '67890',  # ✅ Has order ID
                'avgPrice': '3000'
            }
        }
    ]

    mock_exchange.fetch_positions = AsyncMock(return_value=real_positions)

    # Create synchronizer
    exchanges = {'binance': mock_exchange}
    synchronizer = PositionSynchronizer(mock_repository, exchanges)

    # Run synchronization
    result = await synchronizer.synchronize_exchange('binance', mock_exchange)

    # ✅ ASSERTION: Both positions should be created
    assert len(mock_repository.positions_created) == 2, \
        f"Created {len(mock_repository.positions_created)} positions, expected 2"

    # Verify exchange_order_id was saved
    for pos_data in mock_repository.positions_created:
        assert 'exchange_order_id' in pos_data, "Missing exchange_order_id"
        assert pos_data['exchange_order_id'] in ['12345', '67890']

    print(f"✅ PASS: Accepted {len(real_positions)} real positions")


@pytest.mark.asyncio
async def test_sync_rejects_positions_without_order_id(mock_repository):
    """
    Integration test: Positions without order_id should be rejected

    Scenario:
    - CCXT returns position with positionAmt > 0
    - BUT no positionId in info
    - Should reject (likely stale data)
    """

    mock_exchange = MagicMock()

    # Position with positionAmt but no positionId (suspicious!)
    suspicious_positions = [
        {
            'symbol': 'XRP/USDT:USDT',
            'contracts': 100,
            'side': 'long',
            'markPrice': 0.5,
            'info': {
                'symbol': 'XRPUSDT',
                'positionAmt': '100',  # Has position amount
                'avgPrice': '0.5'
                # ❌ NO positionId - REJECT!
            }
        }
    ]

    mock_exchange.fetch_positions = AsyncMock(return_value=suspicious_positions)

    # Create synchronizer
    exchanges = {'binance': mock_exchange}
    synchronizer = PositionSynchronizer(mock_repository, exchanges)

    # Run synchronization
    result = await synchronizer.synchronize_exchange('binance', mock_exchange)

    # ✅ ASSERTION: Should NOT create position (missing order_id)
    assert len(mock_repository.positions_created) == 0, \
        f"Created {len(mock_repository.positions_created)} positions, expected 0"

    print("✅ PASS: Rejected position without order_id")


@pytest.mark.asyncio
async def test_sync_mixed_real_and_stale_positions(mock_repository):
    """
    Integration test: Mix of real and stale positions

    Scenario:
    - 2 real positions (positionAmt>0, has positionId)
    - 3 stale positions (contracts>0 but positionAmt=0)
    - 1 suspicious position (positionAmt>0 but no positionId)
    - Should only accept 2 real positions
    """

    mock_exchange = MagicMock()

    mixed_positions = [
        # Real position 1
        {
            'symbol': 'BTC/USDT:USDT',
            'contracts': 0.5,
            'side': 'long',
            'markPrice': 50000,
            'info': {
                'positionAmt': '0.5',
                'positionId': '12345',
                'avgPrice': '50000'
            }
        },
        # Stale position 1 (filtered in Phase 1)
        {
            'symbol': 'ETH/USDT:USDT',
            'contracts': 10,
            'info': {
                'positionAmt': '0',  # Filtered by Phase 1
                'avgPrice': '3000'
            }
        },
        # Real position 2
        {
            'symbol': 'SOL/USDT:USDT',
            'contracts': 5,
            'side': 'long',
            'markPrice': 100,
            'info': {
                'positionAmt': '5',
                'positionId': '67890',
                'avgPrice': '100'
            }
        },
        # Stale position 2 (filtered in Phase 1)
        {
            'symbol': 'ADA/USDT:USDT',
            'contracts': 500,
            'info': {
                'positionAmt': '0',  # Filtered by Phase 1
            }
        },
        # Suspicious position (passes Phase 1 but rejected in Phase 3)
        {
            'symbol': 'XRP/USDT:USDT',
            'contracts': 100,
            'side': 'long',
            'markPrice': 0.5,
            'info': {
                'positionAmt': '100',  # Passes Phase 1
                'avgPrice': '0.5'
                # NO positionId - Rejected in Phase 3
            }
        },
        # Stale position 3 (filtered in Phase 1)
        {
            'symbol': 'DOGE/USDT:USDT',
            'contracts': 1000,
            'info': {
                'positionAmt': '0',  # Filtered by Phase 1
            }
        }
    ]

    mock_exchange.fetch_positions = AsyncMock(return_value=mixed_positions)

    # Create synchronizer
    exchanges = {'binance': mock_exchange}
    synchronizer = PositionSynchronizer(mock_repository, exchanges)

    # Run synchronization
    result = await synchronizer.synchronize_exchange('binance', mock_exchange)

    # ✅ ASSERTION: Only 2 real positions should be created
    assert len(mock_repository.positions_created) == 2, \
        f"Created {len(mock_repository.positions_created)} positions, expected 2"

    # Verify the correct symbols were added
    created_symbols = [pos['symbol'] for pos in mock_repository.positions_created]
    assert 'BTCUSDT' in created_symbols
    assert 'SOLUSDT' in created_symbols

    # Verify all have exchange_order_id
    for pos_data in mock_repository.positions_created:
        assert 'exchange_order_id' in pos_data
        assert pos_data['exchange_order_id'] in ['12345', '67890']

    print(f"✅ PASS: Accepted 2 real positions, rejected 4 stale/suspicious")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
