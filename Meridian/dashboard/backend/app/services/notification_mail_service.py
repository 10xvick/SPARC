"""
Mail notification service for RBAC credential emails.
"""
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from app.utils.json_handler import load_json_safe, save_json_atomic

PROJECT_ROOT = Path(__file__).resolve().parents[4]
MAIL_CONFIG_FILE = os.getenv(
    "TEAMSIGHT_MAIL_CONFIG_FILE",
    str(PROJECT_ROOT / "config" / "mail_config.json"),
)

_ALLOWED_FROM_DOMAIN = "hcl-software.com"
_ALLOWED_TO_DOMAINS = {"hcl.com", "hcl-software.com"}
_CREDENTIALS_BCC = "user@hcl-software.com.example"
_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+)$")


class NotificationMailService:
    def __init__(self) -> None:
        self.mail_config_file = MAIL_CONFIG_FILE

    def _default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "smtp_host": "10.222.2.80",
            "smtp_port": 25,
            "use_tls": False,
            "from_address": "user@hcl-software.com.example",
            "timeout_seconds": 20,
        }

    def get_config(self) -> Dict[str, Any]:
        data = load_json_safe(self.mail_config_file, self._default_config())
        config = self._default_config()
        if isinstance(data, dict):
            config.update({k: v for k, v in data.items() if k in config})
        return config

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        config = self.get_config()
        config.update({k: v for k, v in updates.items() if k in config})
        validated = self._validate_config(config)
        save_json_atomic(self.mail_config_file, validated)
        return validated

    def _validate_email(self, value: str) -> Optional[str]:
        if not value:
            return None
        match = _EMAIL_PATTERN.match(value.strip())
        if not match:
            return None
        return value.strip()

    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        validated = self._default_config()

        validated["enabled"] = bool(config.get("enabled", validated["enabled"]))
        validated["smtp_host"] = str(config.get("smtp_host", validated["smtp_host"]))
        validated["smtp_port"] = int(config.get("smtp_port", validated["smtp_port"]))
        validated["use_tls"] = bool(config.get("use_tls", validated["use_tls"]))
        validated["timeout_seconds"] = int(config.get("timeout_seconds", validated["timeout_seconds"]))

        from_address = self._validate_email(str(config.get("from_address", validated["from_address"])))
        if not from_address:
            raise ValueError("Invalid from address format")

        from_domain = from_address.split("@", 1)[1].lower()
        if from_domain != _ALLOWED_FROM_DOMAIN:
            raise ValueError("From address must use @hcl-software.com domain")

        if validated["smtp_port"] <= 0:
            raise ValueError("SMTP port must be a positive number")
        if validated["timeout_seconds"] <= 0:
            raise ValueError("Timeout must be a positive number")

        validated["from_address"] = from_address
        return validated

    def _is_allowed_recipient(self, to_address: str) -> bool:
        normalized = self._validate_email(to_address)
        if not normalized:
            return False
        domain = normalized.split("@", 1)[1].lower()
        return domain in _ALLOWED_TO_DOMAINS

    def _build_credentials_email(
        self,
        *,
        user_name: str,
        user_sapid: str,
        password: str,
        mode: Literal["create", "reset"],
        dashboard_url: str,
        from_address: str,
        to_address: str,
        bcc_address: str,
    ) -> EmailMessage:
        subject = "TeamSight - New Account Credentials" if mode == "create" else "TeamSight - Password Reset"
        intro_line = (
            "A TeamSight dashboard account has been created for you by an administrator."
            if mode == "create"
            else "Your TeamSight dashboard password has been reset by an administrator."
        )

        body = "\n".join([
            f"Dear {user_name},",
            "",
            intro_line,
            "",
            f"Password: {password}",
            "",
            "Login Instructions:",
            f"1. Go to: {dashboard_url}",
            f"2. Enter SAPID: {user_sapid}",
            "3. Enter the password above",
            "4. After login, change your password via \"Change Password\" in the user menu",
            "",
            "WARNING: This password will not be resent. Save it securely.",
            "",
            "---",
            "TeamSight Admin",
            "Employee Metrics Dashboard",
        ])

        message = EmailMessage()
        message["From"] = from_address
        message["To"] = to_address
        message["Bcc"] = bcc_address
        message["Subject"] = subject
        message.set_content(body)
        return message

    def send_credentials_email(
        self,
        *,
        to_address: Optional[str],
        user_name: str,
        user_sapid: str,
        password: str,
        mode: Literal["create", "reset"],
        dashboard_url: str,
    ) -> Dict[str, str]:
        config = self.get_config()

        if not config.get("enabled", False):
            return {
                "status": "skipped",
                "message": "Mail notifications are disabled in configuration",
            }

        if not to_address:
            return {
                "status": "skipped",
                "message": "User email is not configured",
            }

        if not self._is_allowed_recipient(to_address):
            return {
                "status": "failed",
                "message": "Recipient domain must be @hcl.com or @hcl-software.com",
            }

        if not self._is_allowed_recipient(_CREDENTIALS_BCC):
            return {
                "status": "failed",
                "message": "Configured BCC address is invalid",
            }

        message = self._build_credentials_email(
            user_name=user_name,
            user_sapid=user_sapid,
            password=password,
            mode=mode,
            dashboard_url=dashboard_url,
            from_address=config["from_address"],
            to_address=to_address,
            bcc_address=_CREDENTIALS_BCC,
        )

        try:
            with smtplib.SMTP(
                str(config["smtp_host"]),
                int(config["smtp_port"]),
                timeout=int(config["timeout_seconds"]),
            ) as server:
                if config.get("use_tls"):
                    server.starttls()
                server.send_message(message)
            return {
                "status": "sent",
                "message": f"Email sent to {to_address} (BCC: {_CREDENTIALS_BCC})",
            }
        except Exception as exc:
            return {
                "status": "failed",
                "message": f"Failed to send email: {exc}",
            }
