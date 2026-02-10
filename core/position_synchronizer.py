"""
Position Synchronizer - Ensures database positions match exchange reality
Critical for preventing operations on non-existent positions
"""

import logging
from typing import Dict, List, Set, Tuple, Optional
from datetime import datetime, timezone
from decimal import Decimal
from core.event_logger import get_event_logger, EventType

logger = logging.getLogger(__name__)


from utils.symbol_helpers import normalize_symbol


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

        # Log synchronization start
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.SYNCHRONIZATION_STARTED,
                {
                    'exchanges': list(self.exchanges.keys()),
                    'exchange_count': len(self.exchanges)
                },
                severity='INFO'
            )

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

        # Log synchronization completion
        event_logger = get_event_logger()
        if event_logger:
            await event_logger.log_event(
                EventType.SYNCHRONIZATION_COMPLETED,
                {
                    'db_positions': self.stats['db_positions'],
                    'exchange_positions': self.stats['exchange_positions'],
                    'verified': self.stats['verified'],
                    'closed_phantom': self.stats['closed_phantom'],
                    'added_missing': self.stats['added_missing'],
                    'updated_quantity': self.stats['updated_quantity'],
                    'errors': self.stats['errors']
                },
                severity='INFO'
            )

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

                        # Log quantity mismatch detection
                        event_logger = get_event_logger()
                        if event_logger:
                            await event_logger.log_event(
                                EventType.QUANTITY_MISMATCH_DETECTED,
                                {
                                    'symbol': symbol,
                                    'exchange': exchange_name,
                                    'db_quantity': db_quantity,
                                    'exchange_quantity': exchange_quantity,
                                    'difference': abs(db_quantity - exchange_quantity)
                                },
                                symbol=symbol,
                                exchange=exchange_name,
                                severity='WARNING'
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

                        # Log position verification
                        event_logger = get_event_logger()
                        if event_logger:
                            await event_logger.log_event(
                                EventType.POSITION_VERIFIED,
                                {
                                    'symbol': symbol,
                                    'exchange': exchange_name,
                                    'db_quantity': db_quantity,
                                    'exchange_quantity': exchange_quantity
                                },
                                symbol=symbol,
                                exchange=exchange_name,
                                severity='INFO'
                            )

                else:
                    # Position doesn't exist on exchange - PHANTOM!
                    logger.warning(f"  🗑️ {symbol}: PHANTOM position (not on exchange)")

                    # Log phantom position detection
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.PHANTOM_POSITION_DETECTED,
                            {
                                'symbol': symbol,
                                'exchange': exchange_name,
                                'position_id': db_pos['id'],
                                'db_quantity': float(db_pos['quantity']),
                                'entry_price': float(db_pos.get('entry_price', 0))
                            },
                            symbol=symbol,
                            exchange=exchange_name,
                            severity='WARNING'
                        )

                    # Close in database
                    await self._close_phantom_position(db_pos)
                    result['closed_phantom'].append(symbol)
                    self.stats['closed_phantom'] += 1

            # 4. Check for exchange positions missing from DB
            for symbol, exchange_pos in exchange_map.items():
                if symbol not in db_map:
                    logger.warning(f"  ➕ {symbol}: Missing from database")

                    # Add to database (returns True if actually created)
                    created = await self._add_missing_position(exchange_name, exchange_pos)
                    if created:
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
            exchange_name: Name of exchange ('binance', etc.)

        Returns:
            List of active positions (validated and non-zero)
        """
        try:
            positions = await exchange.fetch_positions()

            # ✅ PHASE 1: STRICTER FILTERING - Check raw exchange data
            active_positions = []
            filtered_count = 0

            for pos in positions:
                contracts = float(pos.get('contracts') or 0)

                # Basic check: non-zero contracts
                if abs(contracts) <= 0:
                    continue

                # ✅ CRITICAL: Validate against raw exchange data
                info = pos.get('info', {})

                # Binance: Check positionAmt in raw response
                if exchange_name == 'binance':
                    position_amt = float(info.get('positionAmt', 0))
                    if abs(position_amt) <= 0:
                        filtered_count += 1
                        logger.debug(
                            f"    Filtered {pos.get('symbol')}: "
                            f"contracts={contracts} but positionAmt={position_amt}"
                        )
                        continue

                # Bybit: Check size in raw response
                elif exchange_name == 'bybit':
                    size_val = float(info.get('size', 0))
                    if abs(size_val) <= 0:
                        filtered_count += 1
                        logger.debug(
                            f"    Filtered {pos.get('symbol')}: "
                            f"contracts={contracts} but size={size_val}"
                        )
                        continue

                # ✅ Position passed all filters
                active_positions.append(pos)

            if filtered_count > 0:
                logger.info(
                    f"  🔍 Filtered {filtered_count} stale/cached positions "
                    f"({len(active_positions)} real)"
                )

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
            exchange = db_position.get('exchange', 'unknown')

            # Close phantom position properly using repository method
            # This ensures all fields (closed_at, exit_reason, pnl) are set correctly
            await self.repository.close_position(
                position_id=position_id,
                close_price=db_position.get('current_price', 0),
                pnl=0,
                pnl_percentage=0,
                reason='PHANTOM_ON_SYNC'
            )

            logger.info(f"    Closed phantom position: {symbol} (ID: {position_id})")

            # Log phantom position closure
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.PHANTOM_POSITION_CLOSED,
                    {
                        'symbol': symbol,
                        'exchange': exchange,
                        'position_id': position_id,
                        'reason': 'not_on_exchange'
                    },
                    symbol=symbol,
                    exchange=exchange,
                    severity='WARNING'
                )

        except Exception as e:
            logger.error(f"Failed to close phantom position {db_position['symbol']}: {e}")

    async def _add_missing_position(self, exchange_name: str, exchange_position: Dict) -> bool:
        """
        Add a position that exists on exchange but missing from database

        Args:
            exchange_name: Name of exchange
            exchange_position: Position data from exchange

        Returns:
            True if position was created, False if rejected
        """
        try:
            symbol = exchange_position['symbol']
            contracts = float(exchange_position.get('contracts') or 0)
            info = exchange_position.get('info', {})

            # ✅ PHASE 2: Extract exchange_order_id from raw response
            exchange_order_id = None

            if exchange_name == 'binance':
                # Binance uses 'positionId' in info
                exchange_order_id = info.get('positionId') or info.get('orderId')
            else:
                # Generic fallback
                exchange_order_id = info.get('positionId') or info.get('orderId')

            # ✅ PHASE 3: VALIDATION - Generate synthetic ID if no exchange_order_id
            if not exchange_order_id:
                import time
                exchange_order_id = f"MANUAL_{exchange_name.upper()}_{symbol}_{int(time.time())}"

                logger.warning(
                    f"    ⚠️  {symbol}: No exchange_order_id found. "
                    f"Generated synthetic ID: {exchange_order_id}"
                )
                logger.warning(
                    f"    This may be a manually opened position or API data issue."
                )
                logger.warning(
                    f"    Position WILL BE ADDED to DB for safety (info keys: {list(info.keys())})"
                )

                # Log missing order_id but continue processing
                event_logger = get_event_logger()
                if event_logger:
                    await event_logger.log_event(
                        EventType.MISSING_POSITION_ADDED_WITH_SYNTHETIC_ID,
                        {
                            'symbol': symbol,
                            'exchange': exchange_name,
                            'synthetic_order_id': exchange_order_id,
                            'reason': 'no_exchange_order_id',
                            'contracts': abs(contracts),
                            'info_keys': list(info.keys())
                        },
                        symbol=symbol,
                        exchange=exchange_name,
                        severity='WARNING'
                    )

            # Determine side
            side = exchange_position.get('side', '').lower()
            if not side:
                side = 'long' if contracts > 0 else 'short'

            # Get prices
            entry_price = float(
                info.get('avgPrice') or
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
                'exchange_order_id': exchange_order_id,
            }

            # Use open_position method
            position_id = await self.repository.open_position(position_data)

            logger.info(
                f"    ✅ Added missing position: {symbol} "
                f"({side} {abs(contracts)} @ ${entry_price:.4f}, order_id={exchange_order_id})"
            )

            # Log missing position added
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.MISSING_POSITION_ADDED,
                    {
                        'symbol': symbol,
                        'exchange': exchange_name,
                        'position_id': position_id,
                        'side': side,
                        'quantity': abs(contracts),
                        'entry_price': entry_price,
                        'exchange_order_id': str(exchange_order_id)
                    },
                    symbol=symbol,
                    exchange=exchange_name,
                    severity='INFO'
                )

            return True

        except Exception as e:
            logger.error(f"Failed to add missing position {exchange_position.get('symbol')}: {e}")
            return False

    async def _update_position_quantity(self, position_id: int, new_quantity: float, exchange_position: Dict):
        """
        Update position quantity in database to match exchange

        Args:
            position_id: Database position ID
            new_quantity: Correct quantity from exchange
            exchange_position: Full position data from exchange
        """
        try:
            # Extract additional fields from exchange position
            current_price = exchange_position.get('markPrice')
            unrealized_pnl = exchange_position.get('unrealizedPnl', 0)
            symbol = exchange_position.get('symbol', 'unknown')

            logger.info(
                f"    📊 Updating quantity for position {position_id}: {new_quantity}"
            )

            await self.repository.update_position(
                position_id=position_id,
                quantity=new_quantity,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl
            )

            # Log quantity update
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.QUANTITY_UPDATED,
                    {
                        'position_id': position_id,
                        'symbol': symbol,
                        'new_quantity': new_quantity,
                        'current_price': float(current_price) if current_price else None,
                        'unrealized_pnl': float(unrealized_pnl)
                    },
                    symbol=symbol,
                    severity='INFO'
                )

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

            # Fetch positions
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