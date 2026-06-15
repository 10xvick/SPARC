"""
UDE (Unified Development Environment) Installation Data API.

Receives installation event records from an external UDE registry system and
provides query endpoints to inspect stored data.

Storage:
  output/ude_installations.json       — full event log, keyed by install_event_id
  output/ude_installations_latest.json — derived: latest 'installed' event per (sapid, device_id)
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.dependencies import get_current_user
from app.models.user import TokenData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.absolute()
_UDE_LOG_FILE = _PROJECT_ROOT / "output" / "ude_installations.json"
_UDE_LATEST_FILE = _PROJECT_ROOT / "output" / "ude_installations_latest.json"

# Thread lock so concurrent requests don't corrupt JSON writes
_write_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Router — accessible to any authenticated user; writes require API User / Admin
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/api/ude", tags=["ude-installations"])


# ---------------------------------------------------------------------------
# Enums & Pydantic models
# ---------------------------------------------------------------------------

class InstallStatus(str, Enum):
    installed = "installed"
    superseded = "superseded"
    uninstalled = "uninstalled"
    failed = "failed"


class InstallationRecord(BaseModel):
    """A single installation event on a single device for a single employee."""

    install_event_id: str = Field(
        ...,
        description="Unique ID for this installation event. Primary deduplication key.",
    )
    ude_id: str = Field(..., description="Employee UDE licence / seat identifier.")
    sapid: str = Field(..., description="Employee SAPID — must match Resources.csv.")
    employee_name: Optional[str] = Field(
        None, description="Advisory display name from source system."
    )
    device_id: str = Field(
        ..., description="Stable unique identifier for the physical machine."
    )
    device_label: Optional[str] = Field(
        None, description="Human-readable device name, e.g. 'Primary Laptop'."
    )
    version: str = Field(..., description="UDE version string installed in this event.")
    release_name: Optional[str] = Field(None, description="Human-readable release label.")
    release_date: str = Field(..., description="Release publish date (YYYY-MM-DD).")
    installed_date: str = Field(
        ..., description="Timestamp of this install event (ISO 8601 or YYYY-MM-DD)."
    )
    status: InstallStatus = Field(InstallStatus.installed, description="Installation status.")

    @field_validator("install_event_id", "ude_id", "device_id", "version")
    @classmethod
    def required_string_fields_must_not_be_blank(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("field must be a non-empty string")
        return v.strip()

    @field_validator("sapid")
    @classmethod
    def sapid_must_be_numeric(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped.isdigit():
            raise ValueError("sapid must be a numeric string with no spaces or dots")
        return stripped

    @field_validator("installed_date")
    @classmethod
    def validate_installed_date(cls, v: str) -> str:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                datetime.strptime(v.split("+")[0].split("Z")[0].strip(), fmt)
                return v
            except ValueError:
                continue
        raise ValueError(
            "installed_date must be ISO 8601 or YYYY-MM-DD format, "
            f"got: {v!r}"
        )

    @field_validator("release_date")
    @classmethod
    def validate_release_date(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("release_date is required and must be YYYY-MM-DD")
        try:
            cleaned = v.strip()
            datetime.strptime(cleaned, "%Y-%m-%d")
            return cleaned
        except ValueError:
            raise ValueError(f"release_date must be YYYY-MM-DD, got: {v!r}")


class IngestRequest(BaseModel):
    """Top-level request body for the batch ingest endpoint."""

    report_date: str = Field(
        ..., description="Snapshot date this data was generated (YYYY-MM-DD)."
    )
    source_system: Optional[str] = Field(
        None, description="Identifier of the calling system."
    )
    installations: List[InstallationRecord] = Field(
        ..., description="List of installation event records. Max 5,000 per call."
    )

    @field_validator("report_date")
    @classmethod
    def validate_report_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError(f"report_date must be YYYY-MM-DD, got: {v!r}")

    @field_validator("installations")
    @classmethod
    def check_max_records(cls, v: list) -> list:
        if len(v) > 5000:
            raise ValueError("Maximum 5,000 installation records per request.")
        if len(v) == 0:
            raise ValueError("installations list must contain at least one record.")
        return v


class IngestError(BaseModel):
    install_event_id: Optional[str] = None
    sapid: Optional[str] = None
    reason: str


class IngestResponse(BaseModel):
    status: str
    received_at: str
    report_date: str
    total_records: int
    accepted: int
    skipped: int
    errors: List[IngestError]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_log() -> Dict[str, Any]:
    """Load the full installation event log from disk. Returns {} if missing."""
    if not _UDE_LOG_FILE.exists():
        return {}
    try:
        return json.loads(_UDE_LOG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed to read UDE log file: %s", exc)
        return {}


def _save_log(log: Dict[str, Any]) -> None:
    """Persist the event log to disk (caller must hold _write_lock)."""
    _UDE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _UDE_LOG_FILE.write_text(
        json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _rebuild_latest(log: Dict[str, Any]) -> None:
    """
    Derive the latest 'installed' event per (sapid, device_id) and write to
    ude_installations_latest.json. Called inside the write lock after each ingest.
    """
    latest: Dict[str, Any] = {}
    for record in log.values():
        if record.get("status") != InstallStatus.installed:
            continue
        key = f"{record['sapid']}::{record['device_id']}"
        existing = latest.get(key)
        if existing is None:
            latest[key] = record
        else:
            # Compare by installed_date string — ISO 8601 lexicographic order is valid
            if record.get("installed_date", "") > existing.get("installed_date", ""):
                latest[key] = record

    _UDE_LATEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    _UDE_LATEST_FILE.write_text(
        json.dumps(list(latest.values()), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_known_sapids() -> set:
    """Load the set of valid SAPIDs from Resources.csv for validation."""
    resources_path = _PROJECT_ROOT / "config" / "Resources.csv"
    if not resources_path.exists():
        return set()
    import csv
    sapids: set = set()
    try:
        with resources_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw = str(row.get("SAPID", "")).strip()
                if raw and raw not in ("", "nan"):
                    try:
                        sapids.add(str(int(float(raw))))
                    except ValueError:
                        pass
    except Exception as exc:
        logger.warning("Could not read Resources.csv for SAPID validation: %s", exc)
    return sapids


def _extract_payload_debug_meta(payload: Any) -> Dict[str, Any]:
    """Return safe, concise metadata for ingest payload logging."""
    if not isinstance(payload, dict):
        return {
            "payload_type": type(payload).__name__,
            "payload_keys": [],
            "installations_count": 0,
            "sample_event_ids": [],
        }

    installations = payload.get("installations")
    install_count = len(installations) if isinstance(installations, list) else 0
    sample_event_ids: list[str] = []
    if isinstance(installations, list):
        for row in installations[:5]:
            if isinstance(row, dict):
                event_id = str(row.get("install_event_id") or "").strip()
                if event_id:
                    sample_event_ids.append(event_id)

    return {
        "payload_type": "dict",
        "payload_keys": sorted(list(payload.keys()))[:20],
        "installations_count": install_count,
        "sample_event_ids": sample_event_ids,
    }


def _log_ingest_validation_failure(
    *,
    source: str,
    current_user: TokenData,
    payload: Any,
    validation_error: ValidationError,
    client_host: str,
) -> None:
    payload_meta = _extract_payload_debug_meta(payload)
    errors = validation_error.errors()
    logger.warning(
        "UDE ingest validation failed: source=%s user=%s role=%s client=%s errors=%s payload_meta=%s",
        source,
        current_user.sapid,
        current_user.role,
        client_host,
        errors,
        payload_meta,
    )


def _process_ingest(
    request: IngestRequest,
    *,
    source: str,
    current_user: TokenData,
    client_host: str,
    upload_filename: str = "",
) -> IngestResponse:
    """Core ingest logic — validate, upsert into log, rebuild latest."""
    logger.info(
        "UDE ingest received: source=%s user=%s role=%s client=%s report_date=%s source_system=%s records=%s upload_filename=%s",
        source,
        current_user.sapid,
        current_user.role,
        client_host,
        request.report_date,
        request.source_system or "",
        len(request.installations),
        upload_filename,
    )

    known_sapids = _load_known_sapids()
    errors: List[IngestError] = []
    accepted_ids: List[str] = []
    unknown_sapid_count = 0
    unknown_sapid_samples: list[dict[str, str]] = []

    # Validate each record before acquiring the write lock
    valid_records: List[Dict[str, Any]] = []
    for rec in request.installations:
        if known_sapids and rec.sapid not in known_sapids:
            errors.append(
                IngestError(
                    install_event_id=rec.install_event_id,
                    sapid=rec.sapid,
                    reason="SAPID not found in TeamSight resource directory",
                )
            )
            unknown_sapid_count += 1
            if len(unknown_sapid_samples) < 5:
                unknown_sapid_samples.append(
                    {
                        "install_event_id": rec.install_event_id,
                        "sapid": rec.sapid,
                    }
                )
            continue
        valid_records.append(rec.model_dump())

    received_at = datetime.now(timezone.utc).isoformat()
    created_count = 0
    updated_count = 0

    with _write_lock:
        log = _load_log()
        for record in valid_records:
            record["_ingested_at"] = received_at
            record["_report_date"] = request.report_date
            record["_source_system"] = request.source_system or ""
            if record["install_event_id"] in log:
                updated_count += 1
            else:
                created_count += 1
            log[record["install_event_id"]] = record
            accepted_ids.append(record["install_event_id"])
        _save_log(log)
        _rebuild_latest(log)

    skipped = len(request.installations) - len(accepted_ids)
    overall_status = "accepted" if not errors else "partial"

    if unknown_sapid_count > 0:
        logger.warning(
            "UDE ingest skipped unknown SAPIDs: source=%s user=%s role=%s client=%s count=%s samples=%s",
            source,
            current_user.sapid,
            current_user.role,
            client_host,
            unknown_sapid_count,
            unknown_sapid_samples,
        )

    logger.info(
        "UDE ingest completed: source=%s user=%s role=%s client=%s status=%s total=%s accepted=%s skipped=%s created=%s updated=%s",
        source,
        current_user.sapid,
        current_user.role,
        client_host,
        overall_status,
        len(request.installations),
        len(accepted_ids),
        skipped,
        created_count,
        updated_count,
    )

    return IngestResponse(
        status=overall_status,
        received_at=received_at,
        report_date=request.report_date,
        total_records=len(request.installations),
        accepted=len(accepted_ids),
        skipped=skipped,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Write endpoints  (require API User or Admin)
# ---------------------------------------------------------------------------

def _require_write_role(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    if current_user.role not in ("Admin", "API User"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or API User role required to push UDE installation data",
        )
    return current_user


@router.post(
    "/installations",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest UDE installation events (JSON body)",
)
def ingest_installations(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(_require_write_role),
) -> IngestResponse:
    """
    Accept a batch of UDE installation event records as a JSON body.

    - One record represents one installation act on one specific device.
    - Records are upserted by **install_event_id** — re-submitting the same ID updates the record.
    - A single call covering all employees (~300–600 records) is the recommended pattern.
    - Maximum 5,000 records per request.
    """
    client_host = request.client.host if request.client else "unknown"

    try:
        parsed_request = IngestRequest.model_validate(payload)
    except ValidationError as exc:
        _log_ingest_validation_failure(
            source="json",
            current_user=current_user,
            payload=payload,
            validation_error=exc,
            client_host=client_host,
        )
        raise HTTPException(status_code=422, detail=exc.errors())

    if not parsed_request.installations:
        raise HTTPException(status_code=400, detail="installations list is empty")

    return _process_ingest(
        parsed_request,
        source="json",
        current_user=current_user,
        client_host=client_host,
    )


@router.post(
    "/installations/upload",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest UDE installation events (file upload)",
)
async def upload_installations(
    request: Request,
    file: UploadFile = File(..., description="JSON file with same schema as POST /installations"),
    current_user: TokenData = Depends(_require_write_role),
) -> IngestResponse:
    """
    Accept a `.json` file containing the same payload schema as the batch ingest endpoint.
    Useful when the source system prefers file-based delivery over a JSON request body.
    """
    client_host = request.client.host if request.client else "unknown"

    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .json file")

    raw = await file.read()
    logger.info(
        "UDE ingest upload received: user=%s role=%s client=%s filename=%s bytes=%s",
        current_user.sapid,
        current_user.role,
        client_host,
        file.filename,
        len(raw),
    )

    if len(raw) > 10 * 1024 * 1024:  # 10 MB safety cap
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        logger.warning(
            "UDE ingest upload JSON decode failed: user=%s role=%s client=%s filename=%s",
            current_user.sapid,
            current_user.role,
            client_host,
            file.filename,
        )
        raise HTTPException(status_code=400, detail="File is not valid JSON")

    try:
        parsed_request = IngestRequest.model_validate(payload)
    except ValidationError as exc:
        _log_ingest_validation_failure(
            source="upload",
            current_user=current_user,
            payload=payload,
            validation_error=exc,
            client_host=client_host,
        )
        raise HTTPException(status_code=422, detail=exc.errors())

    return _process_ingest(
        parsed_request,
        source="upload",
        current_user=current_user,
        client_host=client_host,
        upload_filename=file.filename,
    )


# ---------------------------------------------------------------------------
# Read endpoints  (any authenticated user)
# ---------------------------------------------------------------------------

# Path to the backend log file written by manage.sh
_BACKEND_LOG_FILE = _PROJECT_ROOT / "dashboard" / "logs" / "backend.log"

# Markers used to locate UDE ingest boundaries inside the log
_UDE_INGEST_RECEIVED_RE = re.compile(r"UDE ingest received:")
_UDE_INGEST_COMPLETED_RE = re.compile(r"UDE ingest completed:")
_UDE_INGEST_LINE_RE = re.compile(r"app\.api\.ude")


def _read_last_ingest_log_lines(max_scan_lines: int = 50_000) -> Dict[str, Any]:
    """
    Scan backend.log from the bottom, find the last 'UDE ingest received' entry,
    and collect every UDE-related log line from that point until (and including)
    the matching 'UDE ingest completed' line (or end of file).

    Returns a dict with:
      - session_lines: the matched log lines for the last ingest call
      - started_at:    timestamp from the 'received' line (or None)
      - completed_at:  timestamp from the 'completed' line (or None)
      - log_file:      path that was scanned
      - scanned_lines: how many tail lines were examined
    """
    if not _BACKEND_LOG_FILE.exists():
        return {
            "session_lines": [],
            "started_at": None,
            "completed_at": None,
            "log_file": str(_BACKEND_LOG_FILE),
            "scanned_lines": 0,
            "error": "Log file not found",
        }

    try:
        with _BACKEND_LOG_FILE.open("r", encoding="utf-8", errors="replace") as fh:
            all_lines = fh.readlines()
    except Exception as exc:
        return {
            "session_lines": [],
            "started_at": None,
            "completed_at": None,
            "log_file": str(_BACKEND_LOG_FILE),
            "scanned_lines": 0,
            "error": f"Failed to read log file: {exc}",
        }

    # Work with a tail slice to bound memory / time
    tail = all_lines[-max_scan_lines:] if len(all_lines) > max_scan_lines else all_lines
    scanned = len(tail)

    # Walk backwards to find the last 'UDE ingest received' line
    received_idx: Optional[int] = None
    for i in range(len(tail) - 1, -1, -1):
        if _UDE_INGEST_RECEIVED_RE.search(tail[i]):
            received_idx = i
            break

    if received_idx is None:
        return {
            "session_lines": [],
            "started_at": None,
            "completed_at": None,
            "log_file": str(_BACKEND_LOG_FILE),
            "scanned_lines": scanned,
            "error": "No UDE ingest call found in the scanned log tail",
        }

    # Collect from received_idx onward, keeping lines that come from app.api.ude
    # Stop after the first 'UDE ingest completed' line following the received marker
    session: List[str] = []
    completed_at: Optional[str] = None
    started_at: Optional[str] = None
    found_completed = False

    for i in range(received_idx, len(tail)):
        line = tail[i].rstrip("\n")
        if not _UDE_INGEST_LINE_RE.search(line):
            continue
        session.append(line)
        # Extract timestamps from the first and last meaningful lines
        # Log format: 2026-05-05 12:34:56,789 - app.api.ude - INFO - ...
        ts_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)', line)
        ts = ts_match.group(1) if ts_match else None
        if started_at is None and ts:
            started_at = ts
        if ts:
            # update completed_at with each line's timestamp
            completed_at = ts
        if _UDE_INGEST_COMPLETED_RE.search(line):
            found_completed = True
            break

    return {
        "session_lines": session,
        "started_at": started_at,
        "completed_at": completed_at if found_completed else None,
        "still_running": not found_completed,
        "log_file": str(_BACKEND_LOG_FILE),
        "scanned_lines": scanned,
    }


def _all_records() -> List[Dict[str, Any]]:
    log = _load_log()
    return list(log.values())


def _apply_filters(
    records: List[Dict[str, Any]],
    *,
    sapid: Optional[str],
    device_id: Optional[str],
    version: Optional[str],
    release_name: Optional[str],
    status_filter: Optional[str],
) -> List[Dict[str, Any]]:
    if sapid:
        records = [r for r in records if r.get("sapid") == sapid]
    if device_id:
        records = [r for r in records if r.get("device_id") == device_id]
    if version:
        records = [r for r in records if r.get("version") == version]
    if release_name:
        records = [r for r in records if r.get("release_name") == release_name]
    if status_filter:
        records = [r for r in records if r.get("status") == status_filter]
    return records


@router.get(
    "/installations/ingest-logs",
    summary="Return log lines for the last UDE ingest API call",
)
def get_last_ingest_logs(
    _: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Scans `dashboard/logs/backend.log` for the most recent UDE ingest request
    and returns all associated log lines (received → completed).

    Useful for debugging why a payload was rejected or partially accepted:
    validation errors, unknown SAPIDs, and ingest outcome counters are all
    captured here.
    """
    return _read_last_ingest_log_lines()


@router.get(
    "/installations",
    summary="Query installation records",
)
def get_installations(
    sapid: Optional[str] = Query(None, description="Filter by employee SAPID"),
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    version: Optional[str] = Query(None, description="Filter by UDE version string"),
    release_name: Optional[str] = Query(None, description="Filter by release name"),
    status: Optional[str] = Query(None, description="Filter by status: installed | superseded | uninstalled | failed"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=1000, description="Records per page"),
    _: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Query all stored installation records with optional filters.
    Results are paginated; use `page` and `page_size` to navigate.
    """
    records = _all_records()
    records = _apply_filters(
        records,
        sapid=sapid,
        device_id=device_id,
        version=version,
        release_name=release_name,
        status_filter=status,
    )

    # Sort by installed_date descending
    records.sort(key=lambda r: r.get("installed_date", ""), reverse=True)

    total = len(records)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "data": records[start:end],
    }


@router.get(
    "/installations/summary",
    summary="Latest installed version per employee per device",
)
def get_installations_summary(
    sapid: Optional[str] = Query(None, description="Filter by employee SAPID"),
    _: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns the latest `installed` event for each `(sapid, device_id)` combination.
    Optionally filter to a single employee with `sapid`.
    """
    if not _UDE_LATEST_FILE.exists():
        return {"total": 0, "data": []}

    try:
        records: List[Dict[str, Any]] = json.loads(
            _UDE_LATEST_FILE.read_text(encoding="utf-8")
        )
    except Exception as exc:
        logger.error("Failed to read UDE latest file: %s", exc)
        return {"total": 0, "data": []}

    if sapid:
        records = [r for r in records if r.get("sapid") == sapid]

    records.sort(key=lambda r: (r.get("sapid", ""), r.get("device_id", "")))
    return {"total": len(records), "data": records}


@router.get(
    "/installations/{install_event_id}",
    summary="Get a single installation record by event ID",
)
def get_installation_by_id(
    install_event_id: str,
    _: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Retrieve the stored record for a specific `install_event_id`.
    Returns 404 if not found.
    """
    log = _load_log()
    record = log.get(install_event_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No installation record found for install_event_id: {install_event_id!r}",
        )
    return record
