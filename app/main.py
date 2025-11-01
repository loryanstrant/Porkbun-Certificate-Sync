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
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize configuration and sync
config = Config()
cert_sync = CertificateSync(config)

# Start scheduler if configured
try:
    cert_sync.start_scheduler()
except Exception as e:
    logger.error(f"Failed to start scheduler: {e}")


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@app.route('/api/domains', methods=['GET'])
def get_domains():
    """Get list of domains"""
    try:
        domains = config.get_domains()
        return jsonify({"domains": domains})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/domains', methods=['POST'])
def add_domain():
    """Add a new domain"""
    try:
        data = request.json
        domain = data.get('domain', '').strip()
        custom_name = data.get('custom_name', '').strip()
        alt_names = data.get('alt_names', [])
        
        if not domain:
            return jsonify({"error": "Domain is required"}), 400
        
        config.add_domain(domain, custom_name or None, alt_names)
        
        return jsonify({"status": "success", "message": f"Domain {domain} added"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to add domain: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/domains/<domain>', methods=['DELETE'])
def remove_domain(domain):
    """Remove a domain"""
    try:
        config.remove_domain(domain)
        return jsonify({"status": "success", "message": f"Domain {domain} removed"})
    except Exception as e:
        logger.error(f"Failed to remove domain: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/sync', methods=['POST'])
def trigger_sync():
    """Manually trigger certificate sync"""
    try:
        result = cert_sync.sync_all()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/sync/status', methods=['GET'])
def get_sync_status():
    """Get sync status"""
    try:
        status = cert_sync.get_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
