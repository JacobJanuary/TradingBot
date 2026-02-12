"""
Composite Strategy Loader & Signal Matcher

Loads trading rules from composite_strategy.json and matches incoming signals
to the appropriate strategy parameters based on score range + filters.

Based on: TRADING_BOT_ALGORITHM_SPEC.md §2 (Strategy Loading & Matching)
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Commission rate (taker fee)
COMMISSION_PCT = 0.04  # 0.04%

# Smart Timeout v2.0 constants (2026-02-12)
SMART_TIMEOUT_THRESHOLD = 5          # Min score to extend (out of 10)
SMART_TIMEOUT_EXTENSION_SEC = 1800   # 30 minutes per extension
SMART_TIMEOUT_MAX_EXTENSIONS = 3     # Hard cap = 1.5h total
SMART_TIMEOUT_RECHECK_SEC = 300      # Strength recheck interval (5min)
SMART_TIMEOUT_RSI_OVERSOLD = 30      # RSI below = oversold (+2 pts)
SMART_TIMEOUT_RSI_OVERBOUGHT = 70    # RSI above = overbought (veto)
SMART_TIMEOUT_VOL_ZSCORE_MIN = 2.0   # Volume z-score threshold (+1 pt)
SMART_TIMEOUT_PAIR_DUMP_PCT = -2.0   # 15min dump threshold (+1 pt)


@dataclass
class ScoreFilter:
    """Filter criteria for signal matching (§2.2)"""
    score_min: float
    score_max: float
    rsi_min: float = 0
    vol_min: float = 0
    oi_min: float = 0


@dataclass
class StrategyParams:
    """Trading parameters for matched strategy (§3)"""
    leverage: int = 10
    sl_pct: float = 3.0
    delta_window: int = 3600
    threshold_mult: float = 1.0
    base_activation: float = 10.0
    base_callback: float = 3.0
    base_reentry_drop: float = 5.0
    base_cooldown: int = 300
    max_reentry_hours: float = 4
    max_position_hours: float = 24


@dataclass
class DerivedConstants:
    """Computed constants from strategy params (§3.1)"""
    max_reentry_seconds: int
    max_position_seconds: int
    liquidation_threshold: float  # 100 / leverage
    commission_cost: float        # COMMISSION_PCT * 2 * leverage

    @staticmethod
    def from_params(params: StrategyParams) -> 'DerivedConstants':
        return DerivedConstants(
            max_reentry_seconds=int(params.max_reentry_hours * 3600),
            max_position_seconds=int(params.max_position_hours * 3600),
            liquidation_threshold=100.0 / params.leverage,
            commission_cost=COMMISSION_PCT * 2 * params.leverage,
        )


@dataclass
class StrategyRule:
    """One rule from composite_strategy.json"""
    priority: int
    score_range: str
    filter: ScoreFilter
    strategy: StrategyParams
    consensus_score: float = 0
    expert_scores: Dict[str, float] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)


class CompositeStrategy:
    """
    Loads composite_strategy.json and matches signals to strategy rules.
    
    Usage:
        cs = CompositeStrategy("composite_strategy.json")
        params = cs.match_signal(score=250, rsi=75, vol_zscore=12, oi_delta=5)
        if params:
            derived = DerivedConstants.from_params(params)
            # proceed with trading
    """

    def __init__(self, json_path: str):
        self.version: str = ""
        self.rules: List[StrategyRule] = []
        self.total_expected_pnl: float = 0
        self.avg_win_rate: float = 0
        self.avg_pnl_per_trade: float = 0

        self._load(json_path)

    def _load(self, json_path: str):
        """Load and parse composite_strategy.json"""
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Strategy file not found: {json_path}")

        with open(path, 'r') as f:
            data = json.load(f)

        self.version = data.get('version', 'unknown')
        self.total_expected_pnl = data.get('total_expected_pnl', 0)
        self.avg_win_rate = data.get('avg_win_rate', 0)
        self.avg_pnl_per_trade = data.get('avg_pnl_per_trade', 0)

        # Parse rules
        for rule_data in data.get('rules', []):
            filt = rule_data.get('filter', {})
            strat = rule_data.get('strategy', {})

            rule = StrategyRule(
                priority=rule_data.get('priority', 0),
                score_range=rule_data.get('score_range', ''),
                consensus_score=rule_data.get('consensus_score', 0),
                expert_scores=rule_data.get('expert_scores', {}),
                filter=ScoreFilter(
                    score_min=filt.get('score_min', 0),
                    score_max=filt.get('score_max', 9999),
                    rsi_min=filt.get('rsi_min', 0),
                    vol_min=filt.get('vol_min', 0),
                    oi_min=filt.get('oi_min', 0),
                ),
                strategy=StrategyParams(
                    leverage=strat.get('leverage', 10),
                    sl_pct=strat.get('sl_pct', 3.0),
                    delta_window=strat.get('delta_window', 3600),
                    threshold_mult=strat.get('threshold_mult', 1.0),
                    base_activation=strat.get('base_activation', 10.0),
                    base_callback=strat.get('base_callback', 3.0),
                    base_reentry_drop=strat.get('base_reentry_drop', 5.0),
                    base_cooldown=strat.get('base_cooldown', 300),
                    max_reentry_hours=strat.get('max_reentry_hours', 4),
                    max_position_hours=strat.get('max_position_hours', 24),
                ),
                metrics=rule_data.get('metrics', {}),
            )
            self.rules.append(rule)

        # Sort by priority (ascending = highest priority first)
        self.rules.sort(key=lambda r: r.priority)

        logger.info(
            f"Loaded composite strategy v{self.version}: "
            f"{len(self.rules)} rules, "
            f"expected PnL={self.total_expected_pnl}, "
            f"avg WR={self.avg_win_rate:.1%}"
        )

    def match_signal(self, score: float, rsi: float = 0.0,
                     vol_zscore: float = 0.0, oi_delta: float = 0.0) -> Optional[StrategyParams]:
        """
        Match signal to strategy rule (§2.2).
        
        Checks ALL 4 filters per spec:
        1. Score range [score_min, score_max)
        2. RSI >= rsi_min
        3. Volume z-score >= vol_min
        4. OI delta >= oi_min
        
        Iterates rules by priority. Returns first match.
        
        Args:
            score: Signal total_score
            rsi: Signal RSI value
            vol_zscore: Signal volume z-score
            oi_delta: Signal OI delta percentage
            
        Returns:
            StrategyParams if matched, None if no rule applies
        """
        for rule in self.rules:
            f = rule.filter

            # Check score range
            if not (f.score_min <= score < f.score_max):
                continue

            # §2.2: Check RSI filter
            if rsi < f.rsi_min:
                logger.debug(
                    f"Rule #{rule.priority} [{rule.score_range}]: "
                    f"rsi={rsi:.1f} < rsi_min={f.rsi_min}, skip"
                )
                continue

            # §2.2: Check volume filter
            if vol_zscore < f.vol_min:
                logger.debug(
                    f"Rule #{rule.priority} [{rule.score_range}]: "
                    f"vol={vol_zscore:.1f} < vol_min={f.vol_min}, skip"
                )
                continue

            # §2.2: Check OI delta filter
            if oi_delta < f.oi_min:
                logger.debug(
                    f"Rule #{rule.priority} [{rule.score_range}]: "
                    f"oi={oi_delta:.1f} < oi_min={f.oi_min}, skip"
                )
                continue

            # All filters passed
            logger.info(
                f"✅ Signal MATCHED rule #{rule.priority} [{rule.score_range}]: "
                f"score={score}, rsi={rsi:.1f}, vol={vol_zscore:.1f}, oi={oi_delta:.1f} → "
                f"lev={rule.strategy.leverage}, SL={rule.strategy.sl_pct}%, "
                f"TS act={rule.strategy.base_activation}%/cb={rule.strategy.base_callback}%"
            )
            return rule.strategy

        # No match
        logger.debug(
            f"Signal score={score}, rsi={rsi:.1f}, vol={vol_zscore:.1f}, "
            f"oi={oi_delta:.1f} did not match any rule"
        )
        return None

    def get_rule_for_score(self, score: float) -> Optional[StrategyRule]:
        """Get the full rule (including metrics) for a score value."""
        for rule in self.rules:
            if rule.filter.score_min <= score < rule.filter.score_max:
                return rule
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get strategy summary stats."""
        return {
            'version': self.version,
            'rules_count': len(self.rules),
            'score_ranges': [r.score_range for r in self.rules],
            'total_expected_pnl': self.total_expected_pnl,
            'avg_win_rate': self.avg_win_rate,
            'avg_pnl_per_trade': self.avg_pnl_per_trade,
        }
