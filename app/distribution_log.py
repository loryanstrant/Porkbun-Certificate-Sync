"""
Distribution logging module
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class DistributionLog:
    """Manages distribution event logging"""
    
    def __init__(self, log_file: str = None):
        """
        Initialize distribution log manager
        
        Args:
            log_file: Path to log file (defaults to /app/config/distribution_log.json)
        """
        if log_file is None:
            log_file = "/app/config/distribution_log.json"
        
        self.log_file = log_file
        self.log_dir = Path(log_file).parent
        
        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize log file if it doesn't exist
        if not Path(log_file).exists():
            self._save_logs([])
    
    def _load_logs(self) -> List[Dict]:
        """
        Load logs from file
        
        Returns:
            List of log entries
        """
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load logs: {e}")
            return []
    
    def _save_logs(self, logs: List[Dict]):
        """
        Save logs to file
        
        Args:
            logs: List of log entries
        """
        try:
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save logs: {e}")
            raise
    
    def add_sync_event(self, domains: List[str], status: str, results: List[Dict] = None):
        """
        Add a certificate sync event to the log
        
        Args:
            domains: List of domains synced
            status: Status of the sync (success, error, partial)
            results: List of sync results per domain
        """
        logs = self._load_logs()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "certificate_sync",
            "status": status,
            "domains": domains,
            "results": results or []
        }
        
        logs.append(log_entry)
        self._save_logs(logs)
        logger.info(f"Logged certificate sync event: {status}")
    
    def add_distribution_event(self, domain: str, host: str, status: str, 
                              files: List[str] = None, error: str = None):
        """
        Add a certificate distribution event to the log
        
        Args:
            domain: Domain that was distributed
            host: Target host display name
            status: Status of the distribution (success, error)
            files: List of files distributed
            error: Error message if status is error
        """
        logs = self._load_logs()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "certificate_distribution",
            "domain": domain,
            "host": host,
            "status": status,
            "files": files or [],
            "error": error
        }
        
        logs.append(log_entry)
        self._save_logs(logs)
        logger.info(f"Logged distribution event for {host}: {status}")
    
    def add_bulk_distribution_event(self, results: List[Dict]):
        """
        Add a bulk distribution event to the log
        
        Args:
            results: List of distribution results for multiple hosts
        """
        logs = self._load_logs()
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "bulk_distribution",
            "results": results,
            "total_hosts": len(results),
            "successful": len([r for r in results if r.get("status") == "success"]),
            "failed": len([r for r in results if r.get("status") == "error"])
        }
        
        logs.append(log_entry)
        self._save_logs(logs)
        logger.info(f"Logged bulk distribution: {log_entry['successful']} succeeded, {log_entry['failed']} failed")
    
    def get_logs(self, limit: int = 100, event_type: str = None) -> List[Dict]:
        """
        Get logs with optional filtering
        
        Args:
            limit: Maximum number of logs to return
            event_type: Filter by event type (certificate_sync, certificate_distribution, bulk_distribution)
            
        Returns:
            List of log entries (most recent first)
        """
        logs = self._load_logs()
        
        # Filter by event type if specified
        if event_type:
            logs = [log for log in logs if log.get("event_type") == event_type]
        
        # Sort by timestamp (most recent first) and limit
        logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return logs[:limit]
    
    def clear_logs(self):
        """Clear all logs"""
        self._save_logs([])
        logger.info("Cleared all distribution logs")
    
    def get_stats(self) -> Dict:
        """
        Get statistics about distribution events
        
        Returns:
            Dictionary with statistics
        """
        logs = self._load_logs()
        
        total_syncs = len([log for log in logs if log.get("event_type") == "certificate_sync"])
        total_distributions = len([log for log in logs if log.get("event_type") in ["certificate_distribution", "bulk_distribution"]])
        
        successful_distributions = len([
            log for log in logs 
            if log.get("event_type") == "certificate_distribution" and log.get("status") == "success"
        ])
        
        failed_distributions = len([
            log for log in logs 
            if log.get("event_type") == "certificate_distribution" and log.get("status") == "error"
        ])
        
        return {
            "total_syncs": total_syncs,
            "total_distributions": total_distributions,
            "successful_distributions": successful_distributions,
            "failed_distributions": failed_distributions
        }
