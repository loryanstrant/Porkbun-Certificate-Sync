"""
Configuration management for Porkbun Certificate Sync
"""
import os
import tempfile
import threading
import yaml
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# The config file holds Porkbun API credentials, encrypted SSH passwords and the
# admin password digest, so it must not be world- or group-readable.
CONFIG_FILE_MODE = 0o600


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

        # Serialises save() across the request threads and the scheduler thread.
        # Without it, two concurrent whole-file rewrites can truncate the file --
        # which now means losing the only admin credentials, not just a setting.
        self._save_lock = threading.Lock()

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
            },
            "auth": {
                "version": 1,
                "users": []
            }
        }

    def save(self):
        """
        Save configuration to YAML file.

        Writes to a temporary file in the same directory and then os.replace()s it
        into place, so an interrupted or concurrent write can never leave a
        truncated config behind. The file is created with mode 0600 because it
        holds API credentials, encrypted SSH passwords and the admin password
        digest.
        """
        with self._save_lock:
            tmp_path = None
            try:
                fd, tmp_path = tempfile.mkstemp(
                    prefix='.config-', suffix='.yaml.tmp', dir=self.config_dir
                )
                try:
                    with os.fdopen(fd, 'w') as f:
                        yaml.safe_dump(
                            self.config, f, default_flow_style=False, sort_keys=False
                        )
                        f.flush()
                        os.fsync(f.fileno())
                except Exception:
                    # fdopen took ownership of fd; it is closed by the with-block
                    raise
                os.chmod(tmp_path, CONFIG_FILE_MODE)
                os.replace(tmp_path, self.config_path)
                tmp_path = None
                logger.info(f"Saved configuration to {self.config_path}")
            except Exception as e:
                logger.error(f"Failed to save config: {e}")
                raise
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
    
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
        updated_config = {
            "domain": domain,
            "custom_name": custom_name or domain,
            "separator": separator or "_",
            "alt_file_names": alt_file_names or []
        }
        
        domains[domain_index] = updated_config
        
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

    # ------------------------------------------------------------------
    # Authentication
    #
    # The `auth` section is managed by the application (see app/auth.py) and is
    # not meant to be hand-edited. Users are stored as a list even though only a
    # single admin is supported today, so multi-user support can be added later
    # without migrating existing config files.
    #
    # Break-glass: stop the container, delete the whole `auth:` block from
    # config.yaml and restart. The next request goes to /setup and every other
    # setting is preserved.
    # ------------------------------------------------------------------

    def get_auth_config(self) -> Dict:
        """Get the auth section (empty but well-formed if absent)"""
        auth = self.config.get("auth")
        if not isinstance(auth, dict):
            return {"version": 1, "users": []}
        return auth

    def get_auth_users(self) -> List[Dict]:
        """Get the list of configured users"""
        users = self.get_auth_config().get("users")
        if not isinstance(users, list):
            return []
        return [u for u in users if isinstance(u, dict)]

    def get_auth_user(self, username: str) -> Optional[Dict]:
        """Look up a user by username (case-insensitive)"""
        target = (username or "").strip().lower()
        if not target:
            return None
        for user in self.get_auth_users():
            if str(user.get("username", "")).lower() == target:
                return user
        return None

    def get_auth_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Look up a user by its stable id"""
        if not user_id:
            return None
        for user in self.get_auth_users():
            if user.get("id") == user_id:
                return user
        return None

    def add_auth_user(self, user: Dict):
        """
        Append a user record to the auth section.

        Args:
            user: Fully-formed user dict (see app/auth.py build_user_record)

        Raises:
            ValueError: if the username already exists
        """
        if self.get_auth_user(user.get("username", "")):
            raise ValueError("A user with that name already exists")

        auth = self.config.get("auth")
        if not isinstance(auth, dict):
            auth = {"version": 1, "users": []}
            self.config["auth"] = auth
        if not isinstance(auth.get("users"), list):
            auth["users"] = []
        auth.setdefault("version", 1)

        auth["users"].append(user)
        self.save()

    def update_auth_user(self, user_id: str, changes: Dict):
        """
        Shallow-merge `changes` into the stored user record and persist.

        Raises:
            ValueError: if the user does not exist
        """
        user = self.get_auth_user_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        user.update(changes)
        self.save()
