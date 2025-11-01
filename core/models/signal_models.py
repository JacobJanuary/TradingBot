"""
Signal processing models and enums.
Part of signal filtering fix - Phase 1.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class FilterResult(Enum):
    """Result of signal filtering"""
    PASSED = "passed"
    LOW_OI = "low_open_interest"
    LOW_VOLUME = "low_volume"
    DUPLICATE = "duplicate_position"
    OVERHEATED = "price_overheated"
    MARKET_CLOSED = "market_closed"


class ValidationStatus(Enum):
    """Status of signal validation"""
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionStatus(Enum):
    """Status of signal execution"""
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    POSITION_SIZE_ERROR = "position_size_error"


@dataclass
class EnrichedSignal:
    """Signal with additional metadata for filtering"""
    # Original signal data
    signal_id: int
    symbol: str
    exchange: str
    side: str
    entry_price: float
    score_week: float
    score_month: float
    timestamp: datetime

    # Enriched metadata (populated during filtering)
    combined_score: float  # score_week + score_month
    open_interest_usdt: Optional[float] = None
    volume_1h_usdt: Optional[float] = None

    # Filter results
    passed_filters: bool = False
    filter_reason: Optional[FilterResult] = None
    filter_details: Dict[str, Any] = field(default_factory=dict)

    # Execution tracking
    validation_status: Optional[str] = None  # 'pending', 'passed', 'failed'
    execution_status: Optional[str] = None   # 'pending', 'executed', 'failed'
    execution_error: Optional[str] = None

    def calculate_combined_score(self) -> float:
        """Calculate combined score for sorting"""
        self.combined_score = self.score_week + self.score_month
        return self.combined_score

    def to_dict(self) -> Dict:
        """Convert to dict for logging/storage"""
        return {
            'signal_id': self.signal_id,
            'symbol': self.symbol,
            'exchange': self.exchange,
            'combined_score': self.combined_score,
            'passed_filters': self.passed_filters,
            'filter_reason': self.filter_reason.value if self.filter_reason else None,
            'validation_status': self.validation_status,
            'execution_status': self.execution_status
        }