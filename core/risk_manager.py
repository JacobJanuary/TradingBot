"""
Risk Manager for position and portfolio risk management
"""

from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass
from loguru import logger

from database.repository import Repository
from database.models import Position, Order, RiskEvent


class RiskLevel(Enum):
    """Risk severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskViolation:
    """Risk violation record"""
    type: str
    level: RiskLevel
    message: str
    timestamp: datetime


class RiskManager:
    """
    Comprehensive risk management system
    
    Features:
    - Position size limits
    - Daily loss limits
    - Leverage control
    - Correlation analysis
    - Risk scoring
    """
    
    def __init__(self, repository: Repository, config: Dict[str, Any]):
        self.repository = repository
        self.config = config
        
        # Risk parameters
        self.max_position_size = Decimal(str(config.get('max_position_size', 10000)))
        self.max_daily_loss = Decimal(str(config.get('max_daily_loss', 1000)))
        self.max_open_positions = config.get('max_open_positions', 5)
        self.max_leverage = config.get('max_leverage', 10)
        self.max_correlation = config.get('max_correlation', 0.7)
        self.default_stop_loss = Decimal(str(config.get('default_stop_loss', 2.0)))
        self.risk_per_trade = Decimal(str(config.get('risk_per_trade', 1.0)))
        
        # Tracking
        self.violations: List[RiskViolation] = []
        self.daily_pnl = Decimal('0')
        
        logger.info("RiskManager initialized")
    
    async def check_position_limit(self, exchange: str) -> bool:
        """Check if we can open more positions"""
        try:
            positions = await self.repository.get_active_positions(exchange)
            return len(positions) < self.max_open_positions
        except Exception as e:
            logger.error(f"Failed to check position limit: {e}")
            return False
    
    async def check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit has been reached"""
        try:
            daily_pnl = await self.repository.get_daily_pnl()
            return daily_pnl > -self.max_daily_loss
        except Exception as e:
            logger.error(f"Failed to check daily loss limit: {e}")
            return True  # Allow trading on error
    
    # REMOVED: Complex position sizing calculation
    # The system uses fixed position size from config (POSITION_SIZE_USD)
    # See position_manager._calculate_position_size() for actual implementation

    def get_fixed_position_size(self) -> Decimal:
        """Get fixed position size from config"""
        return self.max_position_size  # Uses the configured max as fixed size
    
    async def validate_order(self, order: Order) -> bool:
        """Validate order against risk rules"""
        
        # Check order size
        order_value = Decimal(str(order.size * order.price)) if order.price else Decimal('0')
        if order_value > self.max_position_size:
            logger.warning(f"Order value {order_value} exceeds max position size")
            return False
        
        return True
    
    async def check_leverage(self, leverage: float) -> bool:
        """Check if leverage is within limits"""
        return leverage <= self.max_leverage
    
    async def calculate_portfolio_risk(self) -> Dict[str, Any]:
        """Calculate overall portfolio risk metrics"""
        
        positions = await self.repository.get_active_positions()
        
        total_exposure = Decimal('0')
        unrealized_pnl = Decimal('0')
        
        for position in positions:
            exposure = abs(position.quantity * position.entry_price)
            total_exposure += exposure
            unrealized_pnl += position.unrealized_pnl or Decimal('0')
        
        risk_score = self._calculate_risk_score(
            total_exposure,
            unrealized_pnl,
            len(positions)
        )
        
        return {
            'total_exposure': total_exposure,
            'position_count': len(positions),
            'unrealized_pnl': unrealized_pnl,
            'risk_score': risk_score,
            'risk_level': self.classify_risk_level(risk_score)
        }
    
    def _calculate_risk_score(self,
                             exposure: Decimal,
                             pnl: Decimal,
                             position_count: int) -> float:
        """Calculate risk score 0-100"""

        score: float = 0.0
        
        # Exposure component (40%)
        exposure_ratio = float(exposure / self.max_position_size)
        score += min(40, exposure_ratio * 40)
        
        # Position count component (30%)
        position_ratio = position_count / self.max_open_positions
        score += min(30, position_ratio * 30)
        
        # PnL component (30%)
        if pnl < 0:
            loss_ratio = float(abs(pnl) / self.max_daily_loss)
            score += min(30, loss_ratio * 30)
        
        return score
    
    def classify_risk_level(self, risk_score: float) -> RiskLevel:
        """Classify risk level based on score"""
        
        if risk_score >= 80:
            return RiskLevel.CRITICAL
        elif risk_score >= 60:
            return RiskLevel.HIGH
        elif risk_score >= 40:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    async def check_correlation_risk(self, positions: List[Dict[str, Any]]) -> float:
        """Check correlation between positions"""
        
        # Simplified correlation check
        # In reality, would calculate actual correlations
        
        if not positions:
            return 0.0
        
        # Check if all positions are in same direction
        long_count = sum(1 for p in positions if p.get('side') == 'long')
        short_count = len(positions) - long_count
        
        if long_count == len(positions) or short_count == len(positions):
            return 0.8  # High correlation
        
        return 0.3  # Mixed positions, lower correlation
    
    async def validate_stop_loss(self,
                                side: str,
                                entry_price: Decimal,
                                stop_loss: Decimal) -> bool:
        """Validate stop loss is on correct side of entry"""
        
        if side == 'long':
            return stop_loss < entry_price
        else:
            return stop_loss > entry_price
    
    
    async def emergency_liquidation(self, reason: str) -> Dict[str, Any]:
        """Emergency liquidation of all positions"""
        
        logger.error(f"EMERGENCY LIQUIDATION: {reason}")
        
        positions = await self.repository.get_active_positions()
        closed = 0
        
        for position in positions:
            try:
                # Close position properly
                await self.repository.close_position(
                    position.id,
                    pnl=0,  # Unknown PNL in emergency
                    reason='emergency_liquidation'
                )
                closed += 1
            except Exception as e:
                logger.error(f"Failed to close position {position.id}: {e}")
        
        return {
            'positions_closed': closed,
            'reason': reason
        }
    
    async def record_risk_violation(self, violation: RiskViolation):
        """Record risk violation"""
        
        # Track in memory
        if not hasattr(self, 'violations'):
            self.violations = []
        self.violations.append(violation)
        
        # Save to database
        await self.repository.create_risk_violation(violation)