"""Alerting system for trading bot events"""

import json
import requests
from typing import Dict, Optional, Any
from datetime import datetime
from loguru import logger


class AlertManager:
    """Manage alerts and notifications"""
    
    def __init__(self, config: dict):
        """
        Initialize alert manager.
        
        Args:
            config: Configuration dictionary with alerts settings
        """
        alerts_config = config.get('operations', {}).get('alerts', {})
        
        self.enabled = alerts_config.get('enabled', False)
        self.discord_webhook_url = alerts_config.get('discord_webhook_url', "")
        self.email_smtp_server = alerts_config.get('email_smtp_server', "")
        self.email_recipients = alerts_config.get('email_recipients', [])
        
        # Alert preferences
        self.alert_on_pause = alerts_config.get('alert_on_pause', True)
        self.alert_on_kill_switch = alerts_config.get('alert_on_kill_switch', True)
        self.alert_on_model_rotation = alerts_config.get('alert_on_model_rotation', True)
        self.alert_on_health_issues = alerts_config.get('alert_on_health_issues', True)
        
        logger.info(f"Initialized AlertManager (enabled={self.enabled})")
    
    def notify_event(
        self,
        event_type: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        severity: str = "INFO"
    ):
        """
        Send alert notification.
        
        Args:
            event_type: Type of event (e.g., 'PERFORMANCE_GUARD_PAUSED', 'KILL_SWITCH', 'HEALTH_ISSUE')
            message: Alert message
            context: Additional context dictionary
            severity: Severity level (INFO, WARNING, CRITICAL)
        """
        # Always log
        log_level = severity.lower()
        if log_level == "critical":
            logger.critical(f"[ALERT] {event_type}: {message}")
        elif log_level == "warning":
            logger.warning(f"[ALERT] {event_type}: {message}")
        else:
            logger.info(f"[ALERT] {event_type}: {message}")
        
        if not self.enabled:
            return
        
        # Check if this event type should trigger alerts
        should_alert = False
        if event_type == "PERFORMANCE_GUARD_PAUSED" and self.alert_on_pause:
            should_alert = True
        elif event_type == "KILL_SWITCH" and self.alert_on_kill_switch:
            should_alert = True
        elif event_type == "MODEL_ROTATION" and self.alert_on_model_rotation:
            should_alert = True
        elif event_type.startswith("HEALTH_") and self.alert_on_health_issues:
            should_alert = True
        elif severity == "CRITICAL":
            should_alert = True
        
        if not should_alert:
            return
        
        # Send to configured channels
        alert_data = {
            'event_type': event_type,
            'message': message,
            'severity': severity,
            'timestamp': datetime.utcnow().isoformat(),
            'context': context or {}
        }
        
        # Discord webhook
        if self.discord_webhook_url:
            self._send_discord_alert(alert_data)
        
        # Email (if configured)
        if self.email_smtp_server and self.email_recipients:
            self._send_email_alert(alert_data)
    
    def _send_discord_alert(self, alert_data: Dict[str, Any]):
        """Send alert to Discord webhook."""
        try:
            # Format Discord message
            severity_emoji = {
                "CRITICAL": "🔴",
                "WARNING": "🟡",
                "INFO": "🔵"
            }.get(alert_data['severity'], "⚪")
            
            embed = {
                "title": f"{severity_emoji} {alert_data['event_type']}",
                "description": alert_data['message'],
                "color": {
                    "CRITICAL": 15158332,  # Red
                    "WARNING": 16776960,   # Yellow
                    "INFO": 3447003        # Blue
                }.get(alert_data['severity'], 9807270),  # Gray
                "timestamp": alert_data['timestamp'],
                "fields": []
            }
            
            # Add context fields
            if alert_data['context']:
                for key, value in alert_data['context'].items():
                    embed['fields'].append({
                        "name": key,
                        "value": str(value),
                        "inline": True
                    })
            
            payload = {
                "embeds": [embed]
            }
            
            response = requests.post(
                self.discord_webhook_url,
                json=payload,
                timeout=5
            )
            response.raise_for_status()
            
        except Exception as e:
            logger.error(f"Error sending Discord alert: {e}")
    
    def _send_email_alert(self, alert_data: Dict[str, Any]):
        """Send alert via email (placeholder - requires SMTP setup)."""
        # This is a placeholder - full email implementation would require
        # smtplib and proper email formatting
        logger.warning(f"Email alerts not fully implemented. Event: {alert_data['event_type']}")
        # TODO: Implement email sending if needed

