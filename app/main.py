"""
Main Flask application for Porkbun Certificate Sync
"""
import os
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from .config import Config
from .sync import CertificateSync
from .porkbun_api import PorkbunAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
# Generate a random secret key if not provided in production
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    import secrets
    secret_key = secrets.token_hex(32)
    logger.warning("No SECRET_KEY environment variable set. Using randomly generated key. Sessions will not persist across restarts.")
app.secret_key = secret_key

# Initialize configuration and sync
config = Config()
cert_sync = CertificateSync(config)

# Start scheduler if configured
try:
    cert_sync.start_scheduler()
except Exception as e:
    logger.error(f"Failed to start scheduler: {e}")


def sanitize_error_message(error: Exception) -> str:
    """
    Sanitize error messages to prevent stack trace exposure.
    
    Args:
        error: The exception to sanitize
        
    Returns:
        A safe error message string
    """
    # Maximum length for error messages to prevent exposure
    MAX_ERROR_LENGTH = 200
    
    # Only return safe, generic messages in production
    error_str = str(error)
    
    # Don't expose file paths, stack traces, or internal details
    if '/' in error_str or '\\' in error_str or 'Traceback' in error_str:
        return "An internal error occurred"
    
    # Return the error message if it's safe
    return error_str if error_str else "An error occurred"


@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get current settings"""
    try:
        api_key, secret_key = config.get_api_credentials()
        cert_config = config.get_certificate_config()
        schedule_config = config.get_schedule_config()
        
        return jsonify({
            "api": {
                "api_key": api_key,
                "secret_key": "***" if secret_key else "",
                "has_secret": bool(secret_key)
            },
            "certificates": cert_config,
            "schedule": schedule_config
        })
    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        return jsonify({"error": "Failed to load settings"}), 500


@app.route('/api/settings/api', methods=['POST'])
def update_api_settings():
    """Update API credentials"""
    try:
        data = request.json
        api_key = data.get('api_key', '')
        secret_key = data.get('secret_key', '')
        
        if not api_key or not secret_key:
            return jsonify({"error": "API key and secret key are required"}), 400
        
        # Test credentials
        api = PorkbunAPI(api_key, secret_key)
        if not api.ping():
            return jsonify({"error": "Invalid API credentials"}), 400
        
        config.set_api_credentials(api_key, secret_key)
        
        return jsonify({"status": "success", "message": "API credentials updated"})
    except Exception as e:
        logger.error(f"Failed to update API settings: {e}")
        return jsonify({"error": "Failed to update API settings"}), 500


@app.route('/api/settings/certificates', methods=['POST'])
def update_certificate_settings():
    """Update certificate settings"""
    try:
        data = request.json
        
        output_dir = data.get('output_dir')
        naming_format = data.get('naming_format')
        formats = data.get('formats')
        
        config.update_certificate_config(
            output_dir=output_dir,
            naming_format=naming_format,
            formats=formats
        )
        
        return jsonify({"status": "success", "message": "Certificate settings updated"})
    except Exception as e:
        logger.error(f"Failed to update certificate settings: {e}")
        return jsonify({"error": "Failed to update certificate settings"}), 500


@app.route('/api/settings/schedule', methods=['POST'])
def update_schedule_settings():
    """Update schedule settings"""
    try:
        data = request.json
        
        enabled = data.get('enabled', False)
        cron = data.get('cron', '0 2 * * *')
        
        config.update_schedule_config(enabled, cron)
        
        # Restart scheduler with new settings
        cert_sync.stop_scheduler()
        if enabled:
            cert_sync.start_scheduler()
        
        return jsonify({"status": "success", "message": "Schedule settings updated"})
    except Exception as e:
        logger.error(f"Failed to update schedule settings: {e}")
        return jsonify({"error": "Failed to update schedule settings"}), 500


@app.route('/api/domains', methods=['GET'])
def get_domains():
    """Get list of domains"""
    try:
        domains = config.get_domains()
        return jsonify({"domains": domains})
    except Exception as e:
        logger.error(f"Failed to get domains: {e}")
        return jsonify({"error": "Failed to load domains"}), 500


@app.route('/api/domains', methods=['POST'])
def add_domain():
    """Add a new domain"""
    try:
        data = request.json
        domain = data.get('domain', '').strip()
        custom_name = data.get('custom_name', '').strip()
        separator = data.get('separator', '_')
        alt_file_names = data.get('alt_file_names', [])
        
        if not domain:
            return jsonify({"error": "Domain is required"}), 400
        
        config.add_domain(domain, custom_name or None, separator, alt_file_names)
        
        return jsonify({"status": "success", "message": f"Domain {domain} added"})
    except ValueError as e:
        # ValueError messages are safe to return as they come from our own code
        # Maximum length for error messages to prevent exposure
        MAX_ERROR_LENGTH = 200
        error_msg = str(e)
        # Only return simple error messages, no stack traces
        if not error_msg or len(error_msg) > MAX_ERROR_LENGTH:
            error_msg = "Invalid domain configuration"
        return jsonify({"error": error_msg}), 400
    except Exception as e:
        logger.error(f"Failed to add domain: {e}")
        return jsonify({"error": "Failed to add domain"}), 500


@app.route('/api/domains/<domain>', methods=['PUT'])
def update_domain(domain):
    """Update an existing domain"""
    try:
        data = request.json
        new_domain = data.get('domain', '').strip()
        custom_name = data.get('custom_name', '').strip()
        separator = data.get('separator', '_')
        alt_file_names = data.get('alt_file_names', [])
        
        if not new_domain:
            return jsonify({"error": "Domain is required"}), 400
        
        config.update_domain(domain, new_domain, custom_name or None, separator, alt_file_names)
        
        return jsonify({"status": "success", "message": f"Domain {new_domain} updated"})
    except ValueError as e:
        # ValueError messages are safe to return as they come from our own code
        MAX_ERROR_LENGTH = 200
        error_msg = str(e)
        if not error_msg or len(error_msg) > MAX_ERROR_LENGTH:
            error_msg = "Invalid domain configuration"
        return jsonify({"error": error_msg}), 400
    except Exception as e:
        logger.error(f"Failed to update domain: {e}")
        return jsonify({"error": "Failed to update domain"}), 500


@app.route('/api/domains/<domain>', methods=['DELETE'])
def remove_domain(domain):
    """Remove a domain"""
    try:
        config.remove_domain(domain)
        return jsonify({"status": "success", "message": f"Domain {domain} removed"})
    except Exception as e:
        logger.error(f"Failed to remove domain: {e}")
        return jsonify({"error": "Failed to remove domain"}), 500


@app.route('/api/sync', methods=['POST'])
def trigger_sync():
    """Manually trigger certificate sync"""
    try:
        result = cert_sync.sync_all()
        # Sanitize result to prevent error exposure
        if result.get("status") == "error" and "error" in result:
            logger.error(f"Sync error: {result.get('error')}")
            return jsonify({"status": "error", "error": "Certificate sync failed"}), 500
        return jsonify(result)
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return jsonify({"error": "Certificate sync failed"}), 500


@app.route('/api/sync/status', methods=['GET'])
def get_sync_status():
    """Get sync status"""
    try:
        status = cert_sync.get_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        return jsonify({"error": "Failed to get sync status"}), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200


@app.route('/api/ssh-hosts', methods=['GET'])
def get_ssh_hosts():
    """Get list of SSH hosts"""
    try:
        hosts = cert_sync.ssh_config.get_ssh_hosts()
        # Remove password hashes from response
        safe_hosts = []
        for host in hosts:
            safe_host = host.copy()
            safe_host.pop('password_hash', None)
            safe_host['has_password'] = bool(host.get('password_hash'))
            safe_hosts.append(safe_host)
        return jsonify({"hosts": safe_hosts})
    except Exception as e:
        logger.error(f"Failed to get SSH hosts: {e}")
        return jsonify({"error": "Failed to load SSH hosts"}), 500


@app.route('/api/ssh-hosts', methods=['POST'])
def add_ssh_host():
    """Add a new SSH host"""
    try:
        data = request.json
        display_name = data.get('display_name', '').strip()
        hostname = data.get('hostname', '').strip()
        port = data.get('port', 22)
        username = data.get('username', '').strip()
        password = data.get('password', '')
        cert_path = data.get('cert_path', '').strip()
        
        if not all([display_name, hostname, username, password, cert_path]):
            return jsonify({"error": "All fields are required"}), 400
        
        try:
            port = int(port)
            if port < 1 or port > 65535:
                raise ValueError("Invalid port number")
        except ValueError:
            return jsonify({"error": "Invalid port number"}), 400
        
        cert_sync.ssh_config.add_ssh_host(
            display_name, hostname, port, username, password, cert_path
        )
        
        return jsonify({"status": "success", "message": f"SSH host {display_name} added"})
    except ValueError as e:
        # ValueError messages are safe to return as they come from our own validation
        error_msg = sanitize_error_message(e)
        return jsonify({"error": error_msg}), 400
    except Exception as e:
        logger.error(f"Failed to add SSH host: {e}")
        return jsonify({"error": "Failed to add SSH host"}), 500


@app.route('/api/ssh-hosts/<display_name>', methods=['PUT'])
def update_ssh_host(display_name):
    """Update an existing SSH host"""
    try:
        data = request.json
        new_display_name = data.get('display_name', '').strip()
        hostname = data.get('hostname', '').strip()
        port = data.get('port', 22)
        username = data.get('username', '').strip()
        password = data.get('password', '')  # Optional - if empty, keep existing
        cert_path = data.get('cert_path', '').strip()
        
        if not all([new_display_name, hostname, username, cert_path]):
            return jsonify({"error": "Display name, hostname, username, and cert path are required"}), 400
        
        try:
            port = int(port)
            if port < 1 or port > 65535:
                raise ValueError("Invalid port number")
        except ValueError:
            return jsonify({"error": "Invalid port number"}), 400
        
        cert_sync.ssh_config.update_ssh_host(
            display_name, new_display_name, hostname, port, username, 
            password if password else None, cert_path
        )
        
        return jsonify({"status": "success", "message": f"SSH host {new_display_name} updated"})
    except ValueError as e:
        # ValueError messages are safe to return as they come from our own validation
        error_msg = sanitize_error_message(e)
        return jsonify({"error": error_msg}), 400
    except Exception as e:
        logger.error(f"Failed to update SSH host: {e}")
        return jsonify({"error": "Failed to update SSH host"}), 500


@app.route('/api/ssh-hosts/<display_name>', methods=['DELETE'])
def remove_ssh_host(display_name):
    """Remove an SSH host"""
    try:
        cert_sync.ssh_config.remove_ssh_host(display_name)
        return jsonify({"status": "success", "message": f"SSH host {display_name} removed"})
    except Exception as e:
        logger.error(f"Failed to remove SSH host: {e}")
        return jsonify({"error": "Failed to remove SSH host"}), 500


@app.route('/api/distribution/logs', methods=['GET'])
def get_distribution_logs():
    """Get distribution logs"""
    try:
        limit = request.args.get('limit', 100, type=int)
        event_type = request.args.get('event_type', None)
        
        logs = cert_sync.distribution_log.get_logs(limit=limit, event_type=event_type)
        stats = cert_sync.distribution_log.get_stats()
        
        return jsonify({
            "logs": logs,
            "stats": stats
        })
    except Exception as e:
        logger.error(f"Failed to get distribution logs: {e}")
        return jsonify({"error": "Failed to get distribution logs"}), 500


@app.route('/api/distribution/test', methods=['POST'])
def test_ssh_connection():
    """Test SSH connection to a host"""
    try:
        data = request.json
        display_name = data.get('display_name')
        password = data.get('password')
        
        if not display_name or not password:
            return jsonify({"error": "Display name and password are required"}), 400
        
        host_config = cert_sync.ssh_config.get_ssh_host(display_name)
        if not host_config:
            return jsonify({"error": "SSH host not found"}), 404
        
        # Verify password
        from werkzeug.security import check_password_hash
        if not check_password_hash(host_config.get('password_hash'), password):
            return jsonify({"error": "Invalid password"}), 401
        
        # Test connection
        import paramiko
        ssh_client = paramiko.SSHClient()
        # SECURITY NOTE: AutoAddPolicy automatically accepts unknown host keys
        # This is used for ease of deployment but has security implications.
        # In production, consider using SSH key-based authentication with known_hosts validation
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            ssh_client.connect(
                hostname=host_config.get('hostname'),
                port=host_config.get('port', 22),
                username=host_config.get('username'),
                password=password,
                timeout=10
            )
            ssh_client.close()
            return jsonify({"status": "success", "message": "Connection successful"})
        except Exception as e:
            logger.error(f"SSH connection test failed: {e}")
            return jsonify({"status": "error", "error": "Connection test failed"}), 400
            
    except Exception as e:
        logger.error(f"Failed to test SSH connection: {e}")
        return jsonify({"error": "Failed to test connection"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
