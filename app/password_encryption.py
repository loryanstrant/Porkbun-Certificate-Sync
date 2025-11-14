"""
Password encryption/decryption utilities
Uses symmetric encryption with a key derived from environment or generated
"""
import os
import base64
import logging
from pathlib import Path
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class PasswordEncryption:
    """Handles password encryption and decryption"""
    
    def __init__(self):
        """Initialize encryption with a key"""
        self._encryption_key = self._get_or_create_encryption_key()
        self._fernet = Fernet(self._encryption_key)
    
    def _get_or_create_encryption_key(self) -> bytes:
        """
        Get encryption key from environment, file, or generate one
        
        Priority:
        1. ENCRYPTION_KEY environment variable
        2. Key file in config directory
        3. Generate new key and save to file
        
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
                    logger.info("Using encryption key from ENCRYPTION_KEY environment variable")
                    return env_key.encode()
            except Exception:
                logger.warning("Invalid ENCRYPTION_KEY in environment, checking for key file")
        
        # Try to get key from file
        config_dir = os.environ.get('CONFIG_PATH', '/app/config/config.yaml')
        config_dir = os.path.dirname(config_dir)
        key_file = os.path.join(config_dir, '.encryption_key')
        
        if os.path.exists(key_file):
            try:
                with open(key_file, 'r') as f:
                    file_key = f.read().strip()
                # Validate it's a proper Fernet key
                key = base64.urlsafe_b64decode(file_key)
                if len(key) == 32:
                    logger.info(f"Using encryption key from file: {key_file}")
                    return file_key.encode()
            except Exception as e:
                logger.warning(f"Invalid encryption key in file {key_file}: {e}")
        
        # Generate a new key and save it to file
        key = Fernet.generate_key()
        try:
            # Ensure config directory exists
            os.makedirs(config_dir, exist_ok=True)
            # Save key to file with restricted permissions
            with open(key_file, 'w') as f:
                f.write(key.decode())
            # Set file permissions to 600 (read/write for owner only)
            os.chmod(key_file, 0o600)
            logger.info(
                f"Generated new encryption key and saved to {key_file}. "
                "This key will persist across container restarts."
            )
        except Exception as e:
            logger.warning(
                f"Failed to save encryption key to file: {e}. "
                "Key will not persist across container restarts. "
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
