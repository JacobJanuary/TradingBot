"""
Trading Bot Configuration
ALL settings from .env file ONLY - NO YAML/JSON configs!
"""
import os
import logging
from dataclasses import dataclass
from typing import Dict, Optional
from decimal import Decimal
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env file IMMEDIATELY
load_dotenv(override=True)


@dataclass
class ExchangeConfig:
    """Exchange configuration from .env ONLY"""
    name: str
    api_key: str
    api_secret: str
    enabled: bool = True
    testnet: bool = False
    rate_limit: bool = True

    # WebSocket settings with defaults
    ws_heartbeat_interval: int = 30
    ws_timeout: int = 60
    ws_reconnect_delay: int = 5
    ws_max_reconnect_attempts: int = 10


@dataclass
class TradingConfig:
    """Trading parameters from .env ONLY"""
    # Position sizing
    position_size_usd: Decimal = Decimal('6')
    min_position_size_usd: Decimal = Decimal('5')
    max_position_size_usd: Decimal = Decimal('10000')
    positions_smart_limit: int = 30  # Max positions for dynamic sizing
    max_positions: int = 150
    max_exposure_usd: Decimal = Decimal('99000')

    # Risk management
    stop_loss_percent: Decimal = Decimal('4.0')
    trailing_activation_percent: Decimal = Decimal('2.0')
    trailing_callback_percent: Decimal = Decimal('0.5')

    # Leverage control (RESTORED 2025-10-25)
    leverage: int = 1                     # Default leverage for all positions
    max_leverage: int = 2                 # Maximum allowed leverage (safety limit)
    auto_set_leverage: bool = True        # Auto-set leverage before opening position

    # Position sizing mode
    use_smart_limit: bool = True          # True = dynamic (balance/POSITIONS_SMART_LIMIT), False = fixed (POSITION_SIZE_USD)

    # Smart Entry configuration (Hunter pattern)
    smart_entry_enabled: bool = False               # Master toggle: True = Smart Entry Hunter, False = immediate entry
    smart_entry_timeout_minutes: int = 30           # How long to search for ideal entry point
    smart_entry_check_interval_seconds: int = 4     # How often to check conditions (lower = more precise, higher = fewer API calls)
    max_concurrent_hunters: int = 30                # Maximum simultaneous Hunter tasks
    
    # Smart Entry thresholds
    hunter_mfi_momentum_threshold: float = 50.0     # MFI threshold for Momentum Breakout scenario
    hunter_mfi_reversion_threshold: float = 30.0    # MFI threshold for Mean Reversion scenario
    hunter_vwap_tolerance_percent: float = 0.2      # VWAP touch tolerance for Mean Reversion (±%)
    hunter_volume_spike_multiplier: float = 2.0     # Volume multiplier for Momentum Breakout (2.0 = 2x average)

    # Trailing Stop SL Update settings (Freqtrade-inspired)
    trailing_min_update_interval_seconds: int = 30  # Min 30s between SL updates
    # ✅ FIX #2.1: Lower threshold from 0.05% to 0.01% for more responsive TS updates
    trailing_min_improvement_percent: Decimal = Decimal('0.01')  # Update only if >= 0.01% improvement
    trailing_alert_if_unprotected_window_ms: int = 300  # Alert if unprotected window > 300ms

    # Aged positions
    max_position_age_hours: int = 3
    aged_grace_period_hours: int = 3
    aged_loss_step_percent: Decimal = Decimal('0.5')
    aged_max_loss_percent: Decimal = Decimal('10.0')
    aged_acceleration_factor: Decimal = Decimal('1.2')
    aged_check_interval_minutes: int = 60
    commission_percent: Decimal = Decimal('0.05')

    # Signal filtering
    max_spread_percent: Decimal = Decimal('0.5')

    # Execution
    signal_time_window_minutes: int = 10

    # NOTE: Fallback only - per-exchange limits from DB (trading_params table) take precedence
    # Used only when DB params unavailable (signal_processor_websocket.py:591,683)
    max_trades_per_15min: int = 5

    # Per-exchange signal selection buffer (fixed value replaces magic number "3")
    # Determines how many extra signals to select before validation/filtering
    # Example: max_trades=6, buffer_fixed=3 → select 9 signals, validate, take top 6
    # Used in signal_processor_websocket.py lines 621, 642, 661, 705, 718
    signal_buffer_fixed: int = 3

    # Advanced signal filters (market quality validation)
    signal_min_open_interest_usdt: int = 1_000_000  # Minimum OI in USDT
    signal_min_volume_1h_usdt: int = 50_000         # Minimum 1h volume in USDT
    signal_max_price_change_5min_percent: float = 4.0  # Max 5min price change %

    # Filter enable/disable switches
    signal_filter_oi_enabled: bool = True           # Enable OI filter
    signal_filter_volume_enabled: bool = True       # Enable volume filter
    signal_filter_price_change_enabled: bool = True # Enable price change filter


@dataclass
class TradingSafetyConstants:
    """
    Trading safety constants - configurable safety margins

    These are technical constants that rarely change but should be
    configurable for advanced users.
    """
    # Stop Loss Safety Margins
    STOP_LOSS_SAFETY_MARGIN_PERCENT: Decimal = Decimal('0.5')  # 0.5% margin

    # Position Size Tolerance
    POSITION_SIZE_TOLERANCE_PERCENT: Decimal = Decimal('10.0')  # 10% over budget allowed

    # Price Update Thresholds
    PRICE_UPDATE_THRESHOLD_PERCENT: Decimal = Decimal('0.5')  # 0.5% price change to update

    # Minimum Balance Threshold
    MINIMUM_ACTIVE_BALANCE_USD: Decimal = Decimal('10.0')  # $10 minimum to consider active

    # Price Precision
    DEFAULT_PRICE_PRECISION: int = 8  # Default decimal precision for prices

    # Tick Size Defaults
    DEFAULT_MIN_QUANTITY: Decimal = Decimal('0.001')
    DEFAULT_TICK_SIZE: Decimal = Decimal('0.01')
    DEFAULT_STEP_SIZE: Decimal = Decimal('0.001')


@dataclass
class DatabaseConfig:
    """Database configuration from .env ONLY"""
    host: str = 'localhost'
    port: int = 5432
    database: str = 'fox_crypto'
    user: str = 'evgeniyyanvarskiy'
    password: str = ''
    pool_size: int = 10
    max_overflow: int = 20


class Config:
    """
    Main configuration class
    ONLY reads from .env file - NO YAML/JSON configs!
    """

    def __init__(self):
        """Initialize configuration from .env ONLY"""
        # Load .env if not already loaded
        load_dotenv(override=True)

        # Initialize configs
        self.exchanges = self._init_exchanges()
        self.trading = self._init_trading()
        self.safety = self._init_safety_constants()  # Phase 3: Safety constants (with .env override)
        self.database = self._init_database()

        # System settings
        self.debug = os.getenv('DEBUG', 'false').lower() == 'true'
        self.environment = os.getenv('ENVIRONMENT', 'production')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')

        # Symbol filtering - FIX: 2025-10-03 - Add missing STOPLIST_SYMBOLS loading
        self.stoplist_symbols = os.getenv('STOPLIST_SYMBOLS', '')

        # Log configuration source
        logger.info("Configuration loaded from .env file ONLY")
        logger.info(f"Environment: {self.environment}")
        logger.info(f"Debug mode: {self.debug}")

    def _init_exchanges(self) -> Dict[str, ExchangeConfig]:
        """Initialize exchange configurations from .env ONLY"""
        exchanges = {}

        # Binance configuration
        binance_trade = os.getenv('BINANCE_TRADE', 'true').lower() == 'true'
        if not binance_trade:
            exchanges['binance'] = ExchangeConfig(
                name='binance',
                api_key='disabled',
                api_secret='disabled',
                enabled=False
            )
            logger.info("Binance trading disabled via BINANCE_TRADE=false")
        else:
            binance_key = os.getenv('BINANCE_API_KEY')
            binance_secret = os.getenv('BINANCE_API_SECRET')

            if binance_key and binance_secret:
                exchanges['binance'] = ExchangeConfig(
                    name='binance',
                    api_key=binance_key,
                    api_secret=binance_secret,
                    enabled=True,  # Always enabled if keys present
                    testnet=os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'
                )
                logger.info(f"Binance configured: testnet={exchanges['binance'].testnet}")

        # Bybit configuration
        bybit_trade = os.getenv('BYBIT_TRADE', 'true').lower() == 'true'
        if not bybit_trade:
            exchanges['bybit'] = ExchangeConfig(
                name='bybit',
                api_key='disabled',
                api_secret='disabled',
                enabled=False
            )
            logger.info("Bybit trading disabled via BYBIT_TRADE=false")
        else:
            bybit_key = os.getenv('BYBIT_API_KEY')
            bybit_secret = os.getenv('BYBIT_API_SECRET')

            if bybit_key and bybit_secret:
                exchanges['bybit'] = ExchangeConfig(
                    name='bybit',
                    api_key=bybit_key,
                    api_secret=bybit_secret,
                    enabled=True,  # Always enabled if keys present
                    testnet=os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'
                )
                logger.info(f"Bybit configured: testnet={exchanges['bybit'].testnet}")
                logger.info(f"Bybit API Key (first 4 chars): {bybit_key[:4]}...")

        if not exchanges:
            logger.warning("No exchange API keys found in .env file!")

        return exchanges

    def _init_trading(self) -> TradingConfig:
        """Initialize trading configuration from .env ONLY"""
        config = TradingConfig()

        # Position sizing
        if val := os.getenv('POSITION_SIZE_USD'):
            config.position_size_usd = Decimal(val)
        if val := os.getenv('MIN_POSITION_SIZE_USD'):
            config.min_position_size_usd = Decimal(val)
        if val := os.getenv('MAX_POSITION_SIZE_USD'):
            config.max_position_size_usd = Decimal(val)
        if val := os.getenv('POSITIONS_SMART_LIMIT'):
            config.positions_smart_limit = int(val)
        if val := os.getenv('MAX_POSITIONS'):
            config.max_positions = int(val)
        if val := os.getenv('MAX_EXPOSURE_USD'):
            config.max_exposure_usd = Decimal(val)

        # Risk management
        if val := os.getenv('STOP_LOSS_PERCENT'):
            config.stop_loss_percent = Decimal(val)
        if val := os.getenv('TRAILING_ACTIVATION_PERCENT'):
            config.trailing_activation_percent = Decimal(val)
        if val := os.getenv('TRAILING_CALLBACK_PERCENT'):
            config.trailing_callback_percent = Decimal(val)

        # Trailing Stop SL Update settings
        if val := os.getenv('TRAILING_MIN_UPDATE_INTERVAL_SECONDS'):
            config.trailing_min_update_interval_seconds = int(val)
        if val := os.getenv('TRAILING_MIN_IMPROVEMENT_PERCENT'):
            config.trailing_min_improvement_percent = Decimal(val)
        if val := os.getenv('TRAILING_ALERT_IF_UNPROTECTED_WINDOW_MS'):
            config.trailing_alert_if_unprotected_window_ms = int(val)

        # Leverage control (RESTORED 2025-10-25)
        if val := os.getenv('LEVERAGE'):
            config.leverage = int(val)
        if val := os.getenv('MAX_LEVERAGE'):
            config.max_leverage = int(val)
        if val := os.getenv('AUTO_SET_LEVERAGE'):
            config.auto_set_leverage = val.lower() == 'true'

        # Aged positions
        if val := os.getenv('MAX_POSITION_AGE_HOURS'):
            config.max_position_age_hours = int(val)
        if val := os.getenv('AGED_GRACE_PERIOD_HOURS'):
            config.aged_grace_period_hours = int(val)
        if val := os.getenv('AGED_LOSS_STEP_PERCENT'):
            config.aged_loss_step_percent = Decimal(val)
        if val := os.getenv('AGED_MAX_LOSS_PERCENT'):
            config.aged_max_loss_percent = Decimal(val)
        if val := os.getenv('AGED_ACCELERATION_FACTOR'):
            config.aged_acceleration_factor = Decimal(val)
        if val := os.getenv('AGED_CHECK_INTERVAL_MINUTES'):
            config.aged_check_interval_minutes = int(val)
        if val := os.getenv('COMMISSION_PERCENT'):
            config.commission_percent = Decimal(val)

        # Signal filtering
        if val := os.getenv('MAX_SPREAD_PERCENT'):
            config.max_spread_percent = Decimal(val)

        # FIX: 2025-10-03 - Добавлена загрузка MAX_TRADES_PER_15MIN из .env
        if val := os.getenv('MAX_TRADES_PER_15MIN'):
            config.max_trades_per_15min = int(val)
        if val := os.getenv('SIGNAL_BUFFER_FIXED'):
            config.signal_buffer_fixed = int(val)

        # Position sizing mode
        if val := os.getenv('USE_SMART_LIMIT'):
            config.use_smart_limit = val.lower() == 'true'

        # FIX: 2025-10-30 - Добавлена загрузка SIGNAL фильтров из .env
        if val := os.getenv('SIGNAL_MIN_OPEN_INTEREST_USDT'):
            config.signal_min_open_interest_usdt = int(val)
        if val := os.getenv('SIGNAL_MIN_VOLUME_1H_USDT'):
            config.signal_min_volume_1h_usdt = int(val)
        if val := os.getenv('SIGNAL_MAX_PRICE_CHANGE_5MIN_PERCENT'):
            config.signal_max_price_change_5min_percent = float(val)
        if val := os.getenv('SIGNAL_FILTER_OI_ENABLED'):
            config.signal_filter_oi_enabled = val.lower() == 'true'
        if val := os.getenv('SIGNAL_FILTER_VOLUME_ENABLED'):
            config.signal_filter_volume_enabled = val.lower() == 'true'
        if val := os.getenv('SIGNAL_FILTER_PRICE_CHANGE_ENABLED'):
            config.signal_filter_price_change_enabled = val.lower() == 'true'

        # Smart Entry Configuration (NEW)
        if val := os.getenv('SMART_ENTRY'):
            config.smart_entry_enabled = val.lower() == 'true'
        if val := os.getenv('SMART_ENTRY_TIMEOUT_MINUTES'):
            config.smart_entry_timeout_minutes = int(val)
        if val := os.getenv('SMART_ENTRY_CHECK_INTERVAL_SECONDS'):
            config.smart_entry_check_interval_seconds = int(val)
        if val := os.getenv('MAX_CONCURRENT_HUNTERS'):
            config.max_concurrent_hunters = int(val)
        if val := os.getenv('HUNTER_MFI_MOMENTUM_THRESHOLD'):
            config.hunter_mfi_momentum_threshold = float(val)
        if val := os.getenv('HUNTER_MFI_REVERSION_THRESHOLD'):
            config.hunter_mfi_reversion_threshold = float(val)
        if val := os.getenv('HUNTER_VWAP_TOLERANCE_PERCENT'):
            config.hunter_vwap_tolerance_percent = float(val)
        if val := os.getenv('HUNTER_VOLUME_SPIKE_MULTIPLIER'):
            config.hunter_volume_spike_multiplier = float(val)

        logger.info(f"Trading config loaded: position_size=${config.position_size_usd}")
        logger.info(f"Wave limits: max_trades={config.max_trades_per_15min} (fallback), buffer_fixed=+{config.signal_buffer_fixed}")
        logger.info(f"Leverage config: leverage={config.leverage}x, max={config.max_leverage}x, auto_set={config.auto_set_leverage}")
        logger.info(f"Position sizing mode: {'DYNAMIC (smart limit)' if config.use_smart_limit else 'FIXED'}")
        logger.info(f"Smart Entry: {'ENABLED' if config.smart_entry_enabled else 'DISABLED'}")
        if config.smart_entry_enabled:
            logger.info(f"  Timeout: {config.smart_entry_timeout_minutes}min, Check interval: {config.smart_entry_check_interval_seconds}s, Max hunters: {config.max_concurrent_hunters}")
            logger.info(f"  Thresholds: MFI_momentum={config.hunter_mfi_momentum_threshold}, MFI_reversion={config.hunter_mfi_reversion_threshold}, VWAP_tolerance={config.hunter_vwap_tolerance_percent}%, Volume_spike={config.hunter_volume_spike_multiplier}x")
        logger.info(f"Signal filters: min_oi=${config.signal_min_open_interest_usdt}, min_vol_1h=${config.signal_min_volume_1h_usdt}, max_price_change_5m={config.signal_max_price_change_5min_percent}%")
        return config

    def _init_safety_constants(self) -> TradingSafetyConstants:
        """Initialize safety constants from .env (if provided)"""
        constants = TradingSafetyConstants()

        # Load from .env if available (override defaults)
        if val := os.getenv('MINIMUM_ACTIVE_BALANCE_USD'):
            constants.MINIMUM_ACTIVE_BALANCE_USD = Decimal(val)

        # Log loaded values
        logger.info(f"Safety constants: min_active_balance=${constants.MINIMUM_ACTIVE_BALANCE_USD}")

        return constants

    def _read_pgpass(self, host: str, port: int, database: str, user: str) -> Optional[str]:
        """
        Read password from .pgpass file (PostgreSQL standard).

        Format: hostname:port:database:username:password
        Wildcards (*) are supported for hostname, port, database.

        Returns:
            Password from .pgpass or None if not found
        """
        import pathlib

        # Determine .pgpass file location
        if os.name == 'nt':  # Windows
            pgpass_path = pathlib.Path(os.getenv('APPDATA', '')) / 'postgresql' / 'pgpass.conf'
        else:  # Linux/Mac
            pgpass_path = pathlib.Path.home() / '.pgpass'

        if not pgpass_path.exists():
            return None

        try:
            with open(pgpass_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    parts = line.split(':')
                    if len(parts) != 5:
                        continue

                    pg_host, pg_port, pg_db, pg_user, pg_pass = parts

                    # Check if line matches our connection parameters
                    if (pg_host in ('*', host)) and \
                       (pg_port in ('*', str(port))) and \
                       (pg_db in ('*', database)) and \
                       (pg_user in ('*', user)):
                        logger.info(f"✅ Found password in .pgpass for {user}@{host}:{port}/{database}")
                        return pg_pass

            return None
        except Exception as e:
            logger.warning(f"⚠️ Failed to read .pgpass: {e}")
            return None

    def _init_database(self) -> DatabaseConfig:
        """Initialize database configuration from .env and .pgpass"""
        config = DatabaseConfig()

        if val := os.getenv('DB_HOST'):
            config.host = val
        if val := os.getenv('DB_PORT'):
            config.port = int(val)
        if val := os.getenv('DB_NAME'):
            config.database = val
        if val := os.getenv('DB_USER'):
            config.user = val

        # Priority: DB_PASSWORD env var > .pgpass file > empty string
        if val := os.getenv('DB_PASSWORD'):
            config.password = val
            logger.info("🔑 Using password from DB_PASSWORD env var")
        elif pgpass_password := self._read_pgpass(config.host, config.port, config.database, config.user):
            config.password = pgpass_password
            logger.info("🔑 Using password from .pgpass file")
        else:
            logger.warning("⚠️ No password found in env or .pgpass - using empty password")

        if val := os.getenv('DB_POOL_SIZE'):
            config.pool_size = int(val)
        if val := os.getenv('DB_MAX_OVERFLOW'):
            config.max_overflow = int(val)

        logger.info(f"Database config: {config.host}:{config.port}/{config.database}")
        return config

    def get_exchange_config(self, exchange_name: str) -> Optional[ExchangeConfig]:
        """Get configuration for specific exchange"""
        return self.exchanges.get(exchange_name)

    def is_testnet(self) -> bool:
        """Check if running in testnet mode"""
        for exchange in self.exchanges.values():
            if exchange.testnet:
                return True
        return False

    def validate(self) -> bool:
        """Validate configuration"""
        # Check if at least one exchange is configured
        if not self.exchanges:
            logger.error("No exchanges configured! Please set API keys in .env file")
            return False

        # Check database configuration
        if not self.database.host or not self.database.database:
            logger.error("Database configuration missing!")
            return False

        # Check trading parameters
        if self.trading.position_size_usd <= 0:
            logger.error("Invalid position size!")
            return False

        if self.trading.stop_loss_percent <= 0:
            logger.error("Invalid stop loss percentage!")
            return False

        logger.info("✅ Configuration validated successfully")
        return True


# Create singleton instance
config = Config()