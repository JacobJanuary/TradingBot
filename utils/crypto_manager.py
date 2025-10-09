"""
Cryptographic utilities for securing sensitive data
"""
import os
import base64
import logging
from typing import Optional
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv, set_key

logger = logging.getLogger(__name__)


class CryptoManager:
    """
    Manages encryption/decryption of sensitive data like API keys
    """

    # Security: Salt file location (not in git)
    SALT_FILE = Path('.crypto_salt')

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize crypto manager with master key

        Args:
            master_key: Master key for encryption. If not provided,
                       will try to load from MASTER_KEY env variable
        """
        self.master_key = master_key or os.getenv('MASTER_KEY')

        if not self.master_key:
            # Generate new master key if none exists
            self.master_key = self._generate_master_key()
            logger.warning("Generated new master key. Please save it securely!")
            logger.info(f"MASTER_KEY={self.master_key}")

        # Security: Load or generate random salt
        self.salt = self._load_or_generate_salt()

        self.cipher = self._create_cipher()
        
    def _generate_master_key(self) -> str:
        """Generate a new master key"""
        return Fernet.generate_key().decode()

    def _load_or_generate_salt(self) -> bytes:
        """
        Load salt from file or generate new random salt

        Returns:
            Salt bytes (16 bytes)
        """
        if self.SALT_FILE.exists():
            # Load existing salt
            try:
                with open(self.SALT_FILE, 'rb') as f:
                    salt = f.read()
                logger.info(f"Loaded salt from {self.SALT_FILE}")
                return salt
            except Exception as e:
                logger.error(f"Failed to load salt from {self.SALT_FILE}: {e}")
                # Fallback to generating new salt

        # Generate new random salt
        salt = os.urandom(16)

        # Save salt to file
        try:
            with open(self.SALT_FILE, 'wb') as f:
                f.write(salt)
            # Set restrictive permissions (owner read/write only)
            os.chmod(self.SALT_FILE, 0o600)
            logger.warning(f"Generated new random salt and saved to {self.SALT_FILE}")
        except Exception as e:
            logger.error(f"Failed to save salt to {self.SALT_FILE}: {e}")

        return salt

    def _create_cipher(self) -> Fernet:
        """Create Fernet cipher from master key"""
        if isinstance(self.master_key, str):
            key_bytes = self.master_key.encode()
        else:
            key_bytes = self.master_key

        # Ensure key is proper format
        try:
            return Fernet(key_bytes)
        except ValueError:
            # If key is not valid Fernet key, derive one from it using PBKDF2
            # Security: Use random salt (loaded from file or generated)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self.salt,  # Security: Random salt, not fixed!
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(key_bytes))
            return Fernet(key)
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext string
        
        Args:
            plaintext: String to encrypt
            
        Returns:
            Encrypted string (base64 encoded)
        """
        if not plaintext:
            return ""
            
        encrypted = self.cipher.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt ciphertext string
        
        Args:
            ciphertext: Encrypted string (base64 encoded)
            
        Returns:
            Decrypted plaintext string
        """
        if not ciphertext:
            return ""
            
        try:
            # Handle double encoding if present
            try:
                decoded = base64.urlsafe_b64decode(ciphertext.encode())
            except (ValueError, TypeError):
                decoded = ciphertext.encode()
                
            decrypted = self.cipher.decrypt(decoded)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            # Return original if decryption fails (might be unencrypted)
            return ciphertext
    
    def encrypt_env_file(self, env_path: str = '.env', backup: bool = True):
        """
        Encrypt sensitive values in .env file
        
        Args:
            env_path: Path to .env file
            backup: Create backup before encryption
        """
        if backup:
            import shutil
            backup_path = f"{env_path}.backup"
            shutil.copy(env_path, backup_path)
            logger.info(f"Created backup at {backup_path}")
        
        # Keys to encrypt
        sensitive_keys = [
            'DB_PASSWORD',
            'BINANCE_API_KEY', 
            'BINANCE_API_SECRET',
            'BYBIT_API_KEY',
            'BYBIT_API_SECRET',
            'DISCORD_WEBHOOK_URL',
            'TELEGRAM_BOT_TOKEN',
            'AWS_ACCESS_KEY_ID',
            'AWS_SECRET_ACCESS_KEY'
        ]
        
        # Load current env
        load_dotenv(env_path, override=True)
        
        encrypted_count = 0
        for key in sensitive_keys:
            value = os.getenv(key)
            if value and not value.startswith('ENC:'):
                # Encrypt and update
                encrypted = self.encrypt(value)
                set_key(env_path, key, f'ENC:{encrypted}')
                encrypted_count += 1
                logger.info(f"Encrypted {key}")
        
        # Add master key reminder
        if encrypted_count > 0:
            logger.warning(f"\n{'='*60}")
            logger.warning("IMPORTANT: Save this master key securely!")
            logger.warning(f"MASTER_KEY={self.master_key}")
            logger.warning("You will need it to decrypt the values")
            logger.warning(f"{'='*60}\n")
            
        return encrypted_count
    
    def get_decrypted_value(self, key: str) -> Optional[str]:
        """
        Get decrypted value from environment
        
        Args:
            key: Environment variable key
            
        Returns:
            Decrypted value or None
        """
        value = os.getenv(key)
        if not value:
            return None
            
        if value.startswith('ENC:'):
            # Remove prefix and decrypt
            encrypted = value[4:]
            return self.decrypt(encrypted)
        else:
            # Return as-is if not encrypted
            return value


# Singleton instance
_crypto_manager: Optional[CryptoManager] = None


def get_crypto_manager() -> CryptoManager:
    """Get or create singleton crypto manager"""
    global _crypto_manager
    if _crypto_manager is None:
        _crypto_manager = CryptoManager()
    return _crypto_manager


def decrypt_env_value(key: str) -> Optional[str]:
    """
    Convenience function to decrypt environment value
    
    Args:
        key: Environment variable key
        
    Returns:
        Decrypted value or None
    """
    return get_crypto_manager().get_decrypted_value(key)