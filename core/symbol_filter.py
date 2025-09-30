"""
Symbol Filter - Centralized symbol filtering with stop-list and whitelist support
Manages which symbols are allowed for trading based on configuration
"""

import logging
import re
from typing import List, Tuple, Set, Dict, Any

logger = logging.getLogger(__name__)


class SymbolFilter:
    """
    Centralized symbol filtering with stop-list, whitelist and pattern support

    Features:
    - Stop-list: symbols that are NEVER traded
    - Whitelist: if enabled, ONLY these symbols are traded
    - Pattern exclusion: exclude symbols matching patterns (e.g., *UP, *DOWN)
    - Special exclusions: index symbols, stablecoin pairs, leveraged tokens
    """

    def __init__(self, config):
        """
        Initialize symbol filter with configuration

        Args:
            config: Configuration object with filtering parameters
        """
        self.config = config

        # Load stop-list symbols
        self.stoplist_symbols = self._load_stoplist_symbols()

        # Whitelist configuration
        self.use_whitelist = self._get_bool_config('USE_SYMBOL_WHITELIST', False)
        self.whitelist_symbols = self._load_whitelist_symbols() if self.use_whitelist else set()

        # Pattern-based exclusions
        self.excluded_patterns = self._load_excluded_patterns()

        # Volume filtering
        self.min_volume_usd = float(getattr(config, 'min_symbol_volume_usd', 0) or 0)

        # Statistics
        self.stats = {
            'total_checked': 0,
            'allowed': 0,
            'blocked_stoplist': 0,
            'blocked_whitelist': 0,
            'blocked_pattern': 0,
            'blocked_special': 0,
            'blocked_volume': 0
        }

        self._log_configuration()

    def _get_bool_config(self, key: str, default: bool = False) -> bool:
        """Get boolean configuration value"""
        value = getattr(self.config, key.lower(), None)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return bool(value)

    def _load_stoplist_symbols(self) -> Set[str]:
        """
        Load stop-list symbols from configuration

        Supports formats:
        - Comma-separated: "BTCDOMUSDT,USDCUSDT,BUSDUSDT"
        - Space-separated: "BTCDOMUSDT USDCUSDT BUSDUSDT"
        - Semicolon-separated: "BTCDOMUSDT;USDCUSDT;BUSDUSDT"
        """
        stoplist_str = getattr(self.config, 'stoplist_symbols', '') or ''

        if not stoplist_str:
            return set()

        # Determine delimiter
        if ',' in stoplist_str:
            delimiter = ','
        elif ';' in stoplist_str:
            delimiter = ';'
        else:
            delimiter = ' '

        # Parse and clean
        symbols = {
            symbol.strip().upper()
            for symbol in stoplist_str.split(delimiter)
            if symbol.strip()
        }

        return symbols

    def _load_whitelist_symbols(self) -> Set[str]:
        """
        Load whitelist symbols (if whitelist mode is enabled)
        """
        whitelist_str = getattr(self.config, 'whitelist_symbols', '') or ''

        if not whitelist_str:
            return set()

        # Same parsing logic as stoplist
        if ',' in whitelist_str:
            delimiter = ','
        elif ';' in whitelist_str:
            delimiter = ';'
        else:
            delimiter = ' '

        symbols = {
            symbol.strip().upper()
            for symbol in whitelist_str.split(delimiter)
            if symbol.strip()
        }

        return symbols

    def _load_excluded_patterns(self) -> List[re.Pattern]:
        """
        Load and compile exclusion patterns
        Examples: *UP, *DOWN, *3S, *3L (leveraged tokens)
        """
        patterns_str = getattr(self.config, 'excluded_patterns', '') or ''

        if not patterns_str:
            return []

        patterns = []
        for pattern in patterns_str.split(','):
            pattern = pattern.strip()
            if pattern:
                # Convert wildcard to regex
                regex_pattern = pattern.replace('*', '.*')
                regex_pattern = f"^{regex_pattern}$"
                try:
                    compiled = re.compile(regex_pattern, re.IGNORECASE)
                    patterns.append(compiled)
                except re.error as e:
                    logger.warning(f"Invalid pattern '{pattern}': {e}")

        return patterns

    def _log_configuration(self):
        """Log filter configuration"""
        logger.info("🔍 Symbol Filter initialized:")
        logger.info(f"  • Stop-list: {len(self.stoplist_symbols)} symbols")

        if self.stoplist_symbols:
            symbols_preview = list(self.stoplist_symbols)[:5]
            if len(self.stoplist_symbols) > 5:
                logger.info(f"    Excluded: {', '.join(symbols_preview)}... (+{len(self.stoplist_symbols)-5} more)")
            else:
                logger.info(f"    Excluded: {', '.join(symbols_preview)}")

        if self.use_whitelist:
            logger.info(f"  • Whitelist: {len(self.whitelist_symbols)} symbols (ENABLED)")
            if self.whitelist_symbols:
                symbols_preview = list(self.whitelist_symbols)[:5]
                if len(self.whitelist_symbols) > 5:
                    logger.info(f"    Allowed: {', '.join(symbols_preview)}... (+{len(self.whitelist_symbols)-5} more)")
                else:
                    logger.info(f"    Allowed: {', '.join(symbols_preview)}")

        if self.excluded_patterns:
            logger.info(f"  • Exclusion patterns: {len(self.excluded_patterns)}")
            for pattern in self.excluded_patterns[:3]:
                logger.info(f"    Pattern: {pattern.pattern}")

        if self.min_volume_usd > 0:
            logger.info(f"  • Min volume: ${self.min_volume_usd:,.0f} USD")

    def is_symbol_allowed(self, symbol: str, check_volume: bool = False) -> Tuple[bool, str]:
        """
        Check if a symbol is allowed for trading

        Args:
            symbol: Symbol to check
            check_volume: Whether to check trading volume

        Returns:
            tuple: (is_allowed, reason)
        """
        if not symbol:
            return False, "Empty symbol"

        symbol = symbol.upper()
        self.stats['total_checked'] += 1

        # 1. Check stop-list (highest priority)
        if symbol in self.stoplist_symbols:
            self.stats['blocked_stoplist'] += 1
            return False, f"Symbol in stop-list"

        # 2. Check whitelist (if enabled)
        if self.use_whitelist and symbol not in self.whitelist_symbols:
            self.stats['blocked_whitelist'] += 1
            return False, f"Symbol not in whitelist"

        # 3. Check exclusion patterns
        for pattern in self.excluded_patterns:
            if pattern.match(symbol):
                self.stats['blocked_pattern'] += 1
                return False, f"Symbol matches excluded pattern: {pattern.pattern}"

        # 4. Check special exclusions
        special_reason = self._check_special_exclusions(symbol)
        if special_reason:
            self.stats['blocked_special'] += 1
            return False, special_reason

        # 5. Volume check (if requested and available)
        if check_volume and self.min_volume_usd > 0:
            volume = self._get_symbol_volume(symbol)
            if volume < self.min_volume_usd:
                self.stats['blocked_volume'] += 1
                return False, f"Volume ${volume:,.0f} below minimum ${self.min_volume_usd:,.0f}"

        self.stats['allowed'] += 1
        return True, "OK"

    def _check_special_exclusions(self, symbol: str) -> str:
        """
        Check for special types of symbols that should be excluded

        Returns:
            str: Reason for exclusion, or empty string if allowed
        """
        # Index symbols
        if 'DOM' in symbol or 'INDEX' in symbol:
            return "Index symbol (not tradeable)"

        # Stablecoin pairs (low volatility)
        stables = ['USDT', 'USDC', 'BUSD', 'TUSD', 'DAI', 'USDP', 'GUSD']

        # Check if it's a pair of two stablecoins
        for stable1 in stables:
            for stable2 in stables:
                if stable1 != stable2:
                    if symbol == f"{stable1}{stable2}" or symbol == f"{stable2}{stable1}":
                        return "Stablecoin pair (low volatility)"

        # Leveraged tokens (dangerous for spot trading)
        leveraged_suffixes = ['UP', 'DOWN', 'BULL', 'BEAR', '2L', '3L', '2S', '3S']
        for suffix in leveraged_suffixes:
            if symbol.endswith(suffix):
                return f"Leveraged token ({suffix})"

        # Delisted symbols
        delisted_str = getattr(self.config, 'delisted_symbols', '') or ''
        if delisted_str:
            delisted = {s.strip().upper() for s in delisted_str.split(',') if s.strip()}
            if symbol in delisted:
                return "Delisted symbol"

        return ""

    def _get_symbol_volume(self, symbol: str) -> float:
        """
        Get 24h trading volume for symbol

        Note: This is a placeholder. Should be implemented with actual exchange API
        """
        # TODO: Implement actual volume fetching from exchange
        return float('inf')  # For now, assume all symbols have sufficient volume

    def filter_symbols(self, symbols: List[str]) -> List[str]:
        """
        Filter a list of symbols

        Args:
            symbols: List of symbols to filter

        Returns:
            List of allowed symbols
        """
        allowed_symbols = []
        blocked_reasons = {}

        for symbol in symbols:
            is_allowed, reason = self.is_symbol_allowed(symbol)

            if is_allowed:
                allowed_symbols.append(symbol)
            else:
                if reason not in blocked_reasons:
                    blocked_reasons[reason] = []
                blocked_reasons[reason].append(symbol)

        # Log filtering results
        if blocked_reasons:
            logger.info(f"📊 Symbol filtering: {len(symbols)} → {len(allowed_symbols)} symbols")
            for reason, blocked_symbols in blocked_reasons.items():
                if len(blocked_symbols) <= 3:
                    logger.debug(f"  • {reason}: {', '.join(blocked_symbols)}")
                else:
                    logger.debug(f"  • {reason}: {', '.join(blocked_symbols[:3])}... (+{len(blocked_symbols)-3} more)")

        return allowed_symbols

    def add_to_stoplist(self, symbols: List[str]):
        """
        Add symbols to stop-list at runtime

        Args:
            symbols: List of symbols to add
        """
        added = set()
        for symbol in symbols:
            symbol = symbol.upper().strip()
            if symbol and symbol not in self.stoplist_symbols:
                self.stoplist_symbols.add(symbol)
                added.add(symbol)

        if added:
            logger.info(f"Added {len(added)} symbols to stop-list: {', '.join(sorted(added))}")

    def remove_from_stoplist(self, symbols: List[str]):
        """
        Remove symbols from stop-list at runtime

        Args:
            symbols: List of symbols to remove
        """
        removed = set()
        for symbol in symbols:
            symbol = symbol.upper().strip()
            if symbol in self.stoplist_symbols:
                self.stoplist_symbols.remove(symbol)
                removed.add(symbol)

        if removed:
            logger.info(f"Removed {len(removed)} symbols from stop-list: {', '.join(sorted(removed))}")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get filtering statistics

        Returns:
            Dictionary with statistics
        """
        return {
            **self.stats,
            'stoplist_count': len(self.stoplist_symbols),
            'whitelist_enabled': self.use_whitelist,
            'whitelist_count': len(self.whitelist_symbols) if self.use_whitelist else 0,
            'pattern_count': len(self.excluded_patterns),
            'min_volume_usd': self.min_volume_usd,
            'effectiveness': (self.stats['blocked_stoplist'] + self.stats['blocked_pattern'] +
                            self.stats['blocked_special']) / max(1, self.stats['total_checked']) * 100
        }

    def reset_statistics(self):
        """Reset statistics counters"""
        self.stats = {
            'total_checked': 0,
            'allowed': 0,
            'blocked_stoplist': 0,
            'blocked_whitelist': 0,
            'blocked_pattern': 0,
            'blocked_special': 0,
            'blocked_volume': 0
        }