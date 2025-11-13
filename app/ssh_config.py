"""
SSH host configuration management
"""
import logging
from typing import Dict, List, Optional
from werkzeug.security import generate_password_hash, check_password_hash

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
                     username: str, password: str, cert_path: str):
        """
        Add an SSH host to the configuration
        
        Args:
            display_name: Display name for the host
            hostname: Hostname or IP address
            port: SSH port
            username: SSH username
            password: SSH password (will be hashed)
            cert_path: Path where certificates should be stored on remote host
        """
        hosts = self.config.config.get("ssh_hosts", [])
        
        # Check if display name already exists
        if any(h.get("display_name") == display_name for h in hosts):
            raise ValueError(f"Display name '{display_name}' already exists")
        
        # Hash the password
        password_hash = generate_password_hash(password)
        
        host_config = {
            "display_name": display_name,
            "hostname": hostname,
            "port": port,
            "username": username,
            "password_hash": password_hash,
            "cert_path": cert_path
        }
        
        hosts.append(host_config)
        self.config.config["ssh_hosts"] = hosts
        self.config.save()
        logger.info(f"Added SSH host: {display_name}")
    
    def update_ssh_host(self, original_display_name: str, display_name: str, 
                       hostname: str, port: int, username: str, 
                       password: Optional[str], cert_path: str):
        """
        Update an SSH host in the configuration
        
        Args:
            original_display_name: Original display name of the host to update
            display_name: New display name
            hostname: Hostname or IP address
            port: SSH port
            username: SSH username
            password: SSH password (will be hashed). If None, keeps existing password
            cert_path: Path where certificates should be stored on remote host
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
        
        # Keep existing password hash if no new password provided
        if password:
            host_config["password_hash"] = generate_password_hash(password)
        else:
            host_config["password_hash"] = hosts[host_index].get("password_hash")
        
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
        Verify a password against stored hash
        
        Args:
            display_name: Display name of the host
            password: Password to verify
            
        Returns:
            True if password matches
        """
        host = self.get_ssh_host(display_name)
        if not host:
            return False
        
        password_hash = host.get("password_hash")
        if not password_hash:
            return False
        
        return check_password_hash(password_hash, password)
