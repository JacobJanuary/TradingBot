"""
Trading Bot Configuration
Based on best practices from freqtrade and jesse-ai
"""
import os
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from decimal import Decimal
import yaml
from pathlib import Path
import sys
# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from utils.crypto_manager import decrypt_env_value

logger = logging.getLogger(__name__)


@dataclass
class ExchangeConfig:
    """Exchange configuration"""
    name: str
    api_key: str
    api_secret: str
    enabled: bool = True  # Add enabled flag
    testnet: bool = False
    rate_limit: bool = True

    # WebSocket settings
    ws_heartbeat_interval: int = 30
    ws_timeout: int = 10
    ws_reconnect_delay: int = 5
    ws_max_reconnect_attempts: int = 10


@dataclass
class TradingConfig:
    """Trading parameters"""
    # Position sizing
    position_size_usd: Decimal = Decimal('100')
    max_positions: int = 10
    max_exposure_usd: Decimal = Decimal('1000')

    # Risk management
    stop_loss_percent: Decimal = Decimal('2.0')
    # take_profit_percent: Decimal = Decimal('3.0')  # DEPRECATED - Using Smart Trailing Stop
    trailing_activation_percent: Decimal = Decimal('1.5')  # Smart Trailing activation
    trailing_callback_percent: Decimal = Decimal('0.5')  # Trail distance from peak

    # Position management
    max_position_age_hours: int = 1  # From .env
    min_profit_for_breakeven: Decimal = Decimal('0.3')
    commission_percent: Decimal = Decimal('0.3')  # Trading commission for breakeven calculation

    # Aged position liquidation settings
    liquidation_low_balance_factor: int = 10  # Start liquidation if balance < position_size * factor
    liquidation_start_hours: int = 4  # Hours after max_age to start gradual liquidation
    aged_check_interval_minutes: int = 60  # Check interval for aged positions

    # Signal filtering
    min_score_week: Decimal = Decimal('50')
    min_score_month: Decimal = Decimal('50')
    signal_time_window_minutes: int = 1440  # Increased to 24 hours for testing
    max_trades_per_15min: int = 10

    # Wave processing with buffer
    signal_buffer_percent: Decimal = Decimal('33')  # Buffer percentage for duplicate replacement
    duplicate_check_enabled: bool = True  # Enable duplicate position checking
    allow_multiple_positions: bool = False  # One position per symbol only

    # Execution
    max_slippage_percent: Decimal = Decimal('0.5')
    max_spread_percent: Decimal = Decimal('0.5')

    # Symbol filtering
    stoplist_symbols: str = ''  # Comma-separated list of symbols to exclude
    use_symbol_whitelist: bool = False
    whitelist_symbols: str = ''  # Comma-separated list of allowed symbols (if whitelist enabled)
    excluded_patterns: str = ''  # Patterns to exclude (e.g., *UP,*DOWN)
    min_symbol_volume_usd: Decimal = Decimal('0')
    delisted_symbols: str = ''  # Delisted symbols to exclude


@dataclass
class DatabaseConfig:
    """Database configuration"""
    host: str
    port: int
    database: str
    user: str
    password: str
    pool_size: int = 10
    max_overflow: int = 20


class Settings:
    """Main configuration class"""

    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path) if config_path else Path('config')
        self._load_environment()
        self._load_yaml_configs()

        # Initialize configs
        self.exchanges = self._init_exchanges()
        self.trading = self._init_trading()
        self.database = self._init_database()

        # System settings
        self.debug = os.getenv('DEBUG', 'false').lower() == 'true'
        self.environment = os.getenv('ENVIRONMENT', 'development')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')

    def _load_environment(self):
        """Load .env file if exists"""
        env_file = self.config_path.parent / '.env'
        if env_file.exists():
            from dotenv import load_dotenv
            load_dotenv(env_file)

    def _load_yaml_configs(self):
        """Load YAML configuration files"""
        self.yaml_configs = {}
        for yaml_file in self.config_path.glob('*.yaml'):
            with open(yaml_file, 'r') as f:
                self.yaml_configs[yaml_file.stem] = yaml.safe_load(f)

    def _init_exchanges(self) -> Dict[str, ExchangeConfig]:
        """Initialize exchange configurations"""
        exchanges = {}
        
        # Load exchanges from config.yaml if exists
        if 'config' in self.yaml_configs and 'trading' in self.yaml_configs['config']:
            trading_config = self.yaml_configs['config']['trading']
            if 'exchanges' in trading_config:
                for exchange_conf in trading_config['exchanges']:
                    name = exchange_conf.get('name')
                    enabled = exchange_conf.get('enabled', False)
                    
                    # Only process enabled exchanges
                    if not enabled:
                        continue
                        
                    # Get API keys from environment
                    if name == 'binance' and os.getenv('BINANCE_API_KEY'):
                        exchanges['binance'] = ExchangeConfig(
                            name='binance',
                            api_key=os.getenv('BINANCE_API_KEY'),
                            api_secret=os.getenv('BINANCE_API_SECRET'),
                            enabled=enabled,
                            testnet=exchange_conf.get('testnet', False)
                        )
                    elif name == 'bybit' and os.getenv('BYBIT_API_KEY'):
                        exchanges['bybit'] = ExchangeConfig(
                            name='bybit',
                            api_key=os.getenv('BYBIT_API_KEY'),
                            api_secret=os.getenv('BYBIT_API_SECRET'),
                            enabled=enabled,
                            testnet=exchange_conf.get('testnet', False)
                        )

        # Fallback to environment variables if no YAML config
        if not exchanges:
            # Decrypt API keys if they are encrypted
            binance_key = decrypt_env_value('BINANCE_API_KEY') or os.getenv('BINANCE_API_KEY')
            binance_secret = decrypt_env_value('BINANCE_API_SECRET') or os.getenv('BINANCE_API_SECRET')
            
            if binance_key:
                exchanges['binance'] = ExchangeConfig(
                    name='binance',
                    api_key=binance_key,
                    api_secret=binance_secret,
                    enabled=True,
                    testnet=os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'
                )

            # Decrypt Bybit API keys if encrypted
            bybit_key = decrypt_env_value('BYBIT_API_KEY') or os.getenv('BYBIT_API_KEY')
            bybit_secret = decrypt_env_value('BYBIT_API_SECRET') or os.getenv('BYBIT_API_SECRET')
            
            if bybit_key:
                exchanges['bybit'] = ExchangeConfig(
                    name='bybit',
                    api_key=bybit_key,
                    api_secret=bybit_secret,
                    enabled=False,  # Disable by default due to connection issues
                    testnet=os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'
                )

        return exchanges

    def _init_trading(self) -> TradingConfig:
        """Initialize trading configuration"""
        config = TradingConfig()

        # From environment variables
        env_mappings = {
            'POSITION_SIZE_USD': 'position_size_usd',
            'MAX_POSITIONS': 'max_positions',
            'MAX_TRADES_PER_15MIN': 'max_trades_per_15min',
            'MAX_EXPOSURE_USD': 'max_exposure_usd',
            'STOP_LOSS_PERCENT': 'stop_loss_percent',
            'TRAILING_ACTIVATION_PERCENT': 'trailing_activation_percent',
            'TRAILING_CALLBACK_PERCENT': 'trailing_callback_percent',
            'MAX_POSITION_AGE_HOURS': 'max_position_age_hours',
            'COMMISSION_PERCENT': 'commission_percent',
            'MIN_SCORE_WEEK': 'min_score_week',
            'MIN_SCORE_MONTH': 'min_score_month',
            'MAX_SPREAD_PERCENT': 'max_spread_percent',
            'MAX_SLIPPAGE_PERCENT': 'max_slippage_percent',
            'LIQUIDATION_LOW_BALANCE_FACTOR': 'liquidation_low_balance_factor',
            'LIQUIDATION_START_HOURS': 'liquidation_start_hours',
            'AGED_CHECK_INTERVAL_MINUTES': 'aged_check_interval_minutes',
            'STOPLIST_SYMBOLS': 'stoplist_symbols',
            'USE_SYMBOL_WHITELIST': 'use_symbol_whitelist',
            'WHITELIST_SYMBOLS': 'whitelist_symbols',
            'EXCLUDED_PATTERNS': 'excluded_patterns',
            'MIN_SYMBOL_VOLUME_USD': 'min_symbol_volume_usd',
            'DELISTED_SYMBOLS': 'delisted_symbols',
        }

        for env_key, attr_name in env_mappings.items():
            if os.getenv(env_key):
                value = os.getenv(env_key)
                attr_type = type(getattr(config, attr_name))
                if attr_type == Decimal:
                    setattr(config, attr_name, Decimal(value))
                elif attr_type == int:
                    setattr(config, attr_name, int(value))

        # Determine strategy based on environment
        strategy_name = self._get_strategy_name()
        
        # Override with YAML if exists
        if 'strategies' in self.yaml_configs:
            # First try environment-specific strategy, then fallback to default
            strategy_config = self.yaml_configs['strategies'].get(strategy_name, {})
            if not strategy_config:
                strategy_config = self.yaml_configs['strategies'].get('default', {})
                
            logger.info(f"Loading trading strategy: {strategy_name}")
            
            for key, value in strategy_config.items():
                if hasattr(config, key):
                    if isinstance(getattr(config, key), Decimal):
                        setattr(config, key, Decimal(str(value)))
                    else:
                        setattr(config, key, value)

        return config
    
    def _get_strategy_name(self) -> str:
        """Determine strategy name based on environment and exchange settings"""
        # Check if explicitly set via environment variable
        if os.getenv('STRATEGY_NAME'):
            return os.getenv('STRATEGY_NAME')
        
        # Check if any exchange is using testnet
        is_testnet = False
        for exchange in self.exchanges.values():
            if exchange.testnet:
                is_testnet = True
                break
        
        # Select strategy based on environment
        if is_testnet:
            return 'testnet'
        elif self.environment == 'production':
            return 'production'
        else:
            return 'default'

    def _init_database(self) -> DatabaseConfig:
        """Initialize database configuration"""
        # Decrypt password if encrypted
        db_password = decrypt_env_value('DB_PASSWORD') or os.getenv('DB_PASSWORD', '')
        
        return DatabaseConfig(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME', 'trading'),
            user=os.getenv('DB_USER', 'postgres'),
            password=db_password,
            pool_size=int(os.getenv('DB_POOL_SIZE', 10)),
            max_overflow=int(os.getenv('DB_MAX_OVERFLOW', 20))
        )

    def get_exchange(self, name: str) -> Optional[ExchangeConfig]:
        """Get exchange configuration by name"""
        return self.exchanges.get(name.lower())

    def validate(self) -> bool:
        """Validate configuration"""
        errors = []

        # Check required exchanges
        if not self.exchanges:
            errors.append("No exchanges configured")

        # Check database
        if not self.database.password:
            errors.append("Database password not set")

        # Check trading parameters
        if self.trading.position_size_usd <= 0:
            errors.append("Invalid position size")

        if self.trading.stop_loss_percent <= 0:
            errors.append("Invalid stop loss percent")

        if errors:
            for error in errors:
                print(f"Configuration error: {error}")
            return False

        return True


# Singleton instance
settings = Settings()