"""
Porkbun API Client for certificate retrieval
"""
import requests
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class PorkbunAPI:
    """Client for interacting with Porkbun API"""
    
    BASE_URL = "https://api.porkbun.com/api/json/v3"
    
    def __init__(self, api_key: str, secret_key: str):
        """
        Initialize Porkbun API client
        
        Args:
            api_key: Porkbun API key
            secret_key: Porkbun secret key
        """
        self.api_key = api_key
        self.secret_key = secret_key
    
    def _make_request(self, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """
        Make a request to Porkbun API
        
        Args:
            endpoint: API endpoint
            data: Additional data to send
            
        Returns:
            API response as dictionary
        """
        url = f"{self.BASE_URL}/{endpoint}"
        payload = {
            "apikey": self.api_key,
            "secretapikey": self.secret_key
        }
        if data:
            payload.update(data)
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
    
    def ping(self) -> bool:
        """
        Test API credentials
        
        Returns:
            True if credentials are valid
        """
        try:
            result = self._make_request("ping")
            return result.get("status") == "SUCCESS"
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False
    
    def retrieve_ssl_bundle(self, domain: str) -> Tuple[str, str, str]:
        """
        Retrieve SSL certificate bundle for a domain
        
        Args:
            domain: Domain name
            
        Returns:
            Tuple of (certificate_chain, private_key, public_key)
        """
        try:
            result = self._make_request(f"ssl/retrieve/{domain}")
            
            if result.get("status") != "SUCCESS":
                raise Exception(f"Failed to retrieve certificate: {result.get('message', 'Unknown error')}")
            
            cert_chain = result.get("certificatechain", "")
            private_key = result.get("privatekey", "")
            public_key = result.get("publickey", "")
            
            return cert_chain, private_key, public_key
            
        except Exception as e:
            logger.error(f"Failed to retrieve SSL bundle for {domain}: {e}")
            raise
