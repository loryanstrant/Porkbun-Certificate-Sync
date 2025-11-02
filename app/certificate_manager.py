"""
Certificate management and format conversion
"""
import os
import logging
from pathlib import Path
from typing import Dict, List
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs12

logger = logging.getLogger(__name__)


class CertificateManager:
    """Manages certificate storage and format conversion"""
    
    def __init__(self, output_dir: str = "/app/certificates"):
        """
        Initialize certificate manager
        
        Args:
            output_dir: Directory to store certificates
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def save_certificate(self, domain: str, cert_chain: str, private_key: str, 
                        public_key: str, custom_name: str = None,
                        formats: List[str] = None, separator: str = "_",
                        alt_file_names: List[str] = None) -> Dict[str, str]:
        """
        Save certificate files
        
        Args:
            domain: Domain name
            cert_chain: Certificate chain (PEM format)
            private_key: Private key (PEM format)
            public_key: Public key/certificate (PEM format)
            custom_name: Custom name for files (defaults to domain)
            formats: List of formats to save (pem, crt, key, pfx)
            separator: Separator for file names (_, -, or .)
            alt_file_names: Alternative file name variants to save
            
        Returns:
            Dictionary mapping format to file path
        """
        if formats is None:
            formats = ["pem"]
        
        if alt_file_names is None:
            alt_file_names = []
        
        name = custom_name or domain
        saved_files = {}
        
        # Build list of all names to save (primary + alternatives)
        all_names = [name] + alt_file_names
        
        try:
            for file_name in all_names:
                # Always save PEM format components
                if "pem" in formats:
                    # Save full chain
                    fullchain_path = os.path.join(self.output_dir, f"{file_name}{separator}fullchain.pem")
                    with open(fullchain_path, 'w') as f:
                        f.write(cert_chain)
                    saved_files[f'{file_name}_fullchain'] = fullchain_path
                    
                    # Save private key
                    key_path = os.path.join(self.output_dir, f"{file_name}{separator}private.key")
                    with open(key_path, 'w') as f:
                        f.write(private_key)
                    saved_files[f'{file_name}_private_key'] = key_path
                    
                    # Save certificate
                    cert_path = os.path.join(self.output_dir, f"{file_name}{separator}cert.pem")
                    with open(cert_path, 'w') as f:
                        f.write(public_key)
                    saved_files[f'{file_name}_certificate'] = cert_path
                
                # Save as separate .crt and .key files
                if "crt" in formats:
                    crt_path = os.path.join(self.output_dir, f"{file_name}.crt")
                    with open(crt_path, 'w') as f:
                        f.write(cert_chain)
                    saved_files[f'{file_name}_crt'] = crt_path
                
                if "key" in formats:
                    key_path = os.path.join(self.output_dir, f"{file_name}.key")
                    with open(key_path, 'w') as f:
                        f.write(private_key)
                    saved_files[f'{file_name}_key'] = key_path
                
                # Convert to PFX/PKCS12 format
                if "pfx" in formats:
                    pfx_path = self._convert_to_pfx(file_name, public_key, private_key, cert_chain)
                    if pfx_path:
                        saved_files[f'{file_name}_pfx'] = pfx_path
            
            logger.info(f"Saved certificates for {domain} as {name} (with {len(alt_file_names)} alternative names)")
            return saved_files
            
        except Exception as e:
            logger.error(f"Failed to save certificates for {domain}: {e}")
            raise
    
    def _convert_to_pfx(self, name: str, cert_pem: str, key_pem: str, 
                       chain_pem: str, password: str = "") -> str:
        """
        Convert PEM certificates to PFX/PKCS12 format
        
        SECURITY NOTE: PFX files are created without password protection by default.
        This means the private key is not encrypted in the PFX file.
        Users should secure the certificate directory with appropriate file permissions.
        
        Args:
            name: Base name for output file
            cert_pem: Certificate in PEM format
            key_pem: Private key in PEM format
            chain_pem: Certificate chain in PEM format
            password: Password for PFX file (empty by default for compatibility)
            
        Returns:
            Path to PFX file
        """
        try:
            # Load the certificate
            cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
            
            # Load the private key
            key = serialization.load_pem_private_key(
                key_pem.encode(),
                password=None,
                backend=default_backend()
            )
            
            # Load additional certificates (chain)
            ca_certs = []
            # Split chain into individual certificates
            chain_parts = chain_pem.split('-----BEGIN CERTIFICATE-----')
            for part in chain_parts[1:]:  # Skip the first empty part
                cert_data = '-----BEGIN CERTIFICATE-----' + part
                try:
                    ca_cert = x509.load_pem_x509_certificate(
                        cert_data.encode(), 
                        default_backend()
                    )
                    ca_certs.append(ca_cert)
                except Exception:
                    continue
            
            # Create PKCS12
            pfx_data = pkcs12.serialize_key_and_certificates(
                name.encode(),
                key,
                cert,
                ca_certs if ca_certs else None,
                serialization.BestAvailableEncryption(password.encode()) if password else serialization.NoEncryption()
            )
            
            # Save to file
            pfx_path = os.path.join(self.output_dir, f"{name}.pfx")
            with open(pfx_path, 'wb') as f:
                f.write(pfx_data)
            
            logger.info(f"Created PFX file: {pfx_path}")
            return pfx_path
            
        except Exception as e:
            logger.error(f"Failed to convert to PFX: {e}")
            return None
    
    def list_certificates(self) -> List[str]:
        """
        List all certificate files in output directory
        
        Returns:
            List of certificate file paths
        """
        try:
            files = []
            for file in os.listdir(self.output_dir):
                if file.endswith(('.pem', '.key', '.crt', '.pfx')):
                    files.append(os.path.join(self.output_dir, file))
            return sorted(files)
        except Exception as e:
            logger.error(f"Failed to list certificates: {e}")
            return []
