"""
Main Trading Bot Application with Improved Shutdown
"""
import asyncio
import logging
import sys
from datetime import datetime
from typing import Dict, Optional
import argparse

from config.settings import settings
from core.exchange_manager import ExchangeManager
from core.position_manager import PositionManager
from core.signal_processor import SignalProcessor
from core.shutdown_manager import ShutdownManager, ShutdownPriority, ComponentShutdown
from database.repository import Repository as TradingRepository
from websocket.improved_stream import ImprovedStream
from websocket.binance_stream import BinancePrivateStream
from websocket.bybit_stream import BybitPrivateStream
from websocket.event_router import EventRouter
from protection.trailing_stop import SmartTrailingStopManager, TrailingStopConfig
from monitoring.health_check import HealthChecker
from monitoring.performance import PerformanceTracker

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """
    Main trading bot application with improved shutdown handling
    """

    def __init__(self, args: argparse.Namespace):
        """Initialize trading bot"""
        self.args = args
        self.mode = args.mode  # 'production', 'shadow', 'backtest'
        
        # Core components
        self.exchanges: Dict[str, ExchangeManager] = {}
        self.websockets: Dict[str, ImprovedStream] = {}
        self.repository: Optional[TradingRepository] = None
        self.event_router = EventRouter()
        self.position_manager: Optional[PositionManager] = None
        self.signal_processor: Optional[SignalProcessor] = None
        
        # Monitoring
        self.health_monitor = HealthChecker()
        self.performance_tracker = PerformanceTracker()
        
        # Shutdown manager with 10 second timeout
        self.shutdown_manager = ShutdownManager(timeout=10)
        
        # Running tasks
        self.monitor_task = None
        self.health_task = None
        
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
            
            # Initialize exchanges
            logger.info("Initializing exchanges...")
            for name, config in settings.exchanges.items():
                if not config.enabled:
                    logger.info(f"Skipping disabled exchange: {name}")
                    continue
                    
                exchange = ExchangeManager(name, config.__dict__)
                try:
                    await exchange.initialize()
                    self.exchanges[name] = exchange
                    logger.info(f"✅ {name.capitalize()} exchange initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize {name}: {e}")
                    if self.mode == 'production':
                        raise
            
            # Initialize WebSocket streams
            logger.info("Initializing WebSocket streams...")
            await self._initialize_websockets()
            
            # Initialize position manager
            if self.mode in ['production', 'shadow']:
                self.position_manager = PositionManager(
                    exchange_manager=self.exchanges,
                    repository=self.repository
                )
                await self.position_manager.initialize()
                logger.info("Position manager initialized")
            
            # Initialize signal processor
            self.signal_processor = SignalProcessor(
                exchange_manager=self.exchanges,
                position_manager=self.position_manager,
                repository=self.repository,
                mode=self.mode
            )
            await self.signal_processor.initialize()
            logger.info("Signal processor initialized")
            
            # Initialize monitoring
            await self.health_monitor.initialize()
            await self.performance_tracker.initialize(self.repository)
            
            # Register shutdown tasks
            self._register_shutdown_tasks()
            
            # Setup signal handlers
            self.shutdown_manager.setup_signal_handlers()
            
            logger.info("✅ Trading Bot initialization complete")
            
        except Exception as e:
            logger.critical(f"Initialization failed: {e}", exc_info=True)
            await self.cleanup()
            raise

    async def _initialize_websockets(self):
        """Initialize WebSocket streams with improved reconnection"""
        for name, config in settings.exchanges.items():
            if not config.enabled:
                continue
                
            try:
                if name == 'binance':
                    stream = BinancePrivateStream(
                        config=config.__dict__,
                        api_key=config.api_key,
                        api_secret=config.api_secret,
                        event_handler=self._handle_stream_event
                    )
                elif name == 'bybit':
                    stream = BybitPrivateStream(
                        config=config.__dict__,
                        api_key=config.api_key,
                        api_secret=config.api_secret,
                        event_handler=self._handle_stream_event
                    )
                else:
                    logger.warning(f"Unknown exchange type: {name}")
                    continue
                
                self.websockets[name] = stream
                logger.info(f"✅ {name.capitalize()} WebSocket initialized")
                
            except Exception as e:
                logger.error(f"Failed to initialize {name} WebSocket: {e}")

    def _register_shutdown_tasks(self):
        """Register shutdown tasks with priority"""
        
        # CRITICAL: Must complete
        if self.mode == 'production':
            self.shutdown_manager.register_shutdown_task(
                self._close_all_positions,
                ShutdownPriority.CRITICAL
            )
            self.shutdown_manager.register_shutdown_task(
                self._cancel_all_orders,
                ShutdownPriority.CRITICAL
            )
        
        # HIGH: Should complete
        self.shutdown_manager.register_shutdown_task(
            self._save_state,
            ShutdownPriority.HIGH
        )
        
        # MEDIUM: Nice to complete
        self.shutdown_manager.register_shutdown_task(
            self._disconnect_websockets,
            ShutdownPriority.MEDIUM
        )
        self.shutdown_manager.register_shutdown_task(
            self._close_exchanges,
            ShutdownPriority.MEDIUM
        )
        
        # LOW: Optional
        self.shutdown_manager.register_shutdown_task(
            self._save_final_metrics,
            ShutdownPriority.LOW
        )
        self.shutdown_manager.register_shutdown_task(
            self._close_database,
            ShutdownPriority.LOW
        )

    async def start(self):
        """Start trading bot with improved shutdown handling"""
        logger.info("🚀 Starting Trading Bot...")
        
        try:
            # Start WebSocket streams
            for name, stream in self.websockets.items():
                await stream.start()
                logger.info(f"Started {name} WebSocket stream")
            
            # Start signal processor
            if self.mode in ['production', 'shadow']:
                await self.signal_processor.start()
                logger.info("Signal processor started")
            
            # Start monitoring tasks
            self.monitor_task = asyncio.create_task(self._monitor_loop())
            self.health_task = asyncio.create_task(self._health_check_loop())
            
            # Register running tasks for cleanup
            self.shutdown_manager.register_running_task(self.monitor_task)
            self.shutdown_manager.register_running_task(self.health_task)
            
            # Log startup complete
            logger.info("=" * 80)
            logger.info(f"🟢 TRADING BOT RUNNING IN {self.mode.upper()} MODE")
            logger.info("=" * 80)
            
            # Wait for shutdown
            await self.shutdown_manager.wait_for_shutdown()
            
        except Exception as e:
            logger.critical(f"Fatal error: {e}", exc_info=True)
            await self.shutdown_manager.shutdown(f"Fatal error: {e}")

    async def _monitor_loop(self):
        """Performance monitoring loop"""
        while not self.shutdown_manager.is_shutdown_requested():
            try:
                # Update performance metrics
                metrics = await self._collect_metrics()
                await self.performance_tracker.update_metrics(metrics)
                
                # Log summary
                if self.position_manager:
                    stats = self.position_manager.get_statistics()
                    logger.info(
                        f"📊 Positions: {stats.get('open_positions', 0)} | "
                        f"Exposure: ${stats.get('total_exposure', 0):.2f} | "
                        f"PnL: ${stats.get('total_pnl', 0):.2f} | "
                        f"Win Rate: {stats.get('win_rate', 0):.1f}%"
                    )
                
                await asyncio.sleep(60)  # Every minute
                
            except asyncio.CancelledError:
                logger.debug("Monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(60)

    async def _health_check_loop(self):
        """Health check loop"""
        while not self.shutdown_manager.is_shutdown_requested():
            try:
                # Check exchange connections
                for name, exchange in self.exchanges.items():
                    try:
                        await exchange.ping()
                        self.health_monitor.record_check(f"exchange_{name}", True)
                    except:
                        self.health_monitor.record_check(f"exchange_{name}", False)
                
                # Check database
                try:
                    await self.repository.health_check()
                    self.health_monitor.record_check("database", True)
                except:
                    self.health_monitor.record_check("database", False)
                
                # Check WebSocket connections
                for name, stream in self.websockets.items():
                    stats = stream.get_stats()
                    is_connected = stats['state'] == 'connected'
                    self.health_monitor.record_check(f"websocket_{name}", is_connected)
                
                await asyncio.sleep(30)  # Every 30 seconds
                
            except asyncio.CancelledError:
                logger.debug("Health check loop cancelled")
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(30)

    async def _collect_metrics(self) -> Dict:
        """Collect performance metrics"""
        metrics = {}
        
        if self.position_manager:
            metrics['positions'] = self.position_manager.get_statistics()
        
        if self.signal_processor:
            metrics['signals'] = self.signal_processor.get_stats()
        
        # Exchange balances
        balances = {}
        for name, exchange in self.exchanges.items():
            try:
                balance = await exchange.fetch_balance()
                balances[name] = balance.get('USDT', {}).get('free', 0)
            except:
                balances[name] = 0
        metrics['balances'] = balances
        
        return metrics

    async def _handle_stream_event(self, event: str, data: Dict):
        """Handle WebSocket stream events"""
        await self.event_router.emit(event, data, source='websocket')

    # Shutdown tasks
    async def _close_all_positions(self):
        """Close all open positions (CRITICAL)"""
        if not self.position_manager:
            return
            
        logger.info("Closing all open positions...")
        positions = await self.position_manager.get_open_positions()
        
        if not positions:
            logger.info("No open positions to close")
            return
        
        for position in positions:
            try:
                await self.exchanges[position['exchange']].close_position(
                    position['symbol']
                )
                logger.info(f"Closed {position['symbol']} on {position['exchange']}")
            except Exception as e:
                logger.error(f"Failed to close {position['symbol']}: {e}")

    async def _cancel_all_orders(self):
        """Cancel all open orders (CRITICAL)"""
        logger.info("Cancelling all open orders...")
        
        for name, exchange in self.exchanges.items():
            try:
                cancelled = await exchange.cancel_all_orders()
                if cancelled > 0:
                    logger.info(f"Cancelled {cancelled} orders on {name}")
            except Exception as e:
                logger.error(f"Failed to cancel orders on {name}: {e}")

    async def _save_state(self):
        """Save system state (HIGH)"""
        logger.info("Saving system state...")
        
        state = {
            'timestamp': datetime.now().isoformat(),
            'mode': self.mode,
            'positions': await self.position_manager.get_open_positions() if self.position_manager else [],
            'metrics': await self._collect_metrics()
        }
        
        # Save to file as backup
        import json
        with open('logs/shutdown_state.json', 'w') as f:
            json.dump(state, f, indent=2, default=str)
        
        logger.info("System state saved")

    async def _disconnect_websockets(self):
        """Disconnect WebSocket streams (MEDIUM)"""
        logger.info("Disconnecting WebSocket streams...")
        
        for name, stream in self.websockets.items():
            try:
                await stream.stop()
                logger.debug(f"Disconnected {name} WebSocket")
            except Exception as e:
                logger.error(f"Error disconnecting {name} WebSocket: {e}")

    async def _close_exchanges(self):
        """Close exchange connections (MEDIUM)"""
        logger.info("Closing exchange connections...")
        
        for name, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.debug(f"Closed {name} exchange")
            except Exception as e:
                logger.error(f"Error closing {name} exchange: {e}")

    async def _save_final_metrics(self):
        """Save final performance metrics (LOW)"""
        if self.performance_tracker:
            try:
                await self.performance_tracker.save_final_report()
                logger.info("Final metrics saved")
            except Exception as e:
                logger.error(f"Failed to save final metrics: {e}")

    async def _close_database(self):
        """Close database connections (LOW)"""
        if self.repository:
            try:
                await self.repository.close()
                logger.info("Database connections closed")
            except Exception as e:
                logger.error(f"Failed to close database: {e}")

    async def cleanup(self):
        """Emergency cleanup (called if initialization fails)"""
        logger.info("Emergency cleanup...")
        
        # Use shutdown manager for organized cleanup
        await self.shutdown_manager.shutdown("Emergency cleanup")


async def main(args: argparse.Namespace):
    """Main entry point"""
    bot = TradingBot(args)
    
    try:
        await bot.initialize()
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await bot.shutdown_manager.shutdown("User interrupted")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Trading bot terminated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trading Bot")
    parser.add_argument(
        "--mode",
        choices=['production', 'shadow', 'backtest'],
        default='shadow',
        help="Operating mode"
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Configuration file path"
    )
    
    args = parser.parse_args()
    
    # Run the bot
    asyncio.run(main(args))