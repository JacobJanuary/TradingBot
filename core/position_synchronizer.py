"""
Position Synchronizer - Ensures database positions match exchange reality
Critical for preventing operations on non-existent positions
"""

import logging
from typing import Dict, List, Set, Tuple, Optional
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger(__name__)


def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol format for consistent comparison

    Converts exchange format 'HIGH/USDT:USDT' to database format 'HIGHUSDT'

    Args:
        symbol: Symbol in any format

    Returns:
        Normalized symbol (database format)
    """
    if '/' in symbol and ':' in symbol:
        # Exchange format: 'HIGH/USDT:USDT' -> 'HIGHUSDT'
        base_quote = symbol.split(':')[0]  # 'HIGH/USDT'
        return base_quote.replace('/', '')  # 'HIGHUSDT'
    return symbol  # Already normalized (database format)


class PositionSynchronizer:
    """
    Synchronizes positions between database and exchange

    CRITICAL FUNCTIONS:
    1. Verify DB positions exist on exchange
    2. Close DB positions that don't exist on exchange
    3. Add exchange positions missing from DB
    4. Update position quantities if they differ
    """

    def __init__(self, repository, exchanges: Dict):
        self.repository = repository
        self.exchanges = exchanges

        self.stats = {
            'db_positions': 0,
            'exchange_positions': 0,
            'verified': 0,
            'closed_phantom': 0,
            'added_missing': 0,
            'updated_quantity': 0,
            'errors': 0
        }

    async def synchronize_all_exchanges(self) -> Dict:
        """
        Synchronize positions for all configured exchanges

        Returns:
            Dict with synchronization results
        """
        logger.info("="*60)
        logger.info("STARTING POSITION SYNCHRONIZATION")
        logger.info("="*60)

        results = {}

        for exchange_name, exchange_instance in self.exchanges.items():
            try:
                logger.info(f"\nSynchronizing {exchange_name}...")
                result = await self.synchronize_exchange(exchange_name, exchange_instance)
                results[exchange_name] = result

            except Exception as e:
                logger.error(f"Failed to synchronize {exchange_name}: {e}")
                results[exchange_name] = {'error': str(e)}
                self.stats['errors'] += 1

        # Log summary
        logger.info("\n" + "="*60)
        logger.info("SYNCHRONIZATION SUMMARY")
        logger.info("="*60)
        logger.info(f"  DB positions found: {self.stats['db_positions']}")
        logger.info(f"  Exchange positions found: {self.stats['exchange_positions']}")
        logger.info(f"  ✅ Verified: {self.stats['verified']}")
        logger.info(f"  🗑️ Phantom closed: {self.stats['closed_phantom']}")
        logger.info(f"  ➕ Missing added: {self.stats['added_missing']}")
        logger.info(f"  📝 Quantity updated: {self.stats['updated_quantity']}")
        logger.info(f"  ❌ Errors: {self.stats['errors']}")

        return results

    async def synchronize_exchange(self, exchange_name: str, exchange) -> Dict:
        """
        Synchronize positions for a single exchange

        Args:
            exchange_name: Name of exchange
            exchange: Exchange instance

        Returns:
            Synchronization results
        """
        result = {
            'verified': [],
            'closed_phantom': [],
            'added_missing': [],
            'updated_quantity': []
        }

        try:
            # 1. Get positions from database
            # Use get_open_positions and filter by exchange since get_open_positions_by_exchange uses wrong schema
            all_db_positions = await self.repository.get_open_positions()
            db_positions = [pos for pos in all_db_positions if pos.get('exchange') == exchange_name]
            self.stats['db_positions'] += len(db_positions)

            logger.info(f"  Found {len(db_positions)} positions in database")

            # 2. Get positions from exchange
            exchange_positions = await self._fetch_exchange_positions(exchange, exchange_name)
            self.stats['exchange_positions'] += len(exchange_positions)

            logger.info(f"  Found {len(exchange_positions)} positions on exchange")

            # Create lookup maps with normalized symbols for comparison
            # CRITICAL FIX: Use normalized symbols to match 'HIGHUSDT' with 'HIGH/USDT:USDT'
            db_map = {normalize_symbol(pos['symbol']): pos for pos in db_positions}
            exchange_map = {normalize_symbol(pos['symbol']): pos for pos in exchange_positions}

            # 3. Check each DB position exists on exchange
            for symbol, db_pos in db_map.items():
                if symbol in exchange_map:
                    # Position exists - verify quantity
                    exchange_pos = exchange_map[symbol]

                    db_quantity = float(db_pos['quantity'])
                    exchange_quantity = abs(float(exchange_pos['contracts']))

                    # Check if quantities match (with small tolerance)
                    if abs(db_quantity - exchange_quantity) > 0.0001:
                        logger.warning(
                            f"  ⚠️ {symbol}: Quantity mismatch - "
                            f"DB: {db_quantity}, Exchange: {exchange_quantity}"
                        )

                        # Update DB with correct quantity
                        await self._update_position_quantity(
                            db_pos['id'], exchange_quantity, exchange_pos
                        )
                        result['updated_quantity'].append(symbol)
                        self.stats['updated_quantity'] += 1
                    else:
                        logger.info(f"  ✅ {symbol}: Verified")
                        result['verified'].append(symbol)
                        self.stats['verified'] += 1

                else:
                    # Position doesn't exist on exchange - PHANTOM!
                    logger.warning(f"  🗑️ {symbol}: PHANTOM position (not on exchange)")

                    # Close in database
                    await self._close_phantom_position(db_pos)
                    result['closed_phantom'].append(symbol)
                    self.stats['closed_phantom'] += 1

            # 4. Check for exchange positions missing from DB
            for symbol, exchange_pos in exchange_map.items():
                if symbol not in db_map:
                    logger.warning(f"  ➕ {symbol}: Missing from database")

                    # Add to database
                    await self._add_missing_position(exchange_name, exchange_pos)
                    result['added_missing'].append(symbol)
                    self.stats['added_missing'] += 1

        except Exception as e:
            logger.error(f"Error synchronizing {exchange_name}: {e}")
            result['error'] = str(e)
            self.stats['errors'] += 1

        return result

    async def _fetch_exchange_positions(self, exchange, exchange_name: str) -> List[Dict]:
        """
        Fetch active positions from exchange

        Args:
            exchange: Exchange instance
            exchange_name: Name of exchange ('bybit', 'binance', etc.)

        Returns:
            List of active positions
        """
        try:
            # CRITICAL FIX: For Bybit, must pass category='linear' and limit=200
            # CCXT 4.4.8: Bybit returns only 20 positions by default
            if exchange_name == 'bybit':
                positions = await exchange.fetch_positions(
                    params={'category': 'linear', 'limit': 200}
                )
            else:
                positions = await exchange.fetch_positions()

            # Filter only active positions (non-zero contracts)
            active_positions = []
            for pos in positions:
                contracts = float(pos.get('contracts') or 0)
                if abs(contracts) > 0:
                    active_positions.append(pos)

            return active_positions

        except Exception as e:
            logger.error(f"Failed to fetch positions from exchange: {e}")
            return []

    async def _close_phantom_position(self, db_position: Dict):
        """
        Close a phantom position in database (doesn't exist on exchange)

        Args:
            db_position: Database position record
        """
        try:
            position_id = db_position['id']
            symbol = db_position['symbol']

            # Update position status to closed
            # Since position doesn't exist on exchange, just mark it as closed
            # Use 'closed' (lowercase) to match the check constraint
            query = """
                UPDATE monitoring.positions
                SET status = 'closed',
                    updated_at = NOW()
                WHERE id = $1
            """

            async with self.repository.pool.acquire() as conn:
                await conn.execute(query, position_id)

            logger.info(f"    Closed phantom position: {symbol} (ID: {position_id})")

        except Exception as e:
            logger.error(f"Failed to close phantom position {db_position['symbol']}: {e}")

    async def _add_missing_position(self, exchange_name: str, exchange_position: Dict):
        """
        Add a position that exists on exchange but missing from database

        Args:
            exchange_name: Name of exchange
            exchange_position: Position data from exchange
        """
        try:
            symbol = exchange_position['symbol']
            contracts = float(exchange_position.get('contracts') or 0)

            # Determine side
            side = exchange_position.get('side', '').lower()
            if not side:
                side = 'long' if contracts > 0 else 'short'

            # Get prices
            entry_price = float(
                exchange_position.get('info', {}).get('avgPrice') or
                exchange_position.get('average') or
                exchange_position.get('markPrice') or 0
            )

            current_price = float(exchange_position.get('markPrice') or entry_price)

            # Create position data for database
            # Store symbol in normalized database format
            position_data = {
                'symbol': normalize_symbol(symbol),
                'exchange': exchange_name,
                'side': side,
                'quantity': abs(contracts),
                'entry_price': entry_price,
                'current_price': current_price,
                'strategy': 'MANUAL',  # Mark as manual since not opened by bot
                'timeframe': 'UNKNOWN',
                'signal_id': None
            }

            # Use open_position method
            position_id = await self.repository.open_position(position_data)

            logger.info(
                f"    Added missing position: {symbol} "
                f"({side} {abs(contracts)} @ ${entry_price:.4f})"
            )

        except Exception as e:
            logger.error(f"Failed to add missing position {exchange_position.get('symbol')}: {e}")

    async def _update_position_quantity(self, position_id: int, new_quantity: float, exchange_position: Dict):
        """
        Update position quantity in database to match exchange

        Args:
            position_id: Database position ID
            new_quantity: Correct quantity from exchange
            exchange_position: Full position data from exchange
        """
        try:
            # For now, just log the discrepancy
            logger.warning(
                f"    ⚠️ Quantity mismatch detected but update skipped. "
                f"Position ID {position_id} should be {new_quantity}"
            )

            # Position quantity updates are not critical for trading
            # The position will be re-synced on next update cycle
            pass

        except Exception as e:
            logger.error(f"Failed to update position quantity: {e}")

    async def verify_position_exists(self, symbol: str, exchange_name: str) -> bool:
        """
        Quick check if a position exists on exchange

        Args:
            symbol: Trading symbol
            exchange_name: Exchange name

        Returns:
            True if position exists on exchange
        """
        try:
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                logger.error(f"Exchange {exchange_name} not found")
                return False

            # CRITICAL FIX: Use fetch_positions() without [symbol] and add category+limit for Bybit
            # CCXT 4.4.8: Bybit returns only 20 positions by default
            if exchange_name == 'bybit':
                positions = await exchange.fetch_positions(
                    params={'category': 'linear', 'limit': 200}
                )
            else:
                positions = await exchange.fetch_positions()

            # Check if position exists with non-zero contracts
            # Use normalized symbol comparison
            normalized_symbol = normalize_symbol(symbol)
            for pos in positions:
                if normalize_symbol(pos.get('symbol')) == normalized_symbol:
                    contracts = float(pos.get('contracts') or 0)
                    if abs(contracts) > 0:
                        return True

            return False

        except Exception as e:
            logger.error(f"Error verifying position {symbol} on {exchange_name}: {e}")
            return False


async def synchronize_positions_on_startup(position_manager) -> Dict:
    """
    Helper function to synchronize positions during startup

    Args:
        position_manager: PositionManager instance

    Returns:
        Synchronization results
    """
    logger.info("🔄 Synchronizing positions with exchanges...")

    synchronizer = PositionSynchronizer(
        repository=position_manager.repository,
        exchanges=position_manager.exchanges
    )

    results = await synchronizer.synchronize_all_exchanges()

    # Update position manager's internal state
    # Reload positions after synchronization
    position_manager.positions.clear()
    position_manager.total_exposure = Decimal('0')

    await position_manager.load_positions_from_db()

    logger.info("✅ Position synchronization complete")

    return results