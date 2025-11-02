"""
Main Trading Bot Application
Entry point and orchestration
"""
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import signal
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Optional
import argparse

from config.settings import config as settings
from utils.single_instance import SingleInstance, check_running, kill_running
from core.exchange_manager import ExchangeManager
from core.position_manager import PositionManager
from core.signal_processor_websocket import WebSocketSignalProcessor
from database.repository import Repository as TradingRepository
from websocket.binance_stream import BinancePrivateStream
from websocket.event_router import EventRouter
from protection.trailing_stop import SmartTrailingStopManager, TrailingStopConfig
from core.aged_position_manager import AgedPositionManager
from core.position_manager_unified_patch import start_periodic_aged_scan, start_websocket_health_monitor
from monitoring.health_check import HealthChecker, HealthStatus
from monitoring.performance import PerformanceTracker

# Setup logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('logs/trading_bot.log', maxBytes=100*1024*1024, backupCount=10),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """
    Main trading bot application
    Coordinates all components
    """

    def __init__(self, args: argparse.Namespace):
        """Initialize trading bot"""
        self.args = args
        self.mode = args.mode  # 'production', 'shadow', 'backtest'

        # Core components
        self.exchanges: Dict[str, ExchangeManager] = {}
        self.websockets: Dict[str, BinancePrivateStream] = {}
        self.repository: Optional[TradingRepository] = None
        self.event_router = EventRouter()
        self.position_manager: Optional[PositionManager] = None
        self.aged_position_manager: Optional[AgedPositionManager] = None
        self.signal_processor: Optional[WebSocketSignalProcessor] = None

        # Monitoring - will be initialized after repository is ready
        self.health_monitor = None
        self.performance_tracker = None

        # Control
        self.running = False
        self.shutdown_event = asyncio.Event()

        logger.info(f"Trading Bot initializing in {self.mode} mode")

    async def initialize(self):
        """Initialize all components"""
        try:
            logger.info("=" * 80)
            logger.info("TRADING BOT INITIALIZATION")
            logger.info("=" * 80)

            # Validate configuration
            if not settings.validate():
                raise Exception("Configuration validation failed")

            # Initialize database
            logger.info("Initializing database...")
            db_config = {
                'host': settings.database.host,
                'port': settings.database.port,
                'database': settings.database.database,
                'user': settings.database.user,
                'password': settings.database.password,
                'pool_size': settings.database.pool_size,
                'max_overflow': settings.database.max_overflow
            }
            self.repository = TradingRepository(db_config)
            await self.repository.initialize()

            # CRITICAL: Verify pool initialized successfully
            if not self.repository.pool:
                raise RuntimeError("Repository pool initialization failed!")
            logger.info(f"✅ Repository pool initialized: {type(self.repository.pool)}")

            # Initialize health checker and performance tracker with repository
            self.health_monitor = HealthChecker(
                self.repository,
                {'check_interval': 10},
                signal_processor=None  # Will be set after signal_processor initialization
            )

            # CRITICAL FIX: Start health monitoring
            await self.health_monitor.start()
            logger.info("✅ Health monitoring started")

            self.performance_tracker = PerformanceTracker(
                self.repository,
                {'min_trades_for_stats': 20}
            )

            # Initialize exchanges
            logger.info("Initializing exchanges...")
            for name, config in settings.exchanges.items():
                # Skip disabled exchanges
                if not config.enabled:
                    logger.info(f"Skipping disabled exchange: {name}")
                    continue
                    
                exchange = ExchangeManager(name, config.__dict__, repository=self.repository)
                try:
                    await exchange.initialize()
                    self.exchanges[name] = exchange
                    logger.info(f"✅ {name.capitalize()} exchange ready")
                except Exception as e:
                    logger.error(f"Failed to initialize {name}: {e}")
                    # Cleanup on failure
                    await exchange.close()
                    if self.mode == 'production':
                        raise
                    # In non-production, continue with other exchanges

            if not self.exchanges:
                raise Exception("No exchanges available")

            # Initialize WebSocket streams
            logger.info("Initializing WebSocket streams...")
            for name, config in settings.exchanges.items():
                # Skip disabled exchanges
                if not config.enabled:
                    continue
                    
                if name == 'binance':
                    # Check if we're on testnet
                    is_testnet = config.testnet
                    
                    if is_testnet:
                        # Use adaptive stream for testnet
                        logger.info("🔧 Using AdaptiveStream for testnet")
                        from websocket.adaptive_stream import AdaptiveBinanceStream
                        
                        # Get exchange client
                        exchange = self.exchanges.get(name)
                        if exchange:
                            stream = AdaptiveBinanceStream(exchange, is_testnet=True)
                            
                            # Set up callbacks to integrate with existing event system
                            async def on_price_update(symbol, price):
                                await self._handle_stream_event('price_update', {
                                    'symbol': symbol,
                                    'price': price
                                })

                            async def on_position_update(positions):
                                # CRITICAL FIX: Event name must match subscription in position_manager (position.update)
                                # positions is dict {symbol: position_data}, emit event for each position
                                if positions:
                                    logger.info(f"📊 REST polling: received {len(positions)} position updates with mark prices")
                                for symbol, pos_data in positions.items():
                                    await self._handle_stream_event('position.update', pos_data)
                            
                            stream.set_callback('price_update', on_price_update)
                            stream.set_callback('position_update', on_position_update)
                            
                            # Start in background
                            asyncio.create_task(stream.start())
                            self.websockets[name] = stream
                            logger.info(f"✅ {name.capitalize()} AdaptiveStream ready (testnet)")
                    else:
                        # Use Hybrid WebSocket for Binance mainnet
                        logger.info("🚀 Using Hybrid WebSocket for Binance mainnet")
                        from websocket.binance_hybrid_stream import BinanceHybridStream

                        # Get API credentials
                        api_key = os.getenv('BINANCE_API_KEY')
                        api_secret = os.getenv('BINANCE_API_SECRET')

                        if api_key and api_secret:
                            try:
                                hybrid_stream = BinanceHybridStream(
                                    api_key=api_key,
                                    api_secret=api_secret,
                                    event_handler=self._handle_stream_event,
                                    testnet=False
                                )
                                await hybrid_stream.start()
                                self.websockets[f'{name}_hybrid'] = hybrid_stream
                                logger.info(f"✅ {name.capitalize()} Hybrid WebSocket ready (mainnet)")
                                logger.info(f"   → User WS: Position lifecycle (ACCOUNT_UPDATE)")
                                logger.info(f"   → Mark WS: Price updates (1-3s)")
                            except Exception as e:
                                logger.error(f"Failed to start Binance hybrid stream: {e}")
                                raise
                        else:
                            logger.error(f"❌ Binance mainnet requires API credentials")
                            raise ValueError("Binance API credentials required for mainnet")

                elif name == 'bybit':
                    # Check if we're on testnet
                    is_testnet = config.testnet

                    if is_testnet:
                        # Use adaptive stream for testnet (REST polling like Binance)
                        logger.info("🔧 Using AdaptiveStream for Bybit testnet")
                        from websocket.adaptive_stream import AdaptiveBybitStream

                        # Get exchange client
                        exchange = self.exchanges.get(name)
                        if exchange:
                            stream = AdaptiveBybitStream(exchange, is_testnet=True)

                            # Set up callbacks to integrate with existing event system
                            async def on_position_update(positions):
                                # CRITICAL FIX: Event name must match subscription in position_manager (position.update)
                                # positions is dict {symbol: position_data}, emit event for each position
                                if positions:
                                    logger.info(f"📊 REST polling (Bybit): received {len(positions)} position updates with mark prices")
                                for symbol, pos_data in positions.items():
                                    await self._handle_stream_event('position.update', pos_data)

                            stream.set_callback('position_update', on_position_update)

                            # Start in background
                            asyncio.create_task(stream.start())
                            self.websockets[name] = stream
                            logger.info(f"✅ {name.capitalize()} AdaptiveStream ready (testnet)")
                    else:
                        # Use Hybrid WebSocket for mainnet
                        # Combines private (position) + public (tickers) streams
                        logger.info("🚀 Using Hybrid WebSocket for Bybit mainnet")
                        from websocket.bybit_hybrid_stream import BybitHybridStream

                        # Get API credentials
                        api_key = os.getenv('BYBIT_API_KEY')
                        api_secret = os.getenv('BYBIT_API_SECRET')

                        if api_key and api_secret:
                            try:
                                hybrid_stream = BybitHybridStream(
                                    api_key=api_key,
                                    api_secret=api_secret,
                                    event_handler=self._handle_stream_event,
                                    testnet=False
                                )
                                await hybrid_stream.start()
                                self.websockets[f'{name}_hybrid'] = hybrid_stream
                                logger.info(f"✅ {name.capitalize()} Hybrid WebSocket ready (mainnet)")
                                logger.info(f"   → Private WS: Position lifecycle")
                                logger.info(f"   → Public WS: Mark price updates (100ms)")
                            except Exception as e:
                                logger.error(f"Failed to start Bybit hybrid stream: {e}")
                                raise
                        else:
                            logger.error(f"❌ Bybit mainnet requires API credentials")
                            raise ValueError("Bybit API credentials required for mainnet")

            # Initialize position manager
            logger.info("Initializing position manager...")
            self.position_manager = PositionManager(
                settings.trading,
                self.exchanges,
                self.repository,
                self.event_router
            )

            # Apply critical fixes to PositionManager
            try:
                from core.position_manager_integration import apply_critical_fixes, check_fixes_applied
                await apply_critical_fixes(self.position_manager)

                # Apply validation fixes for 8/8 compliance
                from core.validation_fixes import add_validation_markers
                add_validation_markers(self.position_manager)

                # Verify fixes are applied
                fixes_status = check_fixes_applied(self.position_manager)
                logger.info(f"Critical fixes status: {fixes_status}")

                if not all(fixes_status.values()):
                    logger.warning("⚠️ Some fixes may not be fully applied")
            except Exception as e:
                logger.error(f"Failed to apply critical fixes: {e}")

            # Load existing positions from database
            logger.info("Loading positions from database...")
            await self.position_manager.load_positions_from_db()

            # CRITICAL FIX: Sync positions with Binance Hybrid WebSocket
            # User WS may not send position snapshot on startup,
            # so we need to explicitly subscribe to mark prices for existing positions
            binance_ws = self.websockets.get('binance_hybrid')
            if binance_ws:
                # Get active Binance positions (PositionState objects)
                binance_position_states = [
                    p for p in self.position_manager.positions.values()
                    if p.exchange == 'binance'
                ]

                if binance_position_states:
                    # Convert PositionState objects to dicts for sync_positions()
                    binance_positions = [
                        {
                            'symbol': p.symbol,
                            'side': p.side,
                            'quantity': p.quantity,
                            'entry_price': p.entry_price,
                            'current_price': p.current_price
                        }
                        for p in binance_position_states
                    ]

                    logger.info(f"🔄 Syncing {len(binance_positions)} Binance positions with WebSocket...")
                    try:
                        await binance_ws.sync_positions(binance_positions)
                        logger.info(f"✅ Binance WebSocket synced with {len(binance_positions)} positions")
                    except Exception as e:
                        logger.error(f"Failed to sync Binance positions: {e}")
                else:
                    logger.info("No active Binance positions to sync")

            # CRITICAL FIX: Sync positions with Bybit Hybrid WebSocket
            # Private WS may not send position snapshot on startup,
            # so we need to explicitly subscribe to tickers for existing positions
            bybit_ws = self.websockets.get('bybit_hybrid')
            if bybit_ws:
                # Get active Bybit positions (PositionState objects)
                bybit_position_states = [
                    p for p in self.position_manager.positions.values()
                    if p.exchange == 'bybit'
                ]

                if bybit_position_states:
                    # Convert PositionState objects to dicts for sync_positions()
                    bybit_positions = [
                        {
                            'symbol': p.symbol,
                            'side': p.side,
                            'quantity': p.quantity,
                            'entry_price': p.entry_price,
                            'current_price': p.current_price
                        }
                        for p in bybit_position_states
                    ]

                    logger.info(f"🔄 Syncing {len(bybit_positions)} Bybit positions with WebSocket...")
                    try:
                        await bybit_ws.sync_positions(bybit_positions)
                        logger.info(f"✅ Bybit WebSocket synced with {len(bybit_positions)} positions")
                    except Exception as e:
                        logger.error(f"Failed to sync Bybit positions: {e}")
                else:
                    logger.info("No active Bybit positions to sync")

            # Initialize aged position manager (only if unified protection is disabled)
            use_unified_protection = os.getenv('USE_UNIFIED_PROTECTION', 'false').lower() == 'true'
            if not use_unified_protection:
                logger.info("Initializing aged position manager (legacy)...")
                self.aged_position_manager = AgedPositionManager(
                    settings.trading,
                    self.position_manager,
                    self.exchanges  # Pass exchanges dict directly
                )
                logger.info("✅ Aged position manager ready (legacy)")
            else:
                logger.info("⚡ Aged position manager disabled - using Unified Protection V2")
                self.aged_position_manager = None

                # CRITICAL FIX: Recover aged positions state from database
                if self.position_manager.unified_protection:
                    from core.position_manager_unified_patch import (
                        recover_aged_positions_state,
                        start_periodic_aged_scan,
                        start_websocket_health_monitor
                    )

                    # Recover existing aged positions from database
                    recovered = await recover_aged_positions_state(self.position_manager.unified_protection)
                    logger.info(f"🔄 Aged positions recovery: {recovered} position(s) restored from database")

            # Initialize WebSocket signal processor
            logger.info("Initializing WebSocket signal processor...")
            self.signal_processor = WebSocketSignalProcessor(
                config=settings.trading,
                position_manager=self.position_manager,
                repository=self.repository,
                event_router=self.event_router
            )
            logger.info("✅ WebSocket signal processor initialized")

            # Set signal processor reference in health monitor
            if self.health_monitor:
                self.health_monitor.set_signal_processor(self.signal_processor)

            # Stop-list symbols are now loaded from configuration (.env file)
            # via SymbolFilter in signal_processor
            logger.info("Symbol filtering configured from .env file")

            # Register event handlers
            self._register_event_handlers()

            # Health monitor and performance tracker are already initialized

            logger.info("=" * 80)
            logger.info("✅ INITIALIZATION COMPLETE")
            logger.info("=" * 80)

            # Log initial state
            await self._log_initial_state()

        except Exception as e:
            logger.critical(f"Initialization failed: {e}", exc_info=True)
            # Cleanup any initialized resources before re-raising
            await self.cleanup()
            raise

    def _register_event_handlers(self):
        """Register application event handlers"""

        @self.event_router.on('error')
        async def handle_error(data: Dict):
            logger.error(f"System error: {data}")
            self.health_monitor.record_error(data)

        @self.event_router.on('position.opened')
        async def handle_position_opened(data: Dict):
            logger.info(f"📈 Position opened: {data['symbol']} {data['side']}")
            await self.performance_tracker.record_trade(data)

        @self.event_router.on('position.closed')
        async def handle_position_closed(data: Dict):
            pnl = data.get('realized_pnl', 0)
            emoji = "✅" if pnl > 0 else "❌"
            logger.info(f"{emoji} Position closed: {data['symbol']} PnL: ${pnl:.2f}")
            await self.performance_tracker.record_trade_close(data)

        @self.event_router.on('stop_loss.triggered')
        async def handle_stop_loss(data: Dict):
            logger.warning(f"⚠️ Stop loss triggered: {data['symbol']}")

        @self.event_router.on('margin_call')
        async def handle_margin_call(data: Dict):
            logger.critical("🚨 MARGIN CALL RECEIVED!")
            # Emergency actions
            if self.mode == 'production':
                await self._emergency_close_all()

    async def _handle_stream_event(self, event: str, data: Dict):
        """Handle WebSocket stream events"""
        await self.event_router.emit(event, data, source='websocket')

    async def _log_initial_state(self):
        """Log initial system state"""
        for name, exchange in self.exchanges.items():
            balance = await exchange.fetch_balance()
            # Для Bybit unified account баланс может быть в info
            if name == 'bybit' and 'info' in balance:
                # Попробуем получить баланс из info для unified account
                try:
                    info = balance['info'].get('result', {}).get('list', [{}])[0]
                    usdt_balance = float(info.get('totalAvailableBalance', 0))
                except:
                    usdt_balance = balance.get('USDT', {}).get('free', 0) or 0
            else:
                usdt_balance = balance.get('USDT', {}).get('free', 0) or 0
            logger.info(f"{name.capitalize()} balance: ${usdt_balance:.2f} USDT")

            positions = await exchange.fetch_positions()
            if positions:
                logger.info(f"{name.capitalize()} has {len(positions)} open positions")
                for pos in positions:
                    logger.info(
                        f"  - {pos['symbol']}: {pos['side']} "
                        f"{pos['contracts']} @ {pos.get('entryPrice', 0)}"
                    )

    async def start(self):
        """Start trading bot"""
        logger.info("🚀 Starting Trading Bot...")

        # Initialize EventLogger for audit trail
        try:
            from core.event_logger import EventLogger, EventType, set_event_logger
            event_logger = EventLogger(self.repository.pool)
            await event_logger.initialize()
            set_event_logger(event_logger)

            # Log bot startup
            await event_logger.log_event(
                EventType.BOT_STARTED,
                {
                    'mode': self.mode,
                    'exchange': 'both',
                    'version': '2.0'
                },
                severity='INFO'
            )
            logger.info("✅ EventLogger initialized - All operations will be logged")
        except Exception as e:
            logger.warning(f"EventLogger initialization failed: {e}")

        # ⚠️ CRITICAL: Recovery for incomplete positions
        try:
            logger.info("🔍 Running position recovery check...")
            from core.atomic_position_manager import AtomicPositionManager
            from core.stop_loss_manager import StopLossManager

            # Create atomic manager for recovery
            sl_manager = StopLossManager(None, 'recovery')
            atomic_manager = AtomicPositionManager(
                repository=self.repository,
                exchange_manager=self.exchanges,
                stop_loss_manager=sl_manager,
                position_manager=None,
                config=settings.trading  # RESTORED 2025-10-25: pass config for leverage
            )

            await atomic_manager.recover_incomplete_positions()
            logger.info("✅ Position recovery check completed")

        except ImportError:
            logger.warning("AtomicPositionManager not available for recovery")
        except Exception as e:
            logger.error(f"Position recovery failed: {e}")

        self.running = True

        try:
            # Start WebSocket streams
            stream_tasks = []
            for name, stream in self.websockets.items():
                # Check if stream has connect method (mainnet) or is already started (testnet)
                if hasattr(stream, 'connect'):
                    task = asyncio.create_task(stream.connect())
                    stream_tasks.append(task)
                    logger.info(f"Starting {name} WebSocket stream...")
                else:
                    # AdaptiveStream is already started in background
                    logger.info(f"{name} AdaptiveStream already running in background")

            # Start signal processor
            if self.mode in ['production', 'shadow']:
                # ✅ CHANGE: Start WebSocket FIRST before aged monitoring
                logger.info("🌐 Starting WebSocket signal processor...")
                await self.signal_processor.start()
                logger.info("✅ WebSocket signal processor started")

                # ✅ CHANGE: Wait for WebSocket connection to establish
                # This ensures price updates are flowing before we start aged monitoring
                logger.info("⏳ Waiting for WebSocket connections to stabilize (3s)...")
                await asyncio.sleep(3)
                logger.info("✅ WebSocket connections established")

                # ✅ CHANGE: NOW start periodic aged scan (with immediate first scan inside)
                # WebSocket is connected, so immediate scan will have price data for verification
                if self.position_manager.unified_protection:
                    logger.info("🔍 Starting periodic aged scan task...")
                    asyncio.create_task(start_periodic_aged_scan(
                        self.position_manager.unified_protection,
                        interval_minutes=5  # Scan every 5 minutes
                    ))
                    logger.info("✅ Periodic aged scan task started (interval: 5 minutes, immediate first scan enabled)")

                    # Start WebSocket health monitor
                    asyncio.create_task(start_websocket_health_monitor(
                        unified_protection=self.position_manager.unified_protection,
                        check_interval_seconds=60,
                        position_manager=self.position_manager
                    ))
                    logger.info("✅ WebSocket health monitor started (interval: 60s, resubscription: enabled)")

            # Start monitoring
            monitor_task = asyncio.create_task(self._monitor_loop())
            health_task = asyncio.create_task(self._health_check_loop())

            # Start periodic position sync with zombie cleanup
            sync_task = None
            if self.position_manager:
                sync_task = asyncio.create_task(self.position_manager.start_periodic_sync())
                logger.info("🔄 Started periodic position synchronization")
                logger.info("🧟 ZOMBIE ORDER CLEANUP: ACTIVE")
                logger.info(f"  - Cleanup interval: {self.position_manager.sync_interval} seconds")
                logger.info(f"  - Mode: REAL CLEANUP (dry_run=False)")
                logger.info(f"  - Aggressive threshold: {self.position_manager.aggressive_cleanup_threshold} zombies")
                logger.info("  - Auto-adjusting interval based on zombie count")

            # Log startup complete
            logger.info("=" * 80)
            logger.info(f"🟢 TRADING BOT RUNNING IN {self.mode.upper()} MODE")
            logger.info("=" * 80)

            # Wait for shutdown
            await self.shutdown_event.wait()

            logger.info("Shutdown initiated...")

            # Stop components
            await self.signal_processor.stop()

            # Cancel tasks
            for task in stream_tasks:
                task.cancel()
            monitor_task.cancel()
            health_task.cancel()

            # Wait for tasks to complete
            await asyncio.gather(*stream_tasks, monitor_task, health_task,
                                 return_exceptions=True)

        except Exception as e:
            logger.critical(f"Fatal error: {e}", exc_info=True)

        finally:
            await self.cleanup()

    async def _monitor_loop(self):
        """Performance monitoring loop"""
        while self.running:
            try:
                # Update performance metrics
                metrics = await self._collect_metrics()
                # Store metrics in performance tracker
                if self.performance_tracker:
                    try:
                        await self.performance_tracker.update_metrics()
                    except Exception as e:
                        logger.debug(f"Performance tracker update skipped: {e}")

                # Check aged positions with smart liquidation
                if self.aged_position_manager:
                    aged_count = await self.aged_position_manager.check_and_process_aged_positions()
                    if aged_count > 0:
                        stats = self.aged_position_manager.get_statistics()
                        logger.info(f"📊 Aged positions processed: {aged_count}, "
                                  f"breakeven: {stats['breakeven_closes']}, "
                                  f"liquidated: {stats['gradual_liquidations']}")

                # Check positions have stop loss protection
                if self.position_manager:
                    await self.position_manager.check_positions_protection()

                # Log summary
                if self.position_manager:
                    stats = self.position_manager.get_statistics()
                    logger.info(
                        f"📊 Positions: {stats['open_positions']} | "
                        f"Exposure: ${stats['total_exposure']:.2f} | "
                        f"PnL: ${stats['total_pnl']:.2f} | "
                        f"Win Rate: {stats['win_rate']:.1f}%"
                    )

                await asyncio.sleep(300)  # Every 5 minutes (optimized to reduce API calls)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(10)

    async def _health_check_loop(self):
        """Health check loop"""
        while self.running:
            try:
                # Check exchange connections
                for name, exchange in self.exchanges.items():
                    try:
                        await exchange.fetch_balance()
                        # Exchange health OK
                    except Exception as e:
                        logger.warning(f"Exchange {name} health check failed")
                        logger.error(f"{name} health check failed: {e}")

                # Check database
                try:
                    await self.repository.pool.fetchval("SELECT 1")
                    # Database health OK
                except Exception:
                    logger.warning("Database health check failed")

                # Check WebSocket streams
                for name, stream in self.websockets.items():
                    is_healthy = stream.connected
                    if not is_healthy:
                        logger.warning(f"WebSocket {name} unhealthy")

                # Log health status
                if self.health_monitor:
                    health_status = self.health_monitor.get_system_health()
                    if health_status.status != HealthStatus.HEALTHY:
                        logger.warning(f"⚠️ System health: {health_status.status.value}")
                        issues = self.health_monitor.get_issues()
                        for issue in issues[:5]:  # Log first 5 issues
                            logger.warning(f"  - {issue}")

                        # Log health check failure
                        try:
                            from core.event_logger import get_event_logger, EventType
                            event_logger = get_event_logger()
                            if event_logger:
                                await event_logger.log_event(
                                    EventType.HEALTH_CHECK_FAILED,
                                    {
                                        'status': health_status.status.value,
                                        'issues': issues[:5],
                                        'issue_count': len(issues)
                                    },
                                    severity='WARNING'
                                )
                        except Exception as log_err:
                            logger.debug(f"Could not log health check failure: {log_err}")

                await asyncio.sleep(300)  # Every 5 minutes (optimized to reduce API calls)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(10)

    async def _collect_metrics(self) -> Dict:
        """Collect current metrics"""
        metrics = {
            'timestamp': datetime.now(timezone.utc),
            'mode': self.mode
        }

        # Collect from each component
        if self.position_manager:
            metrics['positions'] = self.position_manager.get_statistics()

        if self.signal_processor:
            metrics['signals'] = self.signal_processor.get_stats()

        if self.event_router:
            metrics['events'] = self.event_router.get_stats()

        # Exchange balances
        balances = {}
        for name, exchange in self.exchanges.items():
            try:
                balance = await exchange.fetch_balance()
                # Для Bybit unified account баланс может быть в info
                if name == 'bybit' and 'info' in balance:
                    try:
                        info = balance['info'].get('result', {}).get('list', [{}])[0]
                        balances[name] = float(info.get('totalAvailableBalance', 0))
                    except:
                        balances[name] = balance.get('USDT', {}).get('free', 0)
                else:
                    balances[name] = balance.get('USDT', {}).get('free', 0)
            except Exception as e:
                logger.warning(f"Failed to fetch balance for {name}: {e}")
                balances[name] = 0
        metrics['balances'] = balances

        return metrics

    async def _emergency_close_all(self):
        """Emergency close all positions"""
        logger.critical("🚨 EMERGENCY: Closing all positions")

        # Log emergency close trigger
        try:
            from core.event_logger import get_event_logger, EventType
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.EMERGENCY_CLOSE_ALL_TRIGGERED,
                    {
                        'reason': 'emergency_shutdown',
                        'exchanges': list(self.exchanges.keys())
                    },
                    severity='CRITICAL'
                )
        except Exception as log_err:
            logger.debug(f"Could not log emergency close: {log_err}")

        for name, exchange in self.exchanges.items():
            try:
                positions = await exchange.fetch_positions()
                for position in positions:
                    if position['contracts'] > 0:
                        logger.warning(f"Emergency closing {position['symbol']}")
                        await exchange.close_position(position['symbol'])
            except Exception as e:
                logger.error(f"Failed to close positions on {name}: {e}")

    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up resources...")

        # Shutdown EventLogger
        try:
            from core.event_logger import get_event_logger, EventType
            event_logger = get_event_logger()
            if event_logger:
                await event_logger.log_event(
                    EventType.BOT_STOPPED,
                    {'mode': self.mode},
                    severity='INFO'
                )
                await event_logger.shutdown()
                logger.info("EventLogger shut down")
        except Exception as e:
            logger.warning(f"EventLogger shutdown failed: {e}")

        # Disconnect WebSocket streams
        for name, stream in self.websockets.items():
            try:
                await stream.stop()
                logger.debug(f"Closed WebSocket for {name}")
            except Exception as e:
                logger.error(f"Failed to close WebSocket {name}: {e}")

        # Close exchange connections
        for name, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.debug(f"Closed exchange {name}")
            except Exception as e:
                logger.error(f"Failed to close exchange {name}: {e}")

        # Close database
        if self.repository:
            try:
                await self.repository.close()
                logger.debug("Closed database connection")
            except Exception as e:
                logger.error(f"Failed to close database: {e}")

        # Save final metrics
        if self.performance_tracker:
            try:
                # Log final metrics
                try:
                    await self.performance_tracker.update_metrics()
                    logger.info("Final metrics saved")
                except Exception as metrics_err:
                    logger.warning(f"Could not save final metrics: {metrics_err}")
            except Exception as e:
                logger.error(f"Failed to save final report: {e}")

        logger.info("✅ Cleanup complete")

    def handle_shutdown(self, signum, frame):
        """Handle shutdown signal"""
        logger.info(f"Received signal {signum}")
        self.running = False
        self.shutdown_event.set()


async def async_main(bot: TradingBot):
    """Async main function"""
    await bot.initialize()
    await bot.start()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Trading Bot')
    parser.add_argument(
        '--mode',
        choices=['production', 'shadow', 'backtest'],
        default='shadow',
        help='Operating mode'
    )
    parser.add_argument(
        '--config',
        default='config',
        help='Configuration directory'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force start by killing existing instances'
    )
    parser.add_argument(
        '--check-instances',
        action='store_true',
        help='Check for running instances and exit'
    )

    args = parser.parse_args()

    # Check for running instances
    if args.check_instances:
        if check_running('trading_bot'):
            logger.error("Found running instance")
            sys.exit(1)
        else:
            logger.info("No running instances found")
            sys.exit(0)

    # Force kill existing instances if requested
    if args.force:
        if kill_running('trading_bot', force=True):
            logger.info("Killed existing instance")
            # Wait for process to die
            import time
            time.sleep(2)

    # Acquire single instance lock (auto-exits if another instance is running)
    app_lock = SingleInstance('trading_bot')

    try:
        # Create bot instance
        bot = TradingBot(args)

        # Setup signal handlers
        signal.signal(signal.SIGINT, bot.handle_shutdown)
        signal.signal(signal.SIGTERM, bot.handle_shutdown)

        # Run bot
        try:
            logger.info("🚀 Starting trading bot (single instance enforced)")
            asyncio.run(async_main(bot))
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.critical(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)
    finally:
        # Lock is automatically released by SingleInstance on exit
        pass


if __name__ == "__main__":
    main()