"""
SSH certificate distribution
"""
import os
import logging
import warnings
from typing import Dict, List, Optional
import paramiko

# Suppress paramiko deprecation warnings about TripleDES
warnings.filterwarnings('ignore', category=DeprecationWarning, module='paramiko')

logger = logging.getLogger(__name__)


class SSHDistributor:
    """Handles certificate distribution via SSH"""
    
    def __init__(self, ssh_config):
        """
        Initialize SSH distributor
        
        Args:
            ssh_config: SSH configuration manager instance
        """
        self.ssh_config = ssh_config
    
    def distribute_to_host(self, host_config: Dict, certificate_files: List[str]) -> Dict:
        """
        Distribute certificates to a single host
        
        Args:
            host_config: SSH host configuration
            certificate_files: List of certificate file paths to distribute
            
        Returns:
            Dictionary with distribution result
        """
        display_name = host_config.get("display_name")
        hostname = host_config.get("hostname")
        port = host_config.get("port", 22)
        username = host_config.get("username")
        password_hash = host_config.get("password_hash")
        cert_path = host_config.get("cert_path")
        
        logger.info(f"Starting distribution to {display_name} ({hostname})")
        
        # We need to store plain password temporarily for connection
        # In production, consider using SSH keys instead
        ssh_client = None
        sftp = None
        
        try:
            # Create SSH client
            ssh_client = paramiko.SSHClient()
            # SECURITY NOTE: AutoAddPolicy automatically accepts unknown host keys
            # This is used for ease of deployment but has security implications.
            # In production, consider using SSH key-based authentication with known_hosts validation
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Note: password_hash is actually the hashed password from storage
            # We can't reverse it, so we need to handle this differently
            # For now, we'll pass the password directly in the API call
            # and only hash it for storage
            
            # This is a design limitation - we'll need to get the plain password
            # from the caller when distributing
            raise ValueError("Cannot retrieve plain password from hash - password must be provided")
            
        except Exception as e:
            logger.error(f"Failed to distribute to {display_name}: {e}")
            return {
                "host": display_name,
                "status": "error",
                "error": str(e)
            }
        finally:
            if sftp:
                sftp.close()
            if ssh_client:
                ssh_client.close()
    
    def distribute_to_host_with_password(self, host_config: Dict, password: str, 
                                        certificate_files: List[str]) -> Dict:
        """
        Distribute certificates to a single host with plain password
        
        Args:
            host_config: SSH host configuration
            password: Plain text password for SSH connection
            certificate_files: List of certificate file paths to distribute
            
        Returns:
            Dictionary with distribution result
        """
        display_name = host_config.get("display_name")
        hostname = host_config.get("hostname")
        port = host_config.get("port", 22)
        username = host_config.get("username")
        cert_path = host_config.get("cert_path")
        use_sudo = host_config.get("use_sudo", False)
        
        logger.info(f"Starting distribution to {display_name} ({hostname})")
        
        ssh_client = None
        sftp = None
        distributed_files = []
        
        try:
            # Create SSH client
            ssh_client = paramiko.SSHClient()
            # SECURITY NOTE: AutoAddPolicy automatically accepts unknown host keys
            # This is used for ease of deployment but has security implications.
            # In production, consider using SSH key-based authentication with known_hosts validation
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect to host
            ssh_client.connect(
                hostname=hostname,
                port=port,
                username=username,
                password=password,
                timeout=30
            )
            
            # Open SFTP session
            sftp = ssh_client.open_sftp()
            
            # Ensure remote directory exists
            if use_sudo:
                # When using sudo, we need to create directory via shell command
                self._create_remote_directory_with_sudo(ssh_client, cert_path, password)
            else:
                try:
                    sftp.stat(cert_path)
                except FileNotFoundError:
                    # Create directory if it doesn't exist
                    self._create_remote_directory(sftp, cert_path)
            
            # Upload each certificate file
            for local_file in certificate_files:
                if not os.path.exists(local_file):
                    logger.warning(f"Local file not found: {local_file}")
                    continue
                
                filename = os.path.basename(local_file)
                remote_file = os.path.join(cert_path, filename).replace('\\', '/')
                
                if use_sudo:
                    # Upload to temp location first, then move with sudo
                    temp_file = f"/tmp/{filename}"
                    sftp.put(local_file, temp_file)
                    
                    # Move file with sudo
                    move_cmd = f"sudo mv {temp_file} {remote_file}"
                    stdin, stdout, stderr = ssh_client.exec_command(move_cmd, get_pty=True)
                    
                    # Send password if sudo asks for it
                    if stdin.channel.send_ready():
                        stdin.write(password + '\n')
                        stdin.flush()
                    
                    # Wait for command to complete
                    exit_status = stdout.channel.recv_exit_status()
                    if exit_status != 0:
                        error_output = stderr.read().decode()
                        logger.error(f"Failed to move file with sudo: {error_output}")
                        continue
                    
                    # Set proper permissions with sudo
                    chmod_cmd = f"sudo chmod 644 {remote_file}"
                    stdin, stdout, stderr = ssh_client.exec_command(chmod_cmd, get_pty=True)
                    if stdin.channel.send_ready():
                        stdin.write(password + '\n')
                        stdin.flush()
                    stdout.channel.recv_exit_status()
                else:
                    # Upload file directly (overwrites if exists)
                    sftp.put(local_file, remote_file)
                
                distributed_files.append(filename)
                logger.info(f"Uploaded {filename} to {display_name}:{remote_file}")
            
            logger.info(f"Successfully distributed {len(distributed_files)} files to {display_name}")
            
            return {
                "host": display_name,
                "status": "success",
                "files": distributed_files,
                "count": len(distributed_files)
            }
            
        except paramiko.AuthenticationException as e:
            logger.error(f"Authentication failed for {display_name}: {e}")
            return {
                "host": display_name,
                "status": "error",
                "error": "Authentication failed"
            }
        except paramiko.SSHException as e:
            logger.error(f"SSH error for {display_name}: {e}")
            return {
                "host": display_name,
                "status": "error",
                "error": f"SSH connection error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Failed to distribute to {display_name}: {e}")
            return {
                "host": display_name,
                "status": "error",
                "error": str(e)
            }
        finally:
            if sftp:
                sftp.close()
            if ssh_client:
                ssh_client.close()
    
    def _create_remote_directory(self, sftp, path: str):
        """
        Recursively create remote directory
        
        Args:
            sftp: SFTP client
            path: Remote directory path
        """
        dirs = []
        while path and path != '/':
            dirs.append(path)
            path = os.path.dirname(path)
        
        dirs.reverse()
        
        for directory in dirs:
            try:
                sftp.stat(directory)
            except FileNotFoundError:
                sftp.mkdir(directory)
    
    def _create_remote_directory_with_sudo(self, ssh_client, path: str, password: str):
        """
        Create remote directory using sudo
        
        Args:
            ssh_client: SSH client
            path: Remote directory path
            password: Password for sudo
        """
        # Create directory with sudo
        mkdir_cmd = f"sudo mkdir -p {path}"
        stdin, stdout, stderr = ssh_client.exec_command(mkdir_cmd, get_pty=True)
        
        # Send password if sudo asks for it
        if stdin.channel.send_ready():
            stdin.write(password + '\n')
            stdin.flush()
        
        # Wait for command to complete
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            error_output = stderr.read().decode()
            raise Exception(f"Failed to create directory with sudo: {error_output}")
        
        # Set permissions so we can write to it
        chmod_cmd = f"sudo chmod 755 {path}"
        stdin, stdout, stderr = ssh_client.exec_command(chmod_cmd, get_pty=True)
        if stdin.channel.send_ready():
            stdin.write(password + '\n')
            stdin.flush()
        stdout.channel.recv_exit_status()
    
    def distribute_to_all_hosts(self, certificate_files: List[str]) -> List[Dict]:
        """
        Distribute certificates to all configured hosts
        
        Args:
            certificate_files: List of certificate file paths to distribute
            
        Returns:
            List of distribution results for each host
        """
        hosts = self.ssh_config.get_ssh_hosts()
        results = []
        
        if not hosts:
            logger.info("No SSH hosts configured")
            return results
        
        logger.info(f"Distributing certificates to {len(hosts)} hosts")
        
        for host in hosts:
            display_name = host.get("display_name")
            
            # Get decrypted password
            password = self.ssh_config.get_decrypted_password(display_name)
            
            if not password:
                logger.error(f"Could not retrieve password for {display_name}")
                result = {
                    "host": display_name,
                    "status": "error",
                    "error": "Could not decrypt password - encryption key may have changed"
                }
                results.append(result)
                continue
            
            # Distribute to this host
            result = self.distribute_to_host_with_password(host, password, certificate_files)
            results.append(result)
        
        return results
