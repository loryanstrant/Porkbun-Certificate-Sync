"""
Password encryption/decryption utilities
Uses symmetric encryption with a key derived from environment or generated
"""
import os
import base64
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

logger = logging.getLogger(__name__)


class PasswordEncryption:
    """Handles password encryption and decryption"""
    
    def __init__(self):
        """Initialize encryption with a key"""
        self._encryption_key = self._get_or_create_encryption_key()
        self._fernet = Fernet(self._encryption_key)
    
    def _get_or_create_encryption_key(self) -> bytes:
        """
        Get encryption key from environment or generate one
        
        Returns:
            Base64-encoded Fernet key
        """
        # Try to get key from environment
        env_key = os.environ.get('ENCRYPTION_KEY')
        
        if env_key:
            try:
                # Validate it's a proper Fernet key
                key = base64.urlsafe_b64decode(env_key)
                if len(key) == 32:
                    return env_key.encode()
            except Exception:
                logger.warning("Invalid ENCRYPTION_KEY in environment, generating new key")
        
        # Generate a new key (will be different each restart if not persisted)
        key = Fernet.generate_key()
        logger.warning(
            "No ENCRYPTION_KEY environment variable set. "
            "Generated temporary encryption key. "
            "Set ENCRYPTION_KEY environment variable to persist passwords across restarts. "
            f"Current key: {key.decode()}"
        )
        return key
    
    def encrypt_password(self, password: str) -> str:
        """
        Encrypt a password
        
        Args:
            password: Plain text password
            
        Returns:
            Encrypted password (base64 encoded)
        """
        if not password:
            return ""
        
        encrypted = self._fernet.encrypt(password.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt_password(self, encrypted_password: str) -> str:
        """
        Decrypt a password
        
        Args:
            encrypted_password: Encrypted password (base64 encoded)
            
        Returns:
            Plain text password
        """
        if not encrypted_password:
            return ""
        
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_password.encode())
            decrypted = self._fernet.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Failed to decrypt password: {e}")
            raise ValueError("Failed to decrypt password - encryption key may have changed")


# Global instance
_password_encryption = None


def get_password_encryption() -> PasswordEncryption:
    """Get the global password encryption instance"""
    global _password_encryption
    if _password_encryption is None:
        _password_encryption = PasswordEncryption()
    return _password_encryption
