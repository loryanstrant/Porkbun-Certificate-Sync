"""
SSH host configuration management
"""
import logging
from typing import Dict, List, Optional
from .password_encryption import get_password_encryption

logger = logging.getLogger(__name__)


class SSHConfig:
    """Manages SSH host configuration"""
    
    def __init__(self, config):
        """
        Initialize SSH configuration manager
        
        Args:
            config: Main configuration manager instance
        """
        self.config = config
    
    def get_ssh_hosts(self) -> List[Dict]:
        """
        Get list of configured SSH hosts
        
        Returns:
            List of SSH host configurations sorted by display name
        """
        hosts = self.config.config.get("ssh_hosts", [])
        # Sort alphabetically by display_name
        return sorted(hosts, key=lambda x: x.get("display_name", "").lower())
    
    def add_ssh_host(self, display_name: str, hostname: str, port: int, 
                     username: str, password: str, cert_path: str, use_sudo: bool = False,
                     file_overrides: dict = None):
        """
        Add an SSH host to the configuration
        
        Args:
            display_name: Display name for the host
            hostname: Hostname or IP address
            port: SSH port
            username: SSH username
            password: SSH password (will be encrypted)
            cert_path: Path where certificates should be stored on remote host
            use_sudo: Whether to use sudo for file operations on remote host
            file_overrides: Optional dict to override specific file names for this host
        """
        hosts = self.config.config.get("ssh_hosts", [])
        
        # Check if display name already exists
        if any(h.get("display_name") == display_name for h in hosts):
            raise ValueError(f"Display name '{display_name}' already exists")
        
        # Encrypt the password
        password_enc = get_password_encryption()
        encrypted_password = password_enc.encrypt_password(password)
        
        host_config = {
            "display_name": display_name,
            "hostname": hostname,
            "port": port,
            "username": username,
            "password_encrypted": encrypted_password,
            "cert_path": cert_path,
            "use_sudo": use_sudo
        }
        
        # Add file_overrides if provided
        if file_overrides:
            host_config["file_overrides"] = file_overrides
        
        hosts.append(host_config)
        self.config.config["ssh_hosts"] = hosts
        self.config.save()
        logger.info(f"Added SSH host: {display_name}")
    
    def update_ssh_host(self, original_display_name: str, display_name: str, 
                       hostname: str, port: int, username: str, 
                       password: Optional[str], cert_path: str, use_sudo: Optional[bool] = None,
                       file_overrides: Optional[dict] = None):
        """
        Update an SSH host in the configuration
        
        Args:
            original_display_name: Original display name of the host to update
            display_name: New display name
            hostname: Hostname or IP address
            port: SSH port
            username: SSH username
            password: SSH password (will be encrypted). If None, keeps existing password
            cert_path: Path where certificates should be stored on remote host
            use_sudo: Whether to use sudo for file operations. If None, keeps existing setting
            file_overrides: Optional dict to override specific file names for this host
        """
        hosts = self.config.config.get("ssh_hosts", [])
        
        # Find the host to update
        host_index = None
        for i, h in enumerate(hosts):
            if h.get("display_name") == original_display_name:
                host_index = i
                break
        
        if host_index is None:
            raise ValueError(f"SSH host '{original_display_name}' not found")
        
        # If display name is changing, check for duplicates
        if original_display_name != display_name:
            if any(h.get("display_name") == display_name for h in hosts):
                raise ValueError(f"Display name '{display_name}' already exists")
        
        # Update the host configuration
        host_config = {
            "display_name": display_name,
            "hostname": hostname,
            "port": port,
            "username": username,
            "cert_path": cert_path
        }
        
        # Keep existing password if no new password provided
        if password:
            password_enc = get_password_encryption()
            host_config["password_encrypted"] = password_enc.encrypt_password(password)
        else:
            # Try to get encrypted password, fall back to old password_hash field
            host_config["password_encrypted"] = hosts[host_index].get("password_encrypted", hosts[host_index].get("password_hash", ""))
        
        # Keep existing use_sudo setting if not provided
        if use_sudo is not None:
            host_config["use_sudo"] = use_sudo
        else:
            host_config["use_sudo"] = hosts[host_index].get("use_sudo", False)
        
        # Handle file_overrides
        if file_overrides is not None:
            # Explicit value provided: set if non-empty, remove if empty
            if file_overrides:
                host_config["file_overrides"] = file_overrides
            # Empty dict means remove existing overrides (don't add to config)
        else:
            # No value provided (None): keep existing file_overrides
            existing_overrides = hosts[host_index].get("file_overrides")
            if existing_overrides:
                host_config["file_overrides"] = existing_overrides
        
        hosts[host_index] = host_config
        self.config.config["ssh_hosts"] = hosts
        self.config.save()
        logger.info(f"Updated SSH host: {display_name}")
    
    def remove_ssh_host(self, display_name: str):
        """
        Remove an SSH host from the configuration
        
        Args:
            display_name: Display name of the host to remove
        """
        hosts = self.config.config.get("ssh_hosts", [])
        self.config.config["ssh_hosts"] = [h for h in hosts if h.get("display_name") != display_name]
        self.config.save()
        logger.info(f"Removed SSH host: {display_name}")
    
    def get_ssh_host(self, display_name: str) -> Optional[Dict]:
        """
        Get a specific SSH host configuration
        
        Args:
            display_name: Display name of the host
            
        Returns:
            Host configuration or None if not found
        """
        hosts = self.get_ssh_hosts()
        for host in hosts:
            if host.get("display_name") == display_name:
                return host
        return None
    
    def verify_password(self, display_name: str, password: str) -> bool:
        """
        Verify a password against stored encrypted password
        
        Args:
            display_name: Display name of the host
            password: Password to verify
            
        Returns:
            True if password matches
        """
        host = self.get_ssh_host(display_name)
        if not host:
            return False
        
        encrypted_password = host.get("password_encrypted")
        if not encrypted_password:
            return False
        
        try:
            password_enc = get_password_encryption()
            decrypted = password_enc.decrypt_password(encrypted_password)
            return decrypted == password
        except Exception:
            return False
    
    def get_decrypted_password(self, display_name: str) -> Optional[str]:
        """
        Get decrypted password for a host
        
        Args:
            display_name: Display name of the host
            
        Returns:
            Decrypted password or None if not found
        """
        host = self.get_ssh_host(display_name)
        if not host:
            return None
        
        encrypted_password = host.get("password_encrypted")
        if not encrypted_password:
            return None
        
        try:
            password_enc = get_password_encryption()
            return password_enc.decrypt_password(encrypted_password)
        except Exception as e:
            logger.error(f"Failed to decrypt password for {display_name}: {e}")
            return None
