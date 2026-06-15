from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Sequence, Set

from app.utils.json_handler import save_json_atomic, load_json_safe

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
MESSAGES_FILE = PROJECT_ROOT / "data" / "dashboard_messages.json"

ALLOWED_SEVERITIES = {"critical", "high", "low", "warning", "info", "compliance"}
ALLOWED_SCOPES = {"all", "team", "scrum", "employee"}
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}|\{\s*([^{}]+?)\s*\}")

BASE_PLACEHOLDER_CATEGORIES: List[Dict[str, Any]] = [
    {
        "id": "employee",
        "label": "Employee",
        "description": "Identity and role-related values from Resources.csv",
        "placeholders": [
            "employee_name",
            "name",
            "sapid",
            "employee_id",
            "primary_role",
            "secondary_role",
        ],
    },
    {
        "id": "org",
        "label": "Org",
        "description": "Team and reporting structure values",
        "placeholders": [
            "team_name",
            "team",
            "scrum_name",
            "scrum",
            "manager_name",
            "manager_sapid",
        ],
    },
    {
        "id": "contacts",
        "label": "Contacts",
        "description": "Usernames and contact fields",
        "placeholders": [
            "email",
            "jira_name",
            "github_name",
        ],
    },
    {
        "id": "kpi",
        "label": "KPI",
        "description": "Derived values from current KPI context",
        "placeholders": [
            "red_kpi_count",
            "red_kpi_list",
        ],
    },
    {
        "id": "time",
        "label": "Time",
        "description": "Current rendering time values",
        "placeholders": [
            "current_date",
            "current_datetime",
        ],
    },
]


def _normalize_severity(value: Any) -> str:
    raw = str(value or "").strip().lower()
    legacy_map = {
        "error": "critical",
        "success": "low",
    }
    return legacy_map.get(raw, raw or "info")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value: str) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_list(values: Optional[Sequence[str]]) -> List[str]:
    if not values:
        return []
    normalized: List[str] = []
    for value in values:
        item = str(value or "").strip()
        if item:
            normalized.append(item)
    return normalized


def _normalize_kpi_ids(values: Optional[Sequence[str]]) -> List[str]:
    normalized: List[str] = []
    for value in _normalize_list(values):
        token = value.strip().lower()
        if token and token.startswith("k"):
            normalized.append(token)
    return sorted(set(normalized))


def _normalize_placeholder_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "", re.sub(r"[\s\-]+", "_", str(value or "").strip().lower()))


def _build_placeholder_context(employee_profile: Dict[str, Any], red_kpis: Set[str]) -> Dict[str, str]:
    now = _now_utc()
    employee_name = str(employee_profile.get("Name", "")).strip()
    team_name = str(employee_profile.get("Team", "")).strip()
    scrum_name = str(employee_profile.get("Scrum", "")).strip()
    sapid = str(employee_profile.get("SAPID", "")).strip()
    primary_role = str(employee_profile.get("Primary Role", "")).strip()
    secondary_role = str(employee_profile.get("Secondary Role", "")).strip()
    manager_name = str(employee_profile.get("Manager Name", "")).strip()
    manager_sapid = str(employee_profile.get("Manager", "")).strip()
    email = str(employee_profile.get("Email", "")).strip()
    jira_name = str(employee_profile.get("JIRA Name", "")).strip()
    github_name = str(employee_profile.get("GitHub Name", "")).strip()

    context = {
        "employee_name": employee_name,
        "name": employee_name,
        "team_name": team_name,
        "team": team_name,
        "scrum_name": scrum_name,
        "scrum": scrum_name,
        "sapid": sapid,
        "employee_id": sapid,
        "primary_role": primary_role,
        "secondary_role": secondary_role,
        "manager_name": manager_name,
        "manager_sapid": manager_sapid,
        "email": email,
        "jira_name": jira_name,
        "github_name": github_name,
        "red_kpi_count": str(len(red_kpis)),
        "red_kpi_list": ", ".join(sorted(red_kpis)),
        "current_date": now.date().isoformat(),
        "current_datetime": _to_iso(now),
    }

    # Add normalized resource keys to support generic field placeholders.
    for key, value in employee_profile.items():
        normalized_key = _normalize_placeholder_key(str(key or ""))
        if not normalized_key:
            continue
        value_str = str(value or "").strip()
        context.setdefault(normalized_key, value_str)
        context[f"resource_{normalized_key}"] = value_str

    return {k: str(v or "") for k, v in context.items()}


def render_message_template(template_text: str, context: Dict[str, str]) -> str:
    raw_text = str(template_text or "")

    def _replace(match: re.Match[str]) -> str:
        raw_key = match.group(1) or match.group(2) or ""
        normalized_key = _normalize_placeholder_key(raw_key)
        return context.get(normalized_key, match.group(0))

    return PLACEHOLDER_PATTERN.sub(_replace, raw_text)


def _resource_field_placeholders(resource_fields: Optional[Sequence[str]] = None) -> List[str]:
    if not resource_fields:
        return []
    placeholders: List[str] = []
    for field in resource_fields:
        normalized = _normalize_placeholder_key(field)
        if normalized:
            placeholders.append(f"resource_{normalized}")
    return sorted(set(placeholders))


def get_placeholder_categories(resource_fields: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    categories = [
        {
            "id": str(category.get("id", "")),
            "label": str(category.get("label", "")),
            "description": str(category.get("description", "")),
            "type": "placeholder",
            "placeholders": [str(item) for item in category.get("placeholders", []) if str(item).strip()],
        }
        for category in BASE_PLACEHOLDER_CATEGORIES
    ]

    resource_placeholders = _resource_field_placeholders(resource_fields)
    if resource_placeholders:
        categories.append(
            {
                "id": "resource_fields",
                "label": "Resources.csv Fields",
                "description": "Normalized placeholders for any Resources.csv column",
                "type": "placeholder",
                "placeholders": resource_placeholders,
            }
        )

    if resource_fields:
        categories.append(
            {
                "id": "empty_resource_checks",
                "label": "Empty Resource Checks",
                "description": "Copy field names for Empty Resource Field Condition",
                "type": "resource_field",
                "placeholders": [str(item).strip() for item in resource_fields if str(item).strip()],
            }
        )

    return categories


def get_supported_placeholders(resource_fields: Optional[Sequence[str]] = None) -> List[str]:
    placeholders: List[str] = []
    for category in get_placeholder_categories(resource_fields):
        if str(category.get("type", "placeholder")) != "placeholder":
            continue
        placeholders.extend([str(value) for value in category.get("placeholders", [])])
    return sorted(set(placeholders))


def _normalize_resource_field_names(values: Optional[Sequence[str]]) -> List[str]:
    normalized: List[str] = []
    for value in _normalize_list(values):
        token = _normalize_placeholder_key(value)
        if token:
            normalized.append(token)
    return sorted(set(normalized))


def _default_payload() -> Dict[str, Any]:
    return {"messages": []}


def ensure_messages_file() -> None:
    if MESSAGES_FILE.exists():
        return
    save_json_atomic(str(MESSAGES_FILE), _default_payload())


def load_messages() -> List[Dict[str, Any]]:
    ensure_messages_file()
    payload = load_json_safe(str(MESSAGES_FILE), default=_default_payload())
    messages = payload.get("messages", []) if isinstance(payload, dict) else []
    return messages if isinstance(messages, list) else []


def save_messages(messages: List[Dict[str, Any]]) -> None:
    save_json_atomic(str(MESSAGES_FILE), {"messages": messages})


def _expires_at(message: Dict[str, Any]) -> Optional[datetime]:
    created_at = _parse_iso(str(message.get("created_at", "")))
    validity_days = int(message.get("validity_days", 0) or 0)
    if not created_at or validity_days <= 0:
        return None
    return created_at + timedelta(days=validity_days)


def _is_effectively_active(message: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    if not bool(message.get("enabled", True)):
        return False
    current = now or _now_utc()
    expiry = _expires_at(message)
    # validity_days=0 means indefinite validity (no expiry)
    if expiry is None:
        return True
    return current <= expiry


def serialize_message_for_admin(message: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    current = now or _now_utc()
    expiry = _expires_at(message)
    result = dict(message)
    result["severity"] = _normalize_severity(result.get("severity", "info"))
    result["scope"] = str(result.get("scope", "all")).lower()
    result["target_values"] = _normalize_list(result.get("target_values"))
    result["require_any_red_kpi"] = bool(result.get("require_any_red_kpi", False))
    result["kpi_red_ids"] = _normalize_kpi_ids(result.get("kpi_red_ids"))
    result["empty_resource_fields"] = _normalize_resource_field_names(result.get("empty_resource_fields"))
    result["empty_resource_field_sentinels"] = _normalize_list(result.get("empty_resource_field_sentinels"))
    result["validity_days"] = int(result.get("validity_days", 0) or 0)
    result["is_active"] = _is_effectively_active(result, current)
    result["expires_at"] = _to_iso(expiry) if expiry else None
    return result


def normalize_message_payload(payload: Dict[str, Any], existing_id: Optional[str] = None) -> Dict[str, Any]:
    text = str(payload.get("text", "")).strip()
    if not text:
        raise ValueError("Message text is required")

    severity = _normalize_severity(payload.get("severity", "info"))
    if severity not in ALLOWED_SEVERITIES:
        raise ValueError(f"Invalid severity: {severity}")

    scope = str(payload.get("scope", "all")).strip().lower()
    if scope not in ALLOWED_SCOPES:
        raise ValueError(f"Invalid scope: {scope}")

    target_values = _normalize_list(payload.get("target_values"))
    if scope != "all" and not target_values:
        raise ValueError("At least one target value is required for team/scrum/employee scope")

    validity_days = int(payload.get("validity_days", 0) or 0)
    if validity_days < 0:
        raise ValueError("Validity days cannot be negative")

    now_iso = _to_iso(_now_utc())
    message_id = existing_id or str(payload.get("id", "")).strip() or f"msg_{int(_now_utc().timestamp() * 1000)}"

    message: Dict[str, Any] = {
        "id": message_id,
        "text": text,
        "severity": severity,
        "scope": scope,
        "target_values": target_values,
        "require_any_red_kpi": bool(payload.get("require_any_red_kpi", False)),
        "kpi_red_ids": _normalize_kpi_ids(payload.get("kpi_red_ids")),
        "empty_resource_fields": _normalize_resource_field_names(payload.get("empty_resource_fields")),
        "empty_resource_field_sentinels": _normalize_list(payload.get("empty_resource_field_sentinels")),
        "validity_days": validity_days,
        "enabled": bool(payload.get("enabled", True)),
        "created_at": str(payload.get("created_at") or now_iso),
        "updated_at": now_iso,
    }
    return message


def _message_matches_scope(message: Dict[str, Any], employee_profile: Dict[str, Any]) -> bool:
    scope = str(message.get("scope", "all")).lower()
    targets = {str(value).strip().lower() for value in _normalize_list(message.get("target_values"))}

    if scope == "all":
        return True

    if scope == "team":
        team = str(employee_profile.get("Team", "")).strip().lower()
        return bool(team and team in targets)

    if scope == "scrum":
        scrum = str(employee_profile.get("Scrum", "")).strip().lower()
        return bool(scrum and scrum in targets)

    if scope == "employee":
        sapid = str(employee_profile.get("SAPID", "")).strip().lower()
        name = str(employee_profile.get("Name", "")).strip().lower()
        return bool((sapid and sapid in targets) or (name and name in targets))

    return False


def _message_matches_kpi_condition(message: Dict[str, Any], red_kpis: Set[str]) -> bool:
    if bool(message.get("require_any_red_kpi", False)):
        return len(red_kpis) > 0

    required = set(_normalize_kpi_ids(message.get("kpi_red_ids")))
    if not required:
        return True
    return len(required.intersection(red_kpis)) > 0


# Built-in sentinel values that are treated as "empty" for resource-field condition matching.
# These are well-known placeholder strings used throughout the system.
_BUILTIN_EMPTY_SENTINELS: frozenset = frozenset({
    "", "nan", "none", "null", "na", "n/a", "not_mapped", "-na-", "-", "na/",
})


def _message_matches_empty_resource_fields(message: Dict[str, Any], employee_profile: Dict[str, Any]) -> bool:
    required_empty_fields = _normalize_resource_field_names(message.get("empty_resource_fields"))
    if not required_empty_fields:
        return True

    # Custom per-rule sentinels (in addition to the built-ins)
    rule_sentinels = {
        str(s).strip().lower()
        for s in _normalize_list(message.get("empty_resource_field_sentinels"))
        if str(s).strip()
    }
    effective_sentinels = _BUILTIN_EMPTY_SENTINELS | rule_sentinels

    profile_map: Dict[str, str] = {}
    for key, value in employee_profile.items():
        normalized = _normalize_placeholder_key(str(key or ""))
        if normalized:
            profile_map[normalized] = str(value or "").strip()

    def _is_empty(value: str) -> bool:
        return value.strip().lower() in effective_sentinels

    return any(_is_empty(profile_map.get(field, "")) for field in required_empty_fields)


def get_applicable_messages(employee_profile: Dict[str, Any], red_kpi_ids: Sequence[str]) -> List[Dict[str, Any]]:
    red_kpis = {str(value or "").strip().lower() for value in red_kpi_ids if str(value or "").strip()}
    now = _now_utc()
    placeholder_context = _build_placeholder_context(employee_profile, red_kpis)
    results: List[Dict[str, Any]] = []

    for raw in load_messages():
        message = serialize_message_for_admin(raw, now)
        if not message.get("is_active"):
            continue
        if not _message_matches_scope(message, employee_profile):
            continue
        if not _message_matches_kpi_condition(message, red_kpis):
            continue
        if not _message_matches_empty_resource_fields(message, employee_profile):
            continue

        results.append(
            {
                "id": message.get("id"),
                "text": render_message_template(str(message.get("text", "")), placeholder_context),
                "severity": message.get("severity"),
                "scope": message.get("scope"),
                "target_values": message.get("target_values", []),
                "require_any_red_kpi": bool(message.get("require_any_red_kpi", False)),
                "kpi_red_ids": message.get("kpi_red_ids", []),
                "empty_resource_fields": message.get("empty_resource_fields", []),
                "empty_resource_field_sentinels": message.get("empty_resource_field_sentinels", []),
                "validity_days": message.get("validity_days"),
                "expires_at": message.get("expires_at"),
            }
        )

    severity_rank = {"critical": 0, "high": 1, "warning": 2, "compliance": 3, "info": 4, "low": 5}
    results.sort(key=lambda item: (severity_rank.get(str(item.get("severity", "info")), 9), str(item.get("id", ""))))
    return results
