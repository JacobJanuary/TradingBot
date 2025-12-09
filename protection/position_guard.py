"""
Position Guard - Real-time position protection and monitoring system
"""

import asyncio
from typing import Dict, Any, Optional, List, Set
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass, field
import numpy as np
from loguru import logger

from core.exchange_manager import ExchangeManager
from core.risk_manager import RiskManager
from protection.stop_loss_manager import StopLossManager
from protection.trailing_stop import TrailingStopManager
from database.models import Position, Alert, RiskEvent
from database.repository import Repository
from websocket.event_router import EventRouter
from utils.decorators import async_retry


class RiskLevel(Enum):
    """Risk severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class ProtectionAction(Enum):
    """Protection actions that can be taken"""
    MONITOR = "monitor"
    ADJUST_STOP = "adjust_stop"
    PARTIAL_CLOSE = "partial_close"
    FULL_CLOSE = "full_close"
    HEDGE = "hedge"
    FREEZE = "freeze"
    EMERGENCY_EXIT = "emergency_exit"


@dataclass
class PositionHealth:
    """Position health metrics"""
    position_id: str
    symbol: str
    health_score: float  # 0-100
    risk_level: RiskLevel
    unrealized_pnl: Decimal
    pnl_percentage: Decimal
    time_in_position: timedelta
    volatility_score: float
    liquidity_score: float
    drawdown: Decimal
    max_drawdown: Decimal
    recommended_actions: List[ProtectionAction] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)


class PositionGuard:
    """
    Advanced position protection system that monitors and protects positions in real-time
    
    Features:
    - Real-time position health monitoring
    - Automatic risk detection and mitigation
    - Dynamic protection adjustments
    - Emergency exit mechanisms
    - Correlation-based risk analysis
    """
    
    def __init__(self,
                 exchange_manager: ExchangeManager,
                 risk_manager: RiskManager,
                 stop_loss_manager: StopLossManager,
                 trailing_stop_manager: TrailingStopManager,
                 repository: Repository,
                 event_router: EventRouter,
                 config: Dict[str, Any]):
        
        self.exchange_manager = exchange_manager
        self.risk_manager = risk_manager
        self.stop_loss_manager = stop_loss_manager
        self.trailing_stop_manager = trailing_stop_manager
        self.repository = repository
        self.event_router = event_router
        self.config = config
        
        # Protection thresholds
        self.max_drawdown_pct = Decimal(str(config.get('max_drawdown_pct', 5.0)))
        self.critical_loss_pct = Decimal(str(config.get('critical_loss_pct', 3.0)))
        self.time_limit_hours = config.get('max_position_hours', 48)
        self.volatility_threshold = config.get('volatility_threshold', 2.0)
        self.correlation_threshold = config.get('correlation_threshold', 0.7)
        
        # Health score weights
        self.health_weights = {
            'pnl': 0.3,
            'drawdown': 0.2,
            'volatility': 0.2,
            'time': 0.15,
            'liquidity': 0.15
        }
        
        # Monitoring state
        self.monitored_positions: Dict[str, Position] = {}
        self.position_health: Dict[str, PositionHealth] = {}
        self.position_peaks: Dict[str, Decimal] = {}  # Track highest values
        self.emergency_mode: bool = False
        self.frozen_positions: Set[str] = set()
        
        # Performance tracking
        self.protection_stats = {
            'positions_saved': 0,
            'losses_prevented': Decimal('0'),
            'emergency_exits': 0,
            'auto_adjustments': 0
        }
        
        # Setup event handlers
        self._setup_event_handlers()
        
        logger.info("PositionGuard initialized with advanced protection")
    
    def _setup_event_handlers(self):
        """Setup WebSocket event handlers"""
        
        # Register for position updates
        self.event_router.register_handler(
            'position_update',
            self._handle_position_update
        )
        
        # Register for price updates
        self.event_router.register_handler(
            'price_update',
            self._handle_price_update
        )
        
        # Register for order fills
        self.event_router.register_handler(
            'order_filled',
            self._handle_order_filled
        )
        
        # Register for risk alerts
        self.event_router.register_handler(
            'risk_alert',
            self._handle_risk_alert
        )
    
    async def start_protection(self, position: Position):
        """Start protecting a position"""
        
        try:
            position_id = position.id
            
            if position_id in self.monitored_positions:
                logger.warning(f"Position {position_id} already being monitored")
                return
            
            # Initialize monitoring
            self.monitored_positions[position_id] = position
            position_id_str = str(position.id)
            self.position_peaks[position_id_str] = Decimal(str(position.entry_price))
            
            # Perform initial health check
            health = await self._calculate_position_health(position)
            self.position_health[position_id] = health
            
            # Setup initial protection
            await self._setup_initial_protection(position, health)
            
            # Start monitoring loop
            asyncio.create_task(self._monitor_position_loop(position_id))
            
            logger.info(f"Started protection for position {position_id} "
                       f"(Health: {health.health_score:.1f}, Risk: {health.risk_level.value})")
            
        except Exception as e:
            logger.error(f"Failed to start position protection: {e}")
            await self._emergency_protection(position)
    
    async def _monitor_position_loop(self, position_id: str):
        """Continuous monitoring loop for a position"""
        
        check_interval = 5  # seconds
        last_health_check = datetime.now(timezone.utc)
        
        while position_id in self.monitored_positions:
            try:
                await asyncio.sleep(check_interval)
                
                position = self.monitored_positions[position_id]
                
                # Get current market data
                ticker = await self.exchange_manager.fetch_ticker(position.symbol)
                current_price = Decimal(str(ticker['last']))
                
                # Update position peak
                if position.side == 'long':
                    if current_price > self.position_peaks[position_id]:
                        self.position_peaks[position_id] = current_price
                else:
                    if current_price < self.position_peaks[position_id]:
                        self.position_peaks[position_id] = current_price
                
                # Perform health check every minute
                if (datetime.now(timezone.utc) - last_health_check).seconds >= 60:
                    health = await self._calculate_position_health(position, current_price)
                    self.position_health[position_id] = health
                    last_health_check = datetime.now(timezone.utc)
                    
                    # Take protection actions based on health
                    await self._execute_protection_actions(position, health)
                
                # Quick checks for critical conditions
                await self._check_critical_conditions(position, current_price)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in position monitor loop: {e}")
                await asyncio.sleep(check_interval * 2)
    
    async def _calculate_position_health(self, 
                                        position: Position,
                                        current_price: Optional[Decimal] = None) -> PositionHealth:
        """Calculate comprehensive position health score"""
        
        try:
            # Get current price if not provided
            if current_price is None:
                ticker = await self.exchange_manager.fetch_ticker(position.symbol)
                current_price = Decimal(str(ticker['last']))
            
            entry_price = Decimal(str(position.entry_price))
            position_size = Decimal(str(position.quantity))
            
            # Calculate PnL
            if position.side == 'long':
                pnl = (current_price - entry_price) * position_size
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
            else:
                pnl = (entry_price - current_price) * abs(position_size)
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
            
            # Calculate drawdown from peak
            position_id_str = str(position.id)
            peak = self.position_peaks.get(position_id_str, entry_price)
            if position.side == 'long':
                drawdown_pct = ((peak - current_price) / peak) * 100
            else:
                drawdown_pct = ((current_price - peak) / peak) * 100
            drawdown_pct = max(Decimal('0'), drawdown_pct)
            
            # Calculate time in position
            time_in_position = datetime.now(timezone.utc) - position.opened_at
            time_score = self._calculate_time_score(time_in_position)
            
            # Calculate volatility score
            volatility_score = await self._calculate_volatility_score(position.symbol)
            
            # Calculate liquidity score
            liquidity_score = await self._calculate_liquidity_score(position.symbol)
            
            # Calculate health scores for each component
            scores = {
                'pnl': self._score_pnl(pnl_pct),
                'drawdown': self._score_drawdown(drawdown_pct),
                'volatility': self._score_volatility(volatility_score),
                'time': time_score,
                'liquidity': liquidity_score
            }
            
            # Calculate weighted health score
            health_score = sum(
                scores[key] * self.health_weights[key] 
                for key in scores
            )
            
            # Determine risk level
            risk_level = self._determine_risk_level(health_score, pnl_pct, drawdown_pct)
            
            # Determine recommended actions
            actions = self._recommend_actions(risk_level, scores, pnl_pct)
            
            # Generate alerts
            alerts = self._generate_alerts(risk_level, pnl_pct, drawdown_pct, time_in_position)
            
            return PositionHealth(
                position_id=position.id,
                symbol=position.symbol,
                health_score=health_score,
                risk_level=risk_level,
                unrealized_pnl=pnl,
                pnl_percentage=pnl_pct,
                time_in_position=time_in_position,
                volatility_score=volatility_score,
                liquidity_score=liquidity_score,
                drawdown=drawdown_pct,
                max_drawdown=self.max_drawdown_pct,
                recommended_actions=actions,
                alerts=alerts
            )
            
        except Exception as e:
            logger.error(f"Failed to calculate position health: {e}")
            # Return critical health on error
            return PositionHealth(
                position_id=position.id,
                symbol=position.symbol,
                health_score=0,
                risk_level=RiskLevel.CRITICAL,
                unrealized_pnl=Decimal('0'),
                pnl_percentage=Decimal('0'),
                time_in_position=timedelta(),
                volatility_score=0,
                liquidity_score=0,
                drawdown=Decimal('0'),
                max_drawdown=self.max_drawdown_pct,
                recommended_actions=[ProtectionAction.EMERGENCY_EXIT],
                alerts=["Health check failed - emergency mode"]
            )
    
    def _score_pnl(self, pnl_pct: Decimal) -> float:
        """Score PnL component (0-100)"""
        
        if pnl_pct >= 5:
            return 100
        elif pnl_pct >= 2:
            return 80 + (float(pnl_pct - 2) / 3) * 20
        elif pnl_pct >= 0:
            return 60 + (float(pnl_pct) / 2) * 20
        elif pnl_pct >= -2:
            return 40 + (float(pnl_pct + 2) / 2) * 20
        elif pnl_pct >= -5:
            return 20 + (float(pnl_pct + 5) / 3) * 20
        else:
            return max(0, 20 + float(pnl_pct + 5) * 2)
    
    def _score_drawdown(self, drawdown_pct: Decimal) -> float:
        """Score drawdown component (0-100)"""
        
        if drawdown_pct <= 0.5:
            return 100
        elif drawdown_pct <= 1:
            return 90
        elif drawdown_pct <= 2:
            return 70
        elif drawdown_pct <= 3:
            return 50
        elif drawdown_pct <= 5:
            return 30
        else:
            return max(0, 30 - float(drawdown_pct - 5) * 5)
    
    def _score_volatility(self, volatility: float) -> float:
        """Score volatility component (0-100)"""
        
        if volatility <= 0.5:
            return 100
        elif volatility <= 1:
            return 80
        elif volatility <= 1.5:
            return 60
        elif volatility <= 2:
            return 40
        else:
            return max(0, 40 - (volatility - 2) * 10)
    
    def _calculate_time_score(self, time_in_position: timedelta) -> float:
        """Score time component (0-100)"""
        
        hours = time_in_position.total_seconds() / 3600
        
        if hours <= 4:
            return 100
        elif hours <= 12:
            return 90
        elif hours <= 24:
            return 70
        elif hours <= 48:
            return 50
        else:
            return max(0, 50 - (hours - 48) * 2)
    
    async def _calculate_volatility_score(self, symbol: str) -> float:
        """Calculate current volatility score"""
        
        try:
            # Get recent candles
            candles = await self.exchange_manager.fetch_ohlcv(
                symbol, timeframe='5m', limit=20
            )
            
            if len(candles) < 2:
                return 1.0
            
            # Calculate returns
            closes = [c[4] for c in candles]
            returns = [(closes[i] - closes[i-1]) / closes[i-1] 
                      for i in range(1, len(closes))]
            
            # Calculate volatility (standard deviation of returns)
            volatility = np.std(returns) * np.sqrt(288)  # Annualized for 5m bars
            
            return volatility * 100  # Convert to percentage
            
        except Exception as e:
            logger.error(f"Failed to calculate volatility: {e}")
            return 1.0
    
    async def _calculate_liquidity_score(self, symbol: str) -> float:
        """Calculate liquidity score based on order book"""
        
        try:
            orderbook = await self.exchange_manager.fetch_order_book(symbol, limit=20)
            
            # Calculate bid-ask spread
            if orderbook['bids'] and orderbook['asks']:
                best_bid = orderbook['bids'][0][0]
                best_ask = orderbook['asks'][0][0]
                spread_pct = ((best_ask - best_bid) / best_bid) * 100
                
                # Calculate depth
                bid_depth = sum(bid[1] for bid in orderbook['bids'][:10])
                ask_depth = sum(ask[1] for ask in orderbook['asks'][:10])
                total_depth = bid_depth + ask_depth
                
                # Score based on spread and depth
                spread_score = max(0, 100 - spread_pct * 50)
                depth_score = min(100, total_depth / 100)  # Normalize
                
                return (spread_score + depth_score) / 2
            
            return 50  # Default if no orderbook
            
        except Exception as e:
            logger.error(f"Failed to calculate liquidity: {e}")
            return 50
    
    def _determine_risk_level(self, 
                             health_score: float,
                             pnl_pct: Decimal,
                             drawdown_pct: Decimal) -> RiskLevel:
        """Determine overall risk level"""
        
        # Emergency conditions
        if (pnl_pct <= -float(self.critical_loss_pct) or 
            drawdown_pct >= float(self.max_drawdown_pct) or
            health_score < 20):
            return RiskLevel.EMERGENCY
        
        # Critical conditions
        if health_score < 30 or pnl_pct <= -2 or drawdown_pct >= 3:
            return RiskLevel.CRITICAL
        
        # High risk
        if health_score < 50 or pnl_pct <= -1 or drawdown_pct >= 2:
            return RiskLevel.HIGH
        
        # Medium risk
        if health_score < 70 or pnl_pct <= 0 or drawdown_pct >= 1:
            return RiskLevel.MEDIUM
        
        return RiskLevel.LOW
    
    def _recommend_actions(self, 
                          risk_level: RiskLevel,
                          scores: Dict[str, float],
                          pnl_pct: Decimal) -> List[ProtectionAction]:
        """Recommend protection actions based on analysis"""
        
        actions = []
        
        if risk_level == RiskLevel.EMERGENCY:
            actions.append(ProtectionAction.EMERGENCY_EXIT)
        elif risk_level == RiskLevel.CRITICAL:
            actions.append(ProtectionAction.FULL_CLOSE)
        elif risk_level == RiskLevel.HIGH:
            actions.append(ProtectionAction.PARTIAL_CLOSE)
            actions.append(ProtectionAction.ADJUST_STOP)
        elif risk_level == RiskLevel.MEDIUM:
            actions.append(ProtectionAction.ADJUST_STOP)
            if pnl_pct > 0:
                actions.append(ProtectionAction.PARTIAL_CLOSE)
        else:
            actions.append(ProtectionAction.MONITOR)
        
        # Add hedge recommendation for high volatility
        if scores.get('volatility', 0) < 40:
            actions.append(ProtectionAction.HEDGE)
        
        return actions
    
    def _generate_alerts(self,
                        risk_level: RiskLevel,
                        pnl_pct: Decimal,
                        drawdown_pct: Decimal,
                        time_in_position: timedelta) -> List[str]:
        """Generate alerts for the position"""
        
        alerts = []
        
        if risk_level in [RiskLevel.CRITICAL, RiskLevel.EMERGENCY]:
            alerts.append(f"⚠️ {risk_level.value.upper()} RISK LEVEL")
        
        if pnl_pct <= -float(self.critical_loss_pct):
            alerts.append(f"🔴 Critical loss: {pnl_pct:.2f}%")
        
        if drawdown_pct >= float(self.max_drawdown_pct):
            alerts.append(f"📉 Maximum drawdown exceeded: {drawdown_pct:.2f}%")
        
        if time_in_position.total_seconds() / 3600 > self.time_limit_hours:
            alerts.append(f"⏰ Position time limit exceeded")
        
        return alerts
    
    async def _setup_initial_protection(self, position: Position, health: PositionHealth):
        """Setup initial protection measures"""
        
        try:
            # Setup stop losses
            await self.stop_loss_manager.setup_position_stops(position)
            
            # Setup trailing stop if profitable
            if health.pnl_percentage > 0:
                await self.trailing_stop_manager.activate_trailing_stop(position)
            
            # Log protection setup
            await self.repository.create_risk_event(
                RiskEvent(
                    position_id=position.id,
                    event_type='protection_started',
                    risk_level=health.risk_level.value,
                    details={
                        'health_score': health.health_score,
                        'actions': [a.value for a in health.recommended_actions]
                    }
                )
            )
            
        except Exception as e:
            logger.error(f"Failed to setup initial protection: {e}")
    
    async def _execute_protection_actions(self, position: Position, health: PositionHealth):
        """Execute recommended protection actions"""
        
        try:
            for action in health.recommended_actions:
                
                if action == ProtectionAction.EMERGENCY_EXIT:
                    await self._emergency_exit_position(position)
                    break
                
                elif action == ProtectionAction.FULL_CLOSE:
                    await self._close_position(position, "Risk limit reached")
                    break
                
                elif action == ProtectionAction.PARTIAL_CLOSE:
                    await self._partial_close_position(position, Decimal('0.5'))
                
                elif action == ProtectionAction.ADJUST_STOP:
                    await self._adjust_stop_loss(position, health)
                
                elif action == ProtectionAction.HEDGE:
                    await self._create_hedge_position(position)
                
                elif action == ProtectionAction.FREEZE:
                    await self._freeze_position(position)
                
            # Update stats
            if health.recommended_actions and action != ProtectionAction.MONITOR:
                self.protection_stats['auto_adjustments'] += 1
            
        except Exception as e:
            logger.error(f"Failed to execute protection actions: {e}")
    
    async def _check_critical_conditions(self, position: Position, current_price: Decimal):
        """Quick check for critical conditions requiring immediate action"""
        
        try:
            entry_price = Decimal(str(position.entry_price))
            
            # Calculate current loss
            if position.side == 'long':
                loss_pct = ((entry_price - current_price) / entry_price) * 100
            else:
                loss_pct = ((current_price - entry_price) / entry_price) * 100
            
            # Emergency exit on critical loss
            if loss_pct >= float(self.critical_loss_pct):
                logger.warning(f"CRITICAL LOSS on {position.symbol}: {loss_pct:.2f}%")
                await self._emergency_exit_position(position)
                return
            
            # Check for unusual price movement
            ticker = await self.exchange_manager.fetch_ticker(position.symbol)
            daily_change = abs(ticker.get('percentage', 0))
            
            if daily_change > 10:  # 10% daily move
                logger.warning(f"Unusual price movement on {position.symbol}: {daily_change:.2f}%")
                await self._tighten_protection(position)
            
        except Exception as e:
            logger.error(f"Critical condition check failed: {e}")
    
    async def _emergency_exit_position(self, position: Position):
        """Emergency market exit with all available methods"""
        
        try:
            logger.error(f"EMERGENCY EXIT triggered for {position.symbol}")
            
            # Cancel all existing orders
            await self.stop_loss_manager.cancel_position_stops(position.id)
            
            # Place market order to close
            result = await self.exchange_manager.close_position(
                position.symbol,
                position.side,
                abs(position.quantity)
            )
            
            if result:
                # Update stats
                self.protection_stats['emergency_exits'] += 1
                
                # Log event
                await self.repository.create_risk_event(
                    RiskEvent(
                        position_id=position.id,
                        event_type='emergency_exit',
                        risk_level='emergency',
                        details={'reason': 'Critical risk threshold exceeded'}
                    )
                )
                
                # Remove from monitoring
                await self.stop_protection(position.id)
            
        except Exception as e:
            logger.error(f"Emergency exit failed: {e}")
            # Try alternative methods...
    
    async def _close_position(self, position: Position, reason: str):
        """Close position with reason logging"""
        
        try:
            result = await self.exchange_manager.close_position(
                position.symbol,
                position.side,
                abs(position.quantity)
            )
            
            if result:
                logger.info(f"Position {position.id} closed: {reason}")
                
                await self.repository.create_risk_event(
                    RiskEvent(
                        position_id=position.id,
                        event_type='position_closed',
                        risk_level='high',
                        details={'reason': reason}
                    )
                )
                
                await self.stop_protection(position.id)
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
    
    async def _partial_close_position(self, position: Position, close_ratio: Decimal):
        """Partially close position"""
        
        try:
            close_size = abs(Decimal(str(position.quantity))) * Decimal(str(close_ratio))
            
            result = await self.exchange_manager.close_position(
                position.symbol,
                position.side,
                close_size
            )
            
            if result:
                logger.info(f"Partially closed {close_ratio*100:.0f}% of position {position.id}")

                # Update position size
                position.quantity = float(Decimal(str(position.quantity)) * (Decimal('1') - close_ratio))  # type: ignore[assignment]
                
        except Exception as e:
            logger.error(f"Failed to partially close position: {e}")
    
    async def _adjust_stop_loss(self, position: Position, health: PositionHealth):
        """Dynamically adjust stop loss based on conditions"""
        
        try:
            # Tighten stop if in profit
            if health.pnl_percentage > 1:
                position_id_str = str(position.id)
                await self.stop_loss_manager.update_stops(
                    position,
                    self.position_peaks[position_id_str]
                )
            
        except Exception as e:
            logger.error(f"Failed to adjust stop loss: {e}")
    
    async def _tighten_protection(self, position: Position):
        """Tighten all protection measures"""
        
        try:
            # Move stops closer
            current_price = self.position_peaks.get(position.id)
            if current_price:
                await self.stop_loss_manager.update_stops(position, current_price)
            
            # Reduce position size if large
            position_qty_decimal = Decimal(str(abs(position.quantity)))
            max_size_decimal = Decimal(str(self.risk_manager.max_position_size))
            threshold = max_size_decimal * Decimal('0.5')
            if position_qty_decimal > threshold:
                await self._partial_close_position(position, Decimal('0.3'))
            
        except Exception as e:
            logger.error(f"Failed to tighten protection: {e}")
    
    async def _create_hedge_position(self, position: Position):
        """Create hedge position to reduce risk"""
        
        # Implementation depends on strategy
        logger.info(f"Hedge recommended for {position.symbol}")
    
    async def _freeze_position(self, position: Position):
        """Freeze position - no new orders"""
        
        self.frozen_positions.add(position.id)
        logger.warning(f"Position {position.id} frozen")
    
    async def _emergency_protection(self, position: Position):
        """Fallback emergency protection"""
        
        try:
            # Place wide stop loss as last resort
            stop_price = Decimal(str(position.entry_price)) * Decimal('0.95')
            
            # DECEMBER 2025 MIGRATION: Use StopLossManager for Algo API
            # Old create_order with type='stop_market' returns error -4120
            from core.stop_loss_manager import StopLossManager
            sl_manager = StopLossManager(
                self.exchange_manager.exchange,
                self.exchange_manager.name
            )
            
            await sl_manager.set_stop_loss(
                symbol=position.symbol,
                side='sell' if position.side == 'long' else 'buy',
                amount=Decimal(str(abs(position.quantity))),
                stop_price=stop_price
            )
            
            logger.warning(f"Emergency protection activated for {position.id}")
            
        except Exception as e:
            logger.error(f"Emergency protection failed: {e}")
    
    async def stop_protection(self, position_id: str):
        """Stop protecting a position"""
        
        if position_id in self.monitored_positions:
            del self.monitored_positions[position_id]
            
        self.position_health.pop(position_id, None)
        self.position_peaks.pop(position_id, None)
        self.frozen_positions.discard(position_id)
        
        logger.info(f"Stopped protection for position {position_id}")
    
    async def get_protection_status(self) -> Dict[str, Any]:
        """Get current protection system status"""
        
        return {
            'monitored_positions': len(self.monitored_positions),
            'emergency_mode': self.emergency_mode,
            'frozen_positions': list(self.frozen_positions),
            'health_summary': {
                pid: {
                    'health_score': health.health_score,
                    'risk_level': health.risk_level.value,
                    'pnl_pct': float(health.pnl_percentage)
                }
                for pid, health in self.position_health.items()
            },
            'protection_stats': self.protection_stats
        }
    
    # WebSocket Event Handlers
    
    async def _handle_position_update(self, data: Dict[str, Any]):
        """Handle position update from WebSocket"""
        
        position_id = data.get('position_id')
        if position_id in self.monitored_positions:
            # Update position data
            position = self.monitored_positions[position_id]
            position.quantity = data.get('quantity', data.get('size', position.quantity))
            position.unrealized_pnl = data.get('unrealized_pnl', position.unrealized_pnl)
    
    async def _handle_price_update(self, data: Dict[str, Any]):
        """Handle price update from WebSocket"""
        
        symbol = data.get('symbol')
        price = Decimal(str(data.get('price', 0)))
        
        # Update peaks for positions with this symbol
        for position_id, position in self.monitored_positions.items():
            if position.symbol == symbol:
                if position.side == 'long':
                    if price > self.position_peaks[position_id]:
                        self.position_peaks[position_id] = price
                else:
                    if price < self.position_peaks[position_id]:
                        self.position_peaks[position_id] = price
    
    async def _handle_order_filled(self, data: Dict[str, Any]):
        """Handle order fill event"""
        
        # Check if it's a stop loss fill
        order_type = data.get('type')
        if order_type in ['stop_market', 'stop_limit']:
            logger.info(f"Stop loss triggered: {data}")
            # Update protection stats
            self.protection_stats['positions_saved'] += 1
    
    async def _handle_risk_alert(self, data: Dict[str, Any]):
        """Handle risk alert from risk manager"""
        
        alert_type = data.get('type')
        
        if alert_type == 'high_volatility':
            # Tighten all protections
            for position in self.monitored_positions.values():
                await self._tighten_protection(position)
        
        elif alert_type == 'low_liquidity':
            # Consider reducing positions
            logger.warning("Low liquidity alert - reviewing positions")