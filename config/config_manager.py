#!/usr/bin/env python3
"""
Configuration Manager for Trading Bot
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class ConfigManager:
    """Manages bot configuration from YAML and environment"""
    
    def __init__(self, config_file: str = 'config/config.yaml'):
        self.config_file = Path(config_file)
        self.config = self._load_config()
        self._substitute_env_vars()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not self.config_file.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_file}")
        
        with open(self.config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def _substitute_env_vars(self):
        """Substitute environment variables in config"""
        # Substitute Binance API keys
        if 'binance' in self.config:
            if 'api_key' in self.config['binance']:
                self.config['binance']['api_key'] = os.getenv('BINANCE_API_KEY', '')
            if 'api_secret' in self.config['binance']:
                self.config['binance']['api_secret'] = os.getenv('BINANCE_API_SECRET', '')
        
        # Substitute Bybit API keys
        if 'bybit' in self.config:
            if 'api_key' in self.config['bybit']:
                self.config['bybit']['api_key'] = os.getenv('BYBIT_API_KEY', '')
            if 'api_secret' in self.config['bybit']:
                self.config['bybit']['api_secret'] = os.getenv('BYBIT_API_SECRET', '')
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key (supports nested keys with dots)"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value
    
    def get_exchange_config(self, exchange: str) -> Optional[Dict[str, Any]]:
        """Get exchange-specific configuration"""
        # Check if exchange config exists at top level
        exchange_config = self.config.get(exchange, {})
        
        # Also check in trading.exchanges list
        trading = self.config.get('trading', {})
        exchanges = trading.get('exchanges', [])
        
        for ex in exchanges:
            if ex.get('name') == exchange:
                # Merge with top-level exchange config
                merged = {**exchange_config, **ex}
                return merged
        
        return exchange_config if exchange_config else None
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration"""
        return self.config.get('database', {})
    
    def get_risk_config(self) -> Dict[str, Any]:
        """Get risk management configuration"""
        return self.config.get('risk', {})
    
    def get_trading_mode(self) -> str:
        """Get current trading mode"""
        return self.config.get('trading', {}).get('mode', 'shadow')
    
    def reload(self):
        """Reload configuration from file"""
        self.config = self._load_config()
        self._substitute_env_vars()