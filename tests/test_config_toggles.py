import os
import unittest
from unittest.mock import patch

# Import Config class - we need to patch os.getenv before importing if it loads at module level
# But settings.py loads dotenv at module level.
# However, Config class loads env vars in __init__ and _init_exchanges.
# So we can patch os.getenv during Config instantiation.

from config.settings import Config

class TestExchangeToggles(unittest.TestCase):

    @patch('config.settings.load_dotenv') # Prevent loading real .env
    @patch.dict(os.environ, {}, clear=True)
    def test_defaults(self, mock_load_dotenv):
        """Test default behavior (TRADE=true implied)"""
        # Setup env with keys
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'bin_key',
            'BINANCE_API_SECRET': 'bin_secret',
            'BYBIT_API_KEY': 'by_key',
            'BYBIT_API_SECRET': 'by_secret'
        }):
            config = Config()
            self.assertTrue(config.exchanges['binance'].enabled)
            self.assertTrue(config.exchanges['bybit'].enabled)

    @patch('config.settings.load_dotenv')
    @patch.dict(os.environ, {}, clear=True)
    def test_disable_bybit(self, mock_load_dotenv):
        """Test disabling Bybit"""
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'bin_key',
            'BINANCE_API_SECRET': 'bin_secret',
            'BYBIT_API_KEY': 'by_key',
            'BYBIT_API_SECRET': 'by_secret',
            'BYBIT_TRADE': 'false'
        }):
            config = Config()
            self.assertTrue(config.exchanges['binance'].enabled)
            self.assertFalse(config.exchanges['bybit'].enabled)
            self.assertEqual(config.exchanges['bybit'].api_key, 'disabled')

    @patch('config.settings.load_dotenv')
    @patch.dict(os.environ, {}, clear=True)
    def test_disable_binance(self, mock_load_dotenv):
        """Test disabling Binance"""
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'bin_key',
            'BINANCE_API_SECRET': 'bin_secret',
            'BYBIT_API_KEY': 'by_key',
            'BYBIT_API_SECRET': 'by_secret',
            'BINANCE_TRADE': 'false'
        }):
            config = Config()
            self.assertFalse(config.exchanges['binance'].enabled)
            self.assertEqual(config.exchanges['binance'].api_key, 'disabled')
            self.assertTrue(config.exchanges['bybit'].enabled)

    @patch('config.settings.load_dotenv')
    @patch.dict(os.environ, {}, clear=True)
    def test_disable_bybit_no_keys(self, mock_load_dotenv):
        """Test disabling Bybit when keys are missing"""
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'bin_key',
            'BINANCE_API_SECRET': 'bin_secret',
            'BYBIT_TRADE': 'false'
            # No Bybit keys
        }):
            config = Config()
            self.assertTrue(config.exchanges['binance'].enabled)
            # Should still exist but be disabled
            self.assertFalse(config.exchanges['bybit'].enabled)
            self.assertEqual(config.exchanges['bybit'].api_key, 'disabled')

    @patch('config.settings.load_dotenv')
    @patch.dict(os.environ, {}, clear=True)
    def test_enable_bybit_no_keys(self, mock_load_dotenv):
        """Test enabling Bybit (default) when keys are missing"""
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'bin_key',
            'BINANCE_API_SECRET': 'bin_secret',
            'BYBIT_TRADE': 'true'
            # No Bybit keys
        }):
            config = Config()
            self.assertTrue(config.exchanges['binance'].enabled)
            # Should NOT exist in exchanges dict
            self.assertNotIn('bybit', config.exchanges)

if __name__ == '__main__':
    unittest.main()
