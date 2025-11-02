"""
Configuration management for Porkbun Certificate Sync
"""
import os
import yaml
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class Config:
    """Manages application configuration stored in YAML"""
    
    def __init__(self, config_path: str = None):
        """
        Initialize configuration manager
        
        Args:
            config_path: Path to config file (defaults to /app/config/config.yaml)
        """
        if config_path is None:
            config_path = os.environ.get('CONFIG_PATH', '/app/config/config.yaml')
        
        self.config_path = config_path
        self.config_dir = os.path.dirname(config_path)
        
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load configuration from YAML file"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config = yaml.safe_load(f) or {}
                    logger.info(f"Loaded configuration from {self.config_path}")
                    return config
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                return self._default_config()
        else:
            logger.info("No config file found, using defaults")
            return self._default_config()
    
    def _default_config(self) -> Dict:
        """Return default configuration"""
        return {
            "api": {
                "api_key": "",
                "secret_key": ""
            },
            "domains": [],
            "certificates": {
                "output_dir": "/app/certificates",
                "naming_format": "{domain}",
                "formats": ["pem"]
            },
            "schedule": {
                "enabled": False,
                "cron": "0 2 * * *"
            }
        }
    
    def save(self):
        """Save configuration to YAML file"""
        try:
            with open(self.config_path, 'w') as f:
                yaml.safe_dump(self.config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Saved configuration to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise
    
    def get_api_credentials(self) -> tuple:
        """Get API credentials"""
        api_config = self.config.get("api", {})
        return api_config.get("api_key", ""), api_config.get("secret_key", "")
    
    def set_api_credentials(self, api_key: str, secret_key: str):
        """Set API credentials"""
        if "api" not in self.config:
            self.config["api"] = {}
        self.config["api"]["api_key"] = api_key
        self.config["api"]["secret_key"] = secret_key
        self.save()
    
    def get_domains(self) -> List[Dict]:
        """Get list of configured domains"""
        return self.config.get("domains", [])
    
    def add_domain(self, domain: str, custom_name: Optional[str] = None, 
                   separator: Optional[str] = None, alt_file_names: Optional[List[str]] = None):
        """Add a domain to the configuration"""
        domains = self.config.get("domains", [])
        
        # Check if domain already exists
        if any(d.get("domain") == domain for d in domains):
            raise ValueError(f"Domain {domain} already exists")
        
        domain_config = {
            "domain": domain,
            "custom_name": custom_name or domain,
            "separator": separator or "_",
            "alt_file_names": alt_file_names or []
        }
        
        domains.append(domain_config)
        self.config["domains"] = domains
        self.save()
    
    def update_domain(self, original_domain: str, domain: str, custom_name: Optional[str] = None,
                     separator: Optional[str] = None, alt_file_names: Optional[List[str]] = None):
        """Update a domain in the configuration"""
        domains = self.config.get("domains", [])
        
        # Find the domain to update
        domain_index = None
        for i, d in enumerate(domains):
            if d.get("domain") == original_domain:
                domain_index = i
                break
        
        if domain_index is None:
            raise ValueError(f"Domain {original_domain} not found")
        
        # If domain name is changing, check for duplicates
        if original_domain != domain:
            if any(d.get("domain") == domain for d in domains):
                raise ValueError(f"Domain {domain} already exists")
        
        # Update the domain
        domains[domain_index] = {
            "domain": domain,
            "custom_name": custom_name or domain,
            "separator": separator or "_",
            "alt_file_names": alt_file_names or []
        }
        
        self.config["domains"] = domains
        self.save()
    
    def remove_domain(self, domain: str):
        """Remove a domain from the configuration"""
        domains = self.config.get("domains", [])
        self.config["domains"] = [d for d in domains if d.get("domain") != domain]
        self.save()
    
    def get_certificate_config(self) -> Dict:
        """Get certificate configuration"""
        return self.config.get("certificates", {
            "output_dir": "/app/certificates",
            "naming_format": "{domain}",
            "formats": ["pem"]
        })
    
    def update_certificate_config(self, output_dir: Optional[str] = None,
                                  naming_format: Optional[str] = None,
                                  formats: Optional[List[str]] = None):
        """Update certificate configuration"""
        if "certificates" not in self.config:
            self.config["certificates"] = {}
        
        if output_dir is not None:
            self.config["certificates"]["output_dir"] = output_dir
        if naming_format is not None:
            self.config["certificates"]["naming_format"] = naming_format
        if formats is not None:
            self.config["certificates"]["formats"] = formats
        
        self.save()
    
    def get_schedule_config(self) -> Dict:
        """Get schedule configuration"""
        return self.config.get("schedule", {
            "enabled": False,
            "cron": "0 2 * * *"
        })
    
    def update_schedule_config(self, enabled: bool, cron: str):
        """Update schedule configuration"""
        if "schedule" not in self.config:
            self.config["schedule"] = {}
        
        self.config["schedule"]["enabled"] = enabled
        self.config["schedule"]["cron"] = cron
        self.save()
