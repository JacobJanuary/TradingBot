import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from config.settings import TradingConfig
from database.repository import Repository as TradingRepository
from core.position_manager import PositionManager, PositionRequest
from websocket.event_router import EventRouter

logger = logging.getLogger(__name__)


class SignalProcessor:
    """
    Process trading signals from database
    Handles signal filtering, validation, and execution
    """

    def __init__(self,
                 config: TradingConfig,
                 repository: TradingRepository,
                 position_manager: PositionManager,
                 event_router: EventRouter):
        """Initialize signal processor"""
        self.config = config
        self.repository = repository
        self.position_manager = position_manager
        self.event_router = event_router

        # Processing state
        self.processing_signals = set()
        self.failed_signals = set()
        self.stop_list = set()  # Symbols to skip

        # Timing
        self.check_interval = 30  # seconds
        self.signal_time_window = config.signal_time_window_minutes
        self.max_trades_per_window = config.max_trades_per_15min

        # Statistics
        self.stats = {
            'signals_received': 0,
            'signals_processed': 0,
            'signals_executed': 0,
            'signals_rejected': 0,
            'signals_failed': 0,
            'last_check': None
        }

        # Running state
        self.running = False
        self._process_task = None

        logger.info("SignalProcessor initialized")

    def add_to_stop_list(self, symbols: List[str]):
        """Add symbols to stop list"""
        self.stop_list.update(symbols)
        logger.info(f"Added {len(symbols)} symbols to stop list")

    async def start(self):
        """Start signal processing loop"""
        if self.running:
            logger.warning("SignalProcessor already running")
            return

        self.running = True
        self._process_task = asyncio.create_task(self._process_loop())
        logger.info("SignalProcessor started")

    async def stop(self):
        """Stop signal processing"""
        self.running = False

        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass

        logger.info("SignalProcessor stopped")

    async def _process_loop(self):
        """Main processing loop"""
        logger.info("Signal processing loop started")

        while self.running:
            try:
                # Fetch new signals
                signals = await self._fetch_signals()

                if signals:
                    logger.info(f"Processing {len(signals)} new signals")

                    # Process each signal
                    for signal in signals:
                        if not self.running:
                            break

                        await self._process_signal(signal)

                        # Delay between signals
                        if len(signals) > 1:
                            await asyncio.sleep(1)

                # Update stats
                self.stats['last_check'] = datetime.now()

                # Wait before next check
                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Error in signal processing loop: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def _fetch_signals(self) -> List[Dict]:
        """Fetch new signals from database"""
        try:
            signals = await self.repository.get_unprocessed_signals(
                min_score_week=float(self.config.min_score_week),
                min_score_month=float(self.config.min_score_month),
                time_window_minutes=self.signal_time_window,
                limit=self.max_trades_per_window
            )

            self.stats['signals_received'] += len(signals)

            # Filter out processed and failed signals
            filtered_signals = []
            for signal in signals:
                signal_id = signal['id']

                if signal_id in self.processing_signals:
                    continue
                if signal_id in self.failed_signals:
                    continue
                if signal['pair_symbol'] in self.stop_list:
                    logger.debug(f"Signal {signal_id} for {signal['pair_symbol']} in stop list")
                    continue

                filtered_signals.append(signal)

            return filtered_signals

        except Exception as e:
            logger.error(f"Error fetching signals: {e}")
            return []

    async def _process_signal(self, signal: Dict):
        """Process individual signal"""
        signal_id = signal['id']
        symbol = signal['pair_symbol']
        exchange = signal['exchange_name'].lower()

        # Mark as processing
        self.processing_signals.add(signal_id)

        try:
            logger.info(
                f"Processing signal #{signal_id}: {symbol} on {exchange} "
                f"(score_week: {signal['score_week']:.1f}, "
                f"score_month: {signal['score_month']:.1f})"
            )

            # Emit signal received event
            await self.event_router.emit('signal.received', {
                'signal_id': signal_id,
                'symbol': symbol,
                'exchange': exchange,
                'action': signal['recommended_action']
            })

            # Validate signal
            if not await self._validate_signal(signal):
                self.stats['signals_rejected'] += 1
                await self.repository.mark_signal_processed(signal_id)
                return

            # Get current price (for validation)
            exchange_manager = self.position_manager.exchanges.get(exchange)
            if not exchange_manager:
                logger.error(f"Exchange {exchange} not available")
                self.failed_signals.add(signal_id)
                self.stats['signals_failed'] += 1
                return

            ticker = await exchange_manager.fetch_ticker(symbol)
            if not ticker:
                logger.error(f"Cannot get ticker for {symbol}")
                self.failed_signals.add(signal_id)
                self.stats['signals_failed'] += 1
                return

            current_price = ticker.get('last', 0)
            if current_price <= 0:
                logger.error(f"Invalid price for {symbol}: {current_price}")
                self.failed_signals.add(signal_id)
                self.stats['signals_failed'] += 1
                return

            # Create position request
            request = PositionRequest(
                signal_id=signal_id,
                symbol=symbol,
                exchange=exchange,
                side=signal['recommended_action'],  # 'BUY' or 'SELL'
                entry_price=current_price
            )

            # Execute position opening
            position = await self.position_manager.open_position(request)

            if position:
                logger.info(f"✅ Signal #{signal_id} executed successfully")
                self.stats['signals_executed'] += 1

                # Emit position opened event
                await self.event_router.emit('position.opened', {
                    'signal_id': signal_id,
                    'symbol': symbol,
                    'exchange': exchange,
                    'side': position.side,
                    'quantity': position.quantity,
                    'entry_price': position.entry_price
                })
            else:
                logger.warning(f"Failed to execute signal #{signal_id}")
                self.failed_signals.add(signal_id)
                self.stats['signals_failed'] += 1

            # Mark signal as processed
            await self.repository.mark_signal_processed(signal_id)
            self.stats['signals_processed'] += 1

        except Exception as e:
            logger.error(f"Error processing signal {signal_id}: {e}", exc_info=True)
            self.failed_signals.add(signal_id)
            self.stats['signals_failed'] += 1

            # Mark as processed to avoid retry
            try:
                await self.repository.mark_signal_processed(signal_id)
            except:
                pass

        finally:
            self.processing_signals.discard(signal_id)

    async def _validate_signal(self, signal: Dict) -> bool:
        """
        Validate signal before execution

        Checks:
        - Signal age
        - Score thresholds
        - Symbol validity
        - Exchange availability
        """

        # Check signal age
        signal_time = signal.get('created_at')
        if isinstance(signal_time, str):
            signal_time = datetime.fromisoformat(signal_time)

        age_minutes = (datetime.now() - signal_time).total_seconds() / 60

        if age_minutes > self.signal_time_window:
            logger.warning(
                f"Signal #{signal['id']} too old: {age_minutes:.1f} minutes"
            )
            return False

        # Validate scores
        score_week = signal.get('score_week', 0)
        score_month = signal.get('score_month', 0)

        if score_week < float(self.config.min_score_week):
            logger.warning(
                f"Signal #{signal['id']} score_week {score_week} "
                f"below threshold {self.config.min_score_week}"
            )
            return False

        if score_month < float(self.config.min_score_month):
            logger.warning(
                f"Signal #{signal['id']} score_month {score_month} "
                f"below threshold {self.config.min_score_month}"
            )
            return False

        # Validate action
        action = signal.get('recommended_action')
        if action not in ['BUY', 'SELL']:
            logger.warning(f"Invalid action for signal #{signal['id']}: {action}")
            return False

        return True

    def get_stats(self) -> Dict:
        """Get processor statistics"""
        return {
            **self.stats,
            'processing_count': len(self.processing_signals),
            'failed_count': len(self.failed_signals),
            'stop_list_size': len(self.stop_list)
        }