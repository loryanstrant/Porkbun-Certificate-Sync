"""
Certificate synchronization and scheduling
"""
import logging
from datetime import datetime
from typing import List, Dict
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from .porkbun_api import PorkbunAPI
from .certificate_manager import CertificateManager
from .config import Config

logger = logging.getLogger(__name__)


class CertificateSync:
    """Handles certificate synchronization from Porkbun"""
    
    def __init__(self, config: Config):
        """
        Initialize certificate sync
        
        Args:
            config: Configuration manager
        """
        self.config = config
        self.scheduler = BackgroundScheduler()
        self.sync_status = {
            "last_sync": None,
            "status": "idle",
            "results": []
        }
    
    def sync_all(self) -> Dict:
        """
        Sync all configured domains
        
        Returns:
            Dictionary with sync results
        """
        logger.info("Starting certificate sync for all domains")
        self.sync_status["status"] = "running"
        results = []
        
        try:
            # Get API credentials
            api_key, secret_key = self.config.get_api_credentials()
            if not api_key or not secret_key:
                raise ValueError("API credentials not configured")
            
            # Initialize API client
            api = PorkbunAPI(api_key, secret_key)
            
            # Test API connection
            if not api.ping():
                raise ValueError("Failed to authenticate with Porkbun API")
            
            # Get certificate configuration
            cert_config = self.config.get_certificate_config()
            cert_manager = CertificateManager(cert_config.get("output_dir", "/app/certificates"))
            formats = cert_config.get("formats", ["pem"])
            
            # Sync each domain
            domains = self.config.get_domains()
            for domain_config in domains:
                domain = domain_config.get("domain")
                custom_name = domain_config.get("custom_name", domain)
                
                try:
                    logger.info(f"Syncing certificate for {domain}")
                    
                    # Retrieve certificate
                    cert_chain, private_key, public_key = api.retrieve_ssl_bundle(domain)
                    
                    # Save certificate
                    saved_files = cert_manager.save_certificate(
                        domain,
                        cert_chain,
                        private_key,
                        public_key,
                        custom_name,
                        formats
                    )
                    
                    results.append({
                        "domain": domain,
                        "status": "success",
                        "files": list(saved_files.values())
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to sync {domain}: {e}")
                    results.append({
                        "domain": domain,
                        "status": "error",
                        "error": str(e)
                    })
            
            self.sync_status["last_sync"] = datetime.now().isoformat()
            self.sync_status["status"] = "completed"
            self.sync_status["results"] = results
            
            logger.info(f"Certificate sync completed. {len([r for r in results if r['status'] == 'success'])} succeeded, {len([r for r in results if r['status'] == 'error'])} failed")
            
            return {
                "status": "success",
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Certificate sync failed: {e}")
            self.sync_status["status"] = "error"
            return {
                "status": "error",
                "error": str(e)
            }
    
    def start_scheduler(self):
        """Start the scheduler for automatic syncs"""
        schedule_config = self.config.get_schedule_config()
        
        if not schedule_config.get("enabled", False):
            logger.info("Scheduler is disabled")
            return
        
        cron_expr = schedule_config.get("cron", "0 2 * * *")
        
        try:
            # Remove existing jobs
            self.scheduler.remove_all_jobs()
            
            # Add new job
            self.scheduler.add_job(
                self.sync_all,
                CronTrigger.from_crontab(cron_expr),
                id='cert_sync',
                name='Certificate Sync',
                replace_existing=True
            )
            
            if not self.scheduler.running:
                self.scheduler.start()
            
            logger.info(f"Scheduler started with cron: {cron_expr}")
            
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise
    
    def stop_scheduler(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
    
    def get_status(self) -> Dict:
        """Get current sync status"""
        return self.sync_status
