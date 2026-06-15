"""
Audit trail service for tracking login and activity audit events.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.utils.json_handler import load_json_safe, save_json_atomic

PROJECT_ROOT = Path(__file__).resolve().parents[4]
AUDIT_LOGINS_FILE = os.getenv(
    "TEAMSIGHT_AUDIT_LOGINS_FILE",
    str(PROJECT_ROOT / "data" / "audit_login_events.json"),
)


class AuditTrailService:
    """Service to persist and query audit events."""

    def __init__(self) -> None:
        self.audit_file = AUDIT_LOGINS_FILE
        self._lock = threading.Lock()

    @staticmethod
    def _to_iso_utc(value: datetime | None = None) -> str:
        now = value or datetime.now(timezone.utc)
        return now.astimezone(timezone.utc).replace(microsecond=0).isoformat()

    @staticmethod
    def _safe_text(value: Any, max_len: int = 256) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if len(text) > max_len:
            return text[:max_len]
        return text

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        if not value:
            return None
        raw = value.strip()
        if not raw:
            return None

        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass

        try:
            day = datetime.strptime(raw, "%Y-%m-%d")
            return day.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def _load_events(self) -> list[dict[str, Any]]:
        payload = load_json_safe(self.audit_file, {"events": []})
        events = payload.get("events", [])
        if isinstance(events, list):
            return events
        return []

    def _save_events(self, events: list[dict[str, Any]]) -> None:
        save_json_atomic(self.audit_file, {"events": events})

    @staticmethod
    def _safe_json(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            if isinstance(value, str) and len(value) > 500:
                return value[:500]
            return value
        if isinstance(value, list):
            return [AuditTrailService._safe_json(item) for item in value[:50]]
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for key, item in list(value.items())[:50]:
                cleaned[str(key)] = AuditTrailService._safe_json(item)
            return cleaned
        return str(value)

    def _normalize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        event_type = self._safe_text(event.get("event_type"), 64)
        # Backward compatibility: old records are login events.
        if not event_type:
            event_type = "login"

        return {
            "timestamp": self._safe_text(event.get("timestamp"), 64),
            "event_type": event_type,
            "event_name": self._safe_text(event.get("event_name"), 128),
            "sapid": self._safe_text(event.get("sapid"), 64),
            "user_id": event.get("user_id"),
            "user_name": self._safe_text(event.get("user_name"), 128),
            "role": self._safe_text(event.get("role"), 64),
            "success": bool(event.get("success", False)) if event_type == "login" else None,
            "failure_reason": self._safe_text(event.get("failure_reason"), 128),
            "ip_address": self._safe_text(event.get("ip_address"), 64),
            "user_agent": self._safe_text(event.get("user_agent"), 300),
            "details": self._safe_json(event.get("details")),
        }

    def record_event(
        self,
        *,
        event_type: str,
        event_name: str,
        sapid: str,
        user_id: int | None = None,
        user_name: str | None = None,
        role: str | None = None,
        success: bool | None = None,
        failure_reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        event = {
            "timestamp": self._to_iso_utc(),
            "event_type": self._safe_text(event_type, 64),
            "event_name": self._safe_text(event_name, 128),
            "sapid": self._safe_text(sapid, 64),
            "user_id": user_id,
            "user_name": self._safe_text(user_name, 128),
            "role": self._safe_text(role, 64),
            "success": bool(success) if success is not None else None,
            "failure_reason": self._safe_text(failure_reason, 128),
            "ip_address": self._safe_text(ip_address, 64),
            "user_agent": self._safe_text(user_agent, 300),
            "details": self._safe_json(details or {}),
        }

        with self._lock:
            events = self._load_events()
            events.append(event)

            if len(events) > 20000:
                events = events[-20000:]

            self._save_events(events)

    def record_login_event(
        self,
        *,
        sapid: str,
        success: bool,
        user_id: int | None = None,
        user_name: str | None = None,
        role: str | None = None,
        failure_reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Append a login event entry to audit storage."""
        self.record_event(
            event_type="login",
            event_name="login_success" if success else "login_failed",
            sapid=sapid,
            user_id=user_id,
            user_name=user_name,
            role=role,
            success=success,
            failure_reason=failure_reason,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def record_system_admin_event(
        self,
        *,
        sapid: str,
        user_id: int | None,
        user_name: str,
        role: str,
        method: str,
        path: str,
        ip_address: str | None,
        user_agent: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        method_upper = self._safe_text(method, 16).upper()
        event_type = "system_admin_access" if method_upper in {"GET", "HEAD", "OPTIONS"} else "system_admin_change"
        event_name = f"{method_upper} {self._safe_text(path, 180)}"
        self.record_event(
            event_type=event_type,
            event_name=event_name,
            sapid=sapid,
            user_id=user_id,
            user_name=user_name,
            role=role,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )

    def record_report_access_event(
        self,
        *,
        sapid: str,
        user_id: int | None,
        user_name: str,
        role: str,
        method: str,
        path: str,
        ip_address: str | None,
        user_agent: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        method_upper = self._safe_text(method, 16).upper()
        event_name = f"{method_upper} {self._safe_text(path, 180)}"
        self.record_event(
            event_type="report_access",
            event_name=event_name,
            sapid=sapid,
            user_id=user_id,
            user_name=user_name,
            role=role,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )

    def record_dashboard_access_event(
        self,
        *,
        sapid: str,
        user_id: int | None,
        user_name: str,
        role: str,
        method: str,
        path: str,
        ip_address: str | None,
        user_agent: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        method_upper = self._safe_text(method, 16).upper()
        event_name = f"{method_upper} {self._safe_text(path, 180)}"
        self.record_event(
            event_type="dashboard_access",
            event_name=event_name,
            sapid=sapid,
            user_id=user_id,
            user_name=user_name,
            role=role,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )

    def record_configuration_event(
        self,
        *,
        sapid: str,
        user_id: int | None,
        user_name: str,
        role: str,
        method: str,
        path: str,
        ip_address: str | None,
        user_agent: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        method_upper = self._safe_text(method, 16).upper()
        event_type = "configuration_access" if method_upper in {"GET", "HEAD", "OPTIONS"} else "configuration_change"
        event_name = f"{method_upper} {self._safe_text(path, 180)}"
        self.record_event(
            event_type=event_type,
            event_name=event_name,
            sapid=sapid,
            user_id=user_id,
            user_name=user_name,
            role=role,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )

    def list_events(
        self,
        *,
        event_type: str | None = None,
        sapid: str | None = None,
        role: str | None = None,
        success: bool | None = None,
        search: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        offset: int = 0,
        limit: int = 500,
    ) -> dict[str, Any]:
        start_dt = self._parse_datetime(start_date or "")
        end_dt = self._parse_datetime(end_date or "")
        if end_dt and len((end_date or "").strip()) == 10:
            end_dt = end_dt + timedelta(days=1)

        raw_events = self._load_events()
        events = [self._normalize_event(item) for item in raw_events]
        events = sorted(events, key=lambda item: str(item.get("timestamp", "")), reverse=True)

        event_type_filter = (event_type or "").strip().lower()
        search_term = (search or "").strip().lower()

        filtered: list[dict[str, Any]] = []
        for event in events:
            event_ts = self._parse_datetime(str(event.get("timestamp", "")))
            if start_dt and (event_ts is None or event_ts < start_dt):
                continue
            if end_dt and (event_ts is None or event_ts >= end_dt):
                continue
            if event_type_filter and event_type_filter != "all" and str(event.get("event_type", "")).lower() != event_type_filter:
                continue
            if sapid and str(event.get("sapid", "")) != sapid:
                continue
            if role and str(event.get("role", "")) != role:
                continue
            if success is not None:
                if event.get("event_type") != "login":
                    continue
                if bool(event.get("success", False)) != success:
                    continue

            if search_term:
                details_blob = event.get("details")
                details_text = ""
                if isinstance(details_blob, dict):
                    details_text = " ".join(f"{k}:{v}" for k, v in details_blob.items())
                haystack = " ".join(
                    [
                        str(event.get("event_type", "")),
                        str(event.get("event_name", "")),
                        str(event.get("sapid", "")),
                        str(event.get("user_name", "")),
                        str(event.get("role", "")),
                        str(event.get("ip_address", "")),
                        str(event.get("failure_reason", "")),
                        details_text,
                    ]
                ).lower()
                if search_term not in haystack:
                    continue

            filtered.append(event)

        safe_limit = max(1, min(limit, 5000))
        safe_offset = max(0, offset)
        visible = filtered[safe_offset : safe_offset + safe_limit]

        login_events = [item for item in filtered if item.get("event_type") == "login"]
        success_count = sum(1 for item in login_events if bool(item.get("success")))
        failed_count = len(login_events) - success_count
        admin_access_count = sum(1 for item in filtered if item.get("event_type") == "system_admin_access")
        admin_change_count = sum(1 for item in filtered if item.get("event_type") == "system_admin_change")
        report_access_count = sum(1 for item in filtered if item.get("event_type") == "report_access")
        dashboard_access_count = sum(1 for item in filtered if item.get("event_type") == "dashboard_access")
        configuration_access_count = sum(1 for item in filtered if item.get("event_type") == "configuration_access")
        configuration_change_count = sum(1 for item in filtered if item.get("event_type") == "configuration_change")
        unique_users = {
            str(item.get("sapid", "")).strip()
            for item in filtered
            if str(item.get("sapid", "")).strip()
        }
        unique_targets = {
            str((item.get("details") or {}).get("path", "")).strip()
            for item in filtered
            if isinstance(item.get("details"), dict) and str((item.get("details") or {}).get("path", "")).strip()
        }

        by_day: dict[str, dict[str, Any]] = {}
        by_user: dict[str, dict[str, Any]] = {}
        for item in filtered:
            date_key = str(item.get("timestamp", ""))[:10]
            if date_key:
                day_entry = by_day.setdefault(
                    date_key,
                    {
                        "date": date_key,
                        "count": 0,
                        "successful": 0,
                        "failed": 0,
                        "admin_access": 0,
                        "admin_change": 0,
                        "report_access": 0,
                        "dashboard_access": 0,
                        "configuration_access": 0,
                        "configuration_change": 0,
                    },
                )
                day_entry["count"] += 1
                if item.get("event_type") == "login":
                    if bool(item.get("success")):
                        day_entry["successful"] += 1
                    else:
                        day_entry["failed"] += 1
                elif item.get("event_type") == "system_admin_access":
                    day_entry["admin_access"] += 1
                elif item.get("event_type") == "system_admin_change":
                    day_entry["admin_change"] += 1
                elif item.get("event_type") == "report_access":
                    day_entry["report_access"] += 1
                elif item.get("event_type") == "dashboard_access":
                    day_entry["dashboard_access"] += 1
                elif item.get("event_type") == "configuration_access":
                    day_entry["configuration_access"] += 1
                elif item.get("event_type") == "configuration_change":
                    day_entry["configuration_change"] += 1

            user_key = str(item.get("sapid", "")).strip()
            if user_key:
                user_entry = by_user.setdefault(
                    user_key,
                    {
                        "sapid": user_key,
                        "name": str(item.get("user_name", "")),
                        "count": 0,
                        "successful": 0,
                        "failed": 0,
                        "admin_changes": 0,
                    },
                )
                user_entry["count"] += 1
                if item.get("event_type") == "login":
                    if bool(item.get("success")):
                        user_entry["successful"] += 1
                    else:
                        user_entry["failed"] += 1
                if item.get("event_type") == "system_admin_change":
                    user_entry["admin_changes"] += 1

        return {
            "data": visible,
            "total_filtered": len(filtered),
            "summary": {
                "total_events": len(filtered),
                "total_logins": len(login_events),
                "successful_logins": success_count,
                "failed_logins": failed_count,
                "admin_access_events": admin_access_count,
                "admin_change_events": admin_change_count,
                "report_access_events": report_access_count,
                "dashboard_access_events": dashboard_access_count,
                "configuration_access_events": configuration_access_count,
                "configuration_change_events": configuration_change_count,
                "unique_users": len(unique_users),
                "unique_targets": len(unique_targets),
                "last_event_at": filtered[0].get("timestamp") if filtered else None,
                "by_day": sorted(by_day.values(), key=lambda x: x["date"]),
                "top_users": sorted(
                    by_user.values(),
                    key=lambda x: (x["count"], x["successful"]),
                    reverse=True,
                )[:10],
            },
            "filters": {
                "sapids": sorted(
                    {
                        str(item.get("sapid", "")).strip()
                        for item in events
                        if str(item.get("sapid", "")).strip()
                    }
                ),
                "roles": sorted(
                    {
                        str(item.get("role", "")).strip()
                        for item in events
                        if str(item.get("role", "")).strip()
                    }
                ),
                "event_types": sorted(
                    {
                        str(item.get("event_type", "")).strip()
                        for item in events
                        if str(item.get("event_type", "")).strip()
                    }
                ),
            },
        }

    def list_login_events(
        self,
        *,
        sapid: str | None = None,
        role: str | None = None,
        success: bool | None = None,
        search: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        offset: int = 0,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Backward-compatible helper for login-only views."""
        return self.list_events(
            event_type="login",
            sapid=sapid,
            role=role,
            success=success,
            search=search,
            start_date=start_date,
            end_date=end_date,
            offset=offset,
            limit=limit,
        )

    def get_total_event_count(self) -> int:
        """Return total persisted audit event count."""
        return len(self._load_events())

    def trim_events(self, *, keep_latest: int) -> dict[str, int]:
        """Trim persisted audit events to latest N rows and return before/after counts."""
        safe_keep_latest = max(0, int(keep_latest))
        with self._lock:
            events = self._load_events()
            before_count = len(events)
            if safe_keep_latest == 0:
                trimmed_events: list[dict[str, Any]] = []
            elif before_count > safe_keep_latest:
                trimmed_events = events[-safe_keep_latest:]
            else:
                trimmed_events = events

            self._save_events(trimmed_events)
            after_count = len(trimmed_events)

        return {
            "before_count": before_count,
            "after_count": after_count,
            "removed": max(0, before_count - after_count),
        }

    def trim_events_before(self, *, cutoff_utc: datetime) -> dict[str, int]:
        """Trim persisted audit events older than the UTC cutoff timestamp."""
        if cutoff_utc.tzinfo is None:
            cutoff_utc = cutoff_utc.replace(tzinfo=timezone.utc)
        else:
            cutoff_utc = cutoff_utc.astimezone(timezone.utc)

        with self._lock:
            events = self._load_events()
            before_count = len(events)
            kept_events: list[dict[str, Any]] = []

            for event in events:
                event_dt = self._parse_datetime(str(event.get("timestamp", "")))
                # Keep unparseable timestamps to avoid accidental data loss.
                if event_dt is None:
                    kept_events.append(event)
                    continue

                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=timezone.utc)
                else:
                    event_dt = event_dt.astimezone(timezone.utc)

                if event_dt >= cutoff_utc:
                    kept_events.append(event)

            self._save_events(kept_events)
            after_count = len(kept_events)

        return {
            "before_count": before_count,
            "after_count": after_count,
            "removed": max(0, before_count - after_count),
        }
