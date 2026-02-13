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
    
    def _extract_intermediary_certs(self, cert_chain: str) -> str:
        """
        Extract intermediary certificates from the full certificate chain.
        The chain typically contains: leaf cert + intermediate(s) + root (optional)
        We want to extract everything except the first certificate.
        
        Args:
            cert_chain: Full certificate chain in PEM format
            
        Returns:
            Intermediary certificates as a PEM string (empty if none found)
        """
        # Split the chain into individual certificates
        certs = []
        chain_parts = cert_chain.split('-----BEGIN CERTIFICATE-----')
        
        for part in chain_parts[1:]:  # Skip the first empty part
            cert_data = '-----BEGIN CERTIFICATE-----' + part
            if '-----END CERTIFICATE-----' in cert_data:
                certs.append(cert_data.strip())
        
        # Return all certificates except the first one (leaf certificate)
        if len(certs) > 1:
            intermediary = '\n'.join(certs[1:])
            return intermediary
        else:
            return ""
    
    def save_certificate(self, domain: str, cert_chain: str, private_key: str, 
                        public_key: str, custom_name: str = None,
                        formats: List[str] = None, separator: str = "_",
                        alt_file_names: List[str] = None,
                        file_overrides: Dict[str, str] = None) -> Dict[str, str]:
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
            file_overrides: Optional dict to override specific file names
                           Keys: 'cert', 'chain', 'privkey', 'fullchain'
                           Values: custom file names (e.g., 'cert.pem', 'chain.pem')
            
        Returns:
            Dictionary mapping format to file path
        """
        if formats is None:
            formats = ["pem"]
        
        if alt_file_names is None:
            alt_file_names = []
        
        if file_overrides is None:
            file_overrides = {}
        
        name = custom_name or domain
        saved_files = {}
        
        # Extract intermediary certificates from the chain
        intermediary_certs = self._extract_intermediary_certs(cert_chain)
        
        # Build list of all names to save (primary + alternatives)
        all_names = [name] + alt_file_names
        
        try:
            for file_name in all_names:
                # Always save PEM format components
                if "pem" in formats:
                    # Determine file names (use overrides if provided, otherwise use default pattern)
                    if file_overrides:
                        # Use file overrides for custom naming
                        fullchain_filename = file_overrides.get('fullchain', f"{file_name}{separator}fullchain.pem")
                        key_filename = file_overrides.get('privkey', f"{file_name}{separator}private.key")
                        cert_filename = file_overrides.get('cert', f"{file_name}{separator}cert.pem")
                        chain_filename = file_overrides.get('chain', f"{file_name}{separator}chain.pem")
                    else:
                        # Use default naming pattern
                        fullchain_filename = f"{file_name}{separator}fullchain.pem"
                        key_filename = f"{file_name}{separator}private.key"
                        cert_filename = f"{file_name}{separator}cert.pem"
                        chain_filename = f"{file_name}{separator}chain.pem"
                    
                    # Save full chain
                    fullchain_path = os.path.join(self.output_dir, fullchain_filename)
                    with open(fullchain_path, 'w') as f:
                        f.write(cert_chain)
                    saved_files[f'{file_name}_fullchain'] = fullchain_path
                    
                    # Save private key
                    key_path = os.path.join(self.output_dir, key_filename)
                    with open(key_path, 'w') as f:
                        f.write(private_key)
                    saved_files[f'{file_name}_private_key'] = key_path
                    
                    # Save certificate
                    cert_path = os.path.join(self.output_dir, cert_filename)
                    with open(cert_path, 'w') as f:
                        f.write(public_key)
                    saved_files[f'{file_name}_certificate'] = cert_path
                    
                    # Save intermediary certificate chain (if any)
                    if intermediary_certs:
                        chain_path = os.path.join(self.output_dir, chain_filename)
                        with open(chain_path, 'w') as f:
                            f.write(intermediary_certs)
                        saved_files[f'{file_name}_chain'] = chain_path
                        logger.info(f"Saved intermediary certificates to {chain_filename}")
                
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
            cert_pem: Certificate in PEM format (or empty if should extract from chain)
            key_pem: Private key in PEM format
            chain_pem: Certificate chain in PEM format
            password: Password for PFX file (empty by default for compatibility)
            
        Returns:
            Path to PFX file
        """
        try:
            # Load the private key
            key = serialization.load_pem_private_key(
                key_pem.encode(),
                password=None,
                backend=default_backend()
            )
            
            # Try to load the certificate from cert_pem first
            cert = None
            try:
                if cert_pem and cert_pem.strip():
                    cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
                    logger.debug("Loaded certificate from cert_pem parameter")
            except Exception as e:
                logger.debug(f"Could not load certificate from cert_pem: {e}")
            
            # Parse all certificates from the chain
            all_chain_certs = []
            chain_parts = chain_pem.split('-----BEGIN CERTIFICATE-----')
            for part in chain_parts[1:]:  # Skip the first empty part
                cert_data = '-----BEGIN CERTIFICATE-----' + part
                try:
                    chain_cert = x509.load_pem_x509_certificate(
                        cert_data.encode(), 
                        default_backend()
                    )
                    all_chain_certs.append(chain_cert)
                except Exception:
                    continue
            
            # If we couldn't load the certificate from cert_pem, use the first one from the chain
            if cert is None:
                if not all_chain_certs:
                    raise ValueError("No valid certificates found in cert_pem or chain_pem")
                cert = all_chain_certs[0]
                ca_certs = all_chain_certs[1:] if len(all_chain_certs) > 1 else []
                logger.debug(f"Using first certificate from chain as main certificate, {len(ca_certs)} CA certificates")
            else:
                # Use all chain certificates as CA certificates
                ca_certs = all_chain_certs
                logger.debug(f"Using cert_pem as main certificate, {len(ca_certs)} CA certificates from chain")
            
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
