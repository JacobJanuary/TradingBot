"""
Prometheus metrics collection and export for trading bot monitoring
"""

import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from prometheus_client import (
    Counter, Gauge, Histogram, Summary,
    generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry, push_to_gateway
)
from aiohttp import web
import asyncio
from loguru import logger

from database.repository import Repository


class MetricsCollector:
    """
    Collects and exposes metrics for Prometheus monitoring
    
    Metrics categories:
    - Trading performance (PnL, win rate, positions)
    - System health (latency, errors, uptime)
    - Exchange connectivity (API calls, WebSocket status)
    - Risk metrics (exposure, drawdown, violations)
    """
    
    def __init__(self, 
                 repository: Repository,
                 config: Dict[str, Any]):
        
        self.repository = repository
        self.config = config
        
        # Prometheus settings
        self.registry = CollectorRegistry()
        self.port = config.get('metrics_port', 8000)
        self.push_gateway = config.get('push_gateway_url')
        self.push_interval = config.get('push_interval', 60)
        
        # Initialize metrics
        self._init_trading_metrics()
        self._init_system_metrics()
        self._init_exchange_metrics()
        self._init_risk_metrics()
        
        # Metrics server
        self.app = web.Application()
        self._setup_routes()
        self.runner = None
        
        # State tracking
        self.start_time = time.time()
        self.last_push = datetime.now(timezone.utc)
        
        logger.info(f"MetricsCollector initialized on port {self.port}")
    
    def _init_trading_metrics(self):
        """Initialize trading performance metrics"""
        
        # Position metrics
        self.positions_opened = Counter(
            'trading_positions_opened_total',
            'Total number of positions opened',
            ['exchange', 'symbol', 'side'],
            registry=self.registry
        )
        
        self.positions_closed = Counter(
            'trading_positions_closed_total',
            'Total number of positions closed',
            ['exchange', 'symbol', 'side', 'profit_loss'],
            registry=self.registry
        )
        
        self.active_positions = Gauge(
            'trading_active_positions',
            'Number of currently active positions',
            ['exchange'],
            registry=self.registry
        )
        
        # PnL metrics
        self.total_pnl = Gauge(
            'trading_total_pnl_usd',
            'Total profit and loss in USD',
            ['exchange'],
            registry=self.registry
        )
        
        self.daily_pnl = Gauge(
            'trading_daily_pnl_usd',
            'Daily profit and loss in USD',
            ['exchange'],
            registry=self.registry
        )
        
        self.unrealized_pnl = Gauge(
            'trading_unrealized_pnl_usd',
            'Current unrealized PnL',
            ['exchange'],
            registry=self.registry
        )
        
        # Performance metrics
        self.win_rate = Gauge(
            'trading_win_rate_percent',
            'Percentage of profitable trades',
            ['exchange', 'timeframe'],
            registry=self.registry
        )
        
        self.sharpe_ratio = Gauge(
            'trading_sharpe_ratio',
            'Sharpe ratio of returns',
            ['exchange', 'timeframe'],
            registry=self.registry
        )
        
        self.trade_duration = Histogram(
            'trading_position_duration_seconds',
            'Duration of closed positions',
            ['exchange', 'symbol'],
            buckets=(60, 300, 900, 1800, 3600, 7200, 14400, 28800, 86400),
            registry=self.registry
        )
        
        # Order metrics
        self.orders_placed = Counter(
            'trading_orders_placed_total',
            'Total number of orders placed',
            ['exchange', 'type', 'side'],
            registry=self.registry
        )
        
        self.orders_filled = Counter(
            'trading_orders_filled_total',
            'Total number of orders filled',
            ['exchange', 'type', 'side'],
            registry=self.registry
        )
        
        self.order_latency = Histogram(
            'trading_order_latency_ms',
            'Order placement latency in milliseconds',
            ['exchange'],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
            registry=self.registry
        )
    
    def _init_system_metrics(self):
        """Initialize system health metrics"""
        
        # Uptime
        self.uptime = Gauge(
            'system_uptime_seconds',
            'System uptime in seconds',
            registry=self.registry
        )
        
        # Error tracking
        self.errors = Counter(
            'system_errors_total',
            'Total number of errors',
            ['component', 'severity'],
            registry=self.registry
        )
        
        # Processing metrics
        self.signal_processing_time = Histogram(
            'system_signal_processing_seconds',
            'Time to process trading signals',
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
            registry=self.registry
        )
        
        self.db_query_time = Histogram(
            'system_db_query_seconds',
            'Database query execution time',
            ['operation'],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
            registry=self.registry
        )
        
        # Resource usage
        self.memory_usage = Gauge(
            'system_memory_usage_bytes',
            'Memory usage in bytes',
            registry=self.registry
        )
        
        self.cpu_usage = Gauge(
            'system_cpu_usage_percent',
            'CPU usage percentage',
            registry=self.registry
        )
        
        # Task queue
        self.pending_tasks = Gauge(
            'system_pending_tasks',
            'Number of pending tasks',
            ['queue'],
            registry=self.registry
        )
    
    def _init_exchange_metrics(self):
        """Initialize exchange connectivity metrics"""
        
        # API metrics
        self.api_calls = Counter(
            'exchange_api_calls_total',
            'Total number of API calls',
            ['exchange', 'endpoint', 'status'],
            registry=self.registry
        )
        
        self.api_latency = Histogram(
            'exchange_api_latency_ms',
            'API call latency in milliseconds',
            ['exchange', 'endpoint'],
            buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10000),
            registry=self.registry
        )
        
        self.rate_limit_remaining = Gauge(
            'exchange_rate_limit_remaining',
            'Remaining API rate limit',
            ['exchange'],
            registry=self.registry
        )
        
        # WebSocket metrics
        self.ws_connected = Gauge(
            'exchange_websocket_connected',
            'WebSocket connection status (1=connected, 0=disconnected)',
            ['exchange', 'stream'],
            registry=self.registry
        )
        
        self.ws_messages = Counter(
            'exchange_websocket_messages_total',
            'Total WebSocket messages received',
            ['exchange', 'stream', 'type'],
            registry=self.registry
        )
        
        self.ws_reconnects = Counter(
            'exchange_websocket_reconnects_total',
            'Total WebSocket reconnection attempts',
            ['exchange', 'stream'],
            registry=self.registry
        )
        
        # Market data
        self.last_price = Gauge(
            'exchange_last_price',
            'Last traded price',
            ['exchange', 'symbol'],
            registry=self.registry
        )
        
        self.orderbook_spread = Gauge(
            'exchange_orderbook_spread_percent',
            'Order book bid-ask spread percentage',
            ['exchange', 'symbol'],
            registry=self.registry
        )
    
    def _init_risk_metrics(self):
        """Initialize risk management metrics"""
        
        # Exposure metrics
        self.total_exposure = Gauge(
            'risk_total_exposure_usd',
            'Total position exposure in USD',
            ['exchange'],
            registry=self.registry
        )
        
        self.max_drawdown = Gauge(
            'risk_max_drawdown_percent',
            'Maximum drawdown percentage',
            ['exchange', 'timeframe'],
            registry=self.registry
        )
        
        self.current_drawdown = Gauge(
            'risk_current_drawdown_percent',
            'Current drawdown from peak',
            ['exchange'],
            registry=self.registry
        )
        
        # Risk violations
        self.risk_violations = Counter(
            'risk_violations_total',
            'Total risk limit violations',
            ['type', 'severity'],
            registry=self.registry
        )
        
        # Stop loss metrics
        self.stop_losses_triggered = Counter(
            'risk_stop_losses_triggered_total',
            'Total stop losses triggered',
            ['exchange', 'symbol'],
            registry=self.registry
        )
        
        self.positions_saved = Counter(
            'risk_positions_saved_total',
            'Positions saved by risk management',
            ['exchange', 'action'],
            registry=self.registry
        )
        
        # Leverage and margin
        self.leverage_used = Gauge(
            'risk_leverage_used',
            'Current leverage multiplier',
            ['exchange'],
            registry=self.registry
        )
        
        self.margin_ratio = Gauge(
            'risk_margin_ratio_percent',
            'Margin usage percentage',
            ['exchange'],
            registry=self.registry
        )
    
    def _setup_routes(self):
        """Setup HTTP routes for metrics endpoint"""
        
        async def metrics_handler(request):
            """Prometheus metrics endpoint"""
            metrics = generate_latest(self.registry)
            return web.Response(text=metrics.decode('utf-8'), 
                              content_type=CONTENT_TYPE_LATEST)
        
        async def health_handler(request):
            """Health check endpoint"""
            return web.json_response({'status': 'healthy', 
                                    'uptime': time.time() - self.start_time})
        
        self.app.router.add_get('/metrics', metrics_handler)
        self.app.router.add_get('/health', health_handler)
    
    async def start(self):
        """Start metrics server"""
        
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            site = web.TCPSite(self.runner, '0.0.0.0', self.port)
            await site.start()
            
            logger.info(f"Metrics server started on port {self.port}")
            
            # Start push gateway task if configured
            if self.push_gateway:
                asyncio.create_task(self._push_metrics_loop())
            
            # Start metric collection tasks
            asyncio.create_task(self._collect_metrics_loop())
            
        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")
    
    async def stop(self):
        """Stop metrics server"""
        
        if self.runner:
            await self.runner.cleanup()
            logger.info("Metrics server stopped")
    
    async def _collect_metrics_loop(self):
        """Periodically collect and update metrics"""
        
        while True:
            try:
                await asyncio.sleep(10)  # Collect every 10 seconds
                
                # Update uptime
                self.uptime.set(time.time() - self.start_time)
                
                # Collect trading metrics
                await self._collect_trading_metrics()
                
                # Collect system metrics
                await self._collect_system_metrics()
                
                # Collect risk metrics
                await self._collect_risk_metrics()
                
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                self.errors.labels(component='metrics', severity='medium').inc()
    
    async def _collect_trading_metrics(self):
        """Collect current trading metrics from database"""
        
        try:
            # Get active positions
            positions = await self.repository.get_active_positions()
            
            for exchange in ['binance', 'bybit']:
                exchange_positions = [p for p in positions if p.exchange == exchange]
                self.active_positions.labels(exchange=exchange).set(len(exchange_positions))
                
                # Calculate unrealized PnL
                total_unrealized = sum(p.unrealized_pnl or 0 for p in exchange_positions)
                self.unrealized_pnl.labels(exchange=exchange).set(float(total_unrealized))
            
            # Get daily PnL
            daily_stats = await self.repository.get_daily_stats(datetime.now(timezone.utc).date())
            if daily_stats:
                for exchange in ['binance', 'bybit']:
                    daily_pnl = daily_stats.get(exchange, {}).get('pnl', 0)
                    self.daily_pnl.labels(exchange=exchange).set(float(daily_pnl))
            
            # Calculate win rates
            for timeframe in ['1h', '24h', '7d', '30d']:
                win_rate = await self._calculate_win_rate(timeframe)
                for exchange, rate in win_rate.items():
                    self.win_rate.labels(exchange=exchange, timeframe=timeframe).set(rate)
            
        except Exception as e:
            logger.error(f"Error collecting trading metrics: {e}")
    
    async def _collect_system_metrics(self):
        """Collect system resource metrics"""
        
        try:
            import psutil
            
            # Memory usage
            process = psutil.Process()
            memory = process.memory_info().rss
            self.memory_usage.set(memory)
            
            # CPU usage
            cpu_percent = process.cpu_percent()
            self.cpu_usage.set(cpu_percent)
            
            # Pending tasks (example)
            pending = len(asyncio.all_tasks())
            self.pending_tasks.labels(queue='asyncio').set(pending)
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
    
    async def _collect_risk_metrics(self):
        """Collect risk management metrics"""
        
        try:
            positions = await self.repository.get_active_positions()
            
            for exchange in ['binance', 'bybit']:
                exchange_positions = [p for p in positions if p.exchange == exchange]
                
                # Calculate total exposure
                total_exposure = sum(
                    abs(p.size * p.entry_price) 
                    for p in exchange_positions
                )
                self.total_exposure.labels(exchange=exchange).set(float(total_exposure))
                
                # Calculate current drawdown
                drawdown = await self._calculate_drawdown(exchange)
                self.current_drawdown.labels(exchange=exchange).set(drawdown)
            
        except Exception as e:
            logger.error(f"Error collecting risk metrics: {e}")
    
    async def _calculate_win_rate(self, timeframe: str) -> Dict[str, float]:
        """Calculate win rate for given timeframe"""
        
        try:
            # Parse timeframe
            if timeframe.endswith('h'):
                hours = int(timeframe[:-1])
                since = datetime.now(timezone.utc) - timedelta(hours=hours)
            elif timeframe.endswith('d'):
                days = int(timeframe[:-1])
                since = datetime.now(timezone.utc) - timedelta(days=days)
            else:
                return {}
            
            # Get closed positions
            closed = await self.repository.get_closed_positions_since(since)
            
            win_rates = {}
            for exchange in ['binance', 'bybit']:
                exchange_positions = [p for p in closed if p.exchange == exchange]
                if exchange_positions:
                    wins = sum(1 for p in exchange_positions if p.realized_pnl > 0)
                    win_rates[exchange] = (wins / len(exchange_positions)) * 100
                else:
                    win_rates[exchange] = 0
            
            return win_rates
            
        except Exception as e:
            logger.error(f"Error calculating win rate: {e}")
            return {}
    
    async def _calculate_drawdown(self, exchange: str) -> float:
        """Calculate current drawdown from peak"""
        
        try:
            # Get account balance history
            history = await self.repository.get_balance_history(exchange, days=30)
            
            if not history:
                return 0
            
            # Find peak balance
            peak = max(h.balance for h in history)
            current = history[-1].balance
            
            if peak > 0:
                drawdown = ((peak - current) / peak) * 100
                return max(0, drawdown)
            
            return 0
            
        except Exception as e:
            logger.error(f"Error calculating drawdown: {e}")
            return 0
    
    async def _push_metrics_loop(self):
        """Push metrics to Prometheus push gateway"""
        
        while True:
            try:
                await asyncio.sleep(self.push_interval)
                
                if self.push_gateway:
                    push_to_gateway(
                        self.push_gateway,
                        job='trading_bot',
                        registry=self.registry
                    )
                    
                    logger.debug(f"Pushed metrics to {self.push_gateway}")
                
            except Exception as e:
                logger.error(f"Error pushing metrics: {e}")
    
    # Public methods for recording metrics
    
    def record_position_opened(self, exchange: str, symbol: str, side: str):
        """Record new position opened"""
        self.positions_opened.labels(exchange=exchange, symbol=symbol, side=side).inc()
    
    def record_position_closed(self, exchange: str, symbol: str, side: str, pnl: float):
        """Record position closed"""
        profit_loss = 'profit' if pnl > 0 else 'loss'
        self.positions_closed.labels(
            exchange=exchange, 
            symbol=symbol, 
            side=side,
            profit_loss=profit_loss
        ).inc()
    
    def record_order_placed(self, exchange: str, order_type: str, side: str):
        """Record order placement"""
        self.orders_placed.labels(exchange=exchange, type=order_type, side=side).inc()
    
    def record_order_filled(self, exchange: str, order_type: str, side: str):
        """Record order fill"""
        self.orders_filled.labels(exchange=exchange, type=order_type, side=side).inc()
    
    def record_order_latency(self, exchange: str, latency_ms: float):
        """Record order placement latency"""
        self.order_latency.labels(exchange=exchange).observe(latency_ms)
    
    def record_api_call(self, exchange: str, endpoint: str, status: str, latency_ms: float):
        """Record API call metrics"""
        self.api_calls.labels(exchange=exchange, endpoint=endpoint, status=status).inc()
        self.api_latency.labels(exchange=exchange, endpoint=endpoint).observe(latency_ms)
    
    def record_error(self, component: str, severity: str = 'low'):
        """Record system error"""
        self.errors.labels(component=component, severity=severity).inc()
    
    def record_risk_violation(self, violation_type: str, severity: str = 'medium'):
        """Record risk violation"""
        self.risk_violations.labels(type=violation_type, severity=severity).inc()
    
    def record_stop_loss_triggered(self, exchange: str, symbol: str):
        """Record stop loss trigger"""
        self.stop_losses_triggered.labels(exchange=exchange, symbol=symbol).inc()
    
    def set_websocket_status(self, exchange: str, stream: str, connected: bool):
        """Update WebSocket connection status"""
        self.ws_connected.labels(exchange=exchange, stream=stream).set(1 if connected else 0)
    
    def record_websocket_message(self, exchange: str, stream: str, message_type: str):
        """Record WebSocket message received"""
        self.ws_messages.labels(exchange=exchange, stream=stream, type=message_type).inc()
    
    def record_websocket_reconnect(self, exchange: str, stream: str):
        """Record WebSocket reconnection"""
        self.ws_reconnects.labels(exchange=exchange, stream=stream).inc()
    
    def update_price(self, exchange: str, symbol: str, price: float):
        """Update last price metric"""
        self.last_price.labels(exchange=exchange, symbol=symbol).set(price)
    
    def update_spread(self, exchange: str, symbol: str, spread_pct: float):
        """Update orderbook spread"""
        self.orderbook_spread.labels(exchange=exchange, symbol=symbol).set(spread_pct)