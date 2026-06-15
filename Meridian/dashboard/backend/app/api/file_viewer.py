"""File Viewer API — list and read KPI output files, scan reports, and logs."""
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import FileResponse
from typing import List, Dict, Any
import re
import sys
import json
import pandas as pd
from pathlib import Path

from app.dependencies import require_admin, require_admin_or_read_api

# Import KppEvaluator to access equivalence map
_PROJECT_ROOT_FOR_SRC = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT_FOR_SRC / 'src'))
try:
    from KppEvaluator import KppEvaluator as _KppEvaluator
    # Lazily instantiate once to access the equivalents dict
    _evaluator_instance = None
    def _get_kpi_equivalents() -> Dict[str, str]:
        global _evaluator_instance
        if _evaluator_instance is None:
            try:
                _evaluator_instance = _KppEvaluator(
                    resources_file=str(_PROJECT_ROOT_FOR_SRC / 'config' / 'Resources.csv'),
                    jira_issues_file=str(_PROJECT_ROOT_FOR_SRC / 'output' / 'JIRAIssues.csv'),
                    github_commits_file=str(_PROJECT_ROOT_FOR_SRC / 'output' / 'github_commits.csv'),
                    output_dir=str(_PROJECT_ROOT_FOR_SRC / 'output'),
                )
            except Exception:
                return {}
        return _evaluator_instance.kpi_equivalents
except ImportError:
    def _get_kpi_equivalents() -> Dict[str, str]:
        return {}

router = APIRouter(
    prefix="/api/file-viewer",
    tags=["file-viewer"],
    dependencies=[Depends(require_admin_or_read_api)],
)

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
_OUTPUT_DIR = _PROJECT_ROOT / "output"
_SCANS_DIR = _OUTPUT_DIR / "scans"
_SNAPSHOTS_DIR = _OUTPUT_DIR / "dashboard_snapshots"
_LOGS_DIR = _PROJECT_ROOT / "dashboard" / "logs"

_KPI_FILE_RE = re.compile(r'^k\d+-data\.csv$')
_SCAN_TYPE_RE = re.compile(r'^[a-zA-Z0-9_]+$')
_LOG_FILE_RE = re.compile(r'^[\w\-]+\.log$')
_SNAPSHOT_ID_RE = re.compile(r'^[A-Za-z0-9_\-]+$')
_SNAPSHOT_FILE_RE = re.compile(r'^[A-Za-z0-9_\-]+\.json$')


def _safe_child(base: Path, filename: str) -> Path:
    """Resolve *filename* inside *base*, raising 400 on path-traversal attempts."""
    try:
        resolved = (base / filename).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not str(resolved).startswith(str(base.resolve()) + "/") and resolved != base.resolve():
        raise HTTPException(status_code=400, detail="Invalid file path")
    return resolved


# ---------------------------------------------------------------------------
# KPI section
# ---------------------------------------------------------------------------

@router.get("/kpi-files", response_model=List[str])
def list_kpi_files():
    """Return sorted list of k*-data.csv file names from the output directory."""
    return sorted(f.name for f in _OUTPUT_DIR.glob("k*-data.csv") if _KPI_FILE_RE.match(f.name))


@router.get("/kpi-equivalents", response_model=Dict[str, str])
def get_kpi_equivalents():
    """
    Return the KPI equivalence map: {alias_kpi: base_kpi}.
    Equivalent KPIs share computation and data with their base KPI.
    """
    return _get_kpi_equivalents()


@router.get("/kpi-data")
def get_kpi_data(
    file: str = Query(..., description="KPI CSV file name, e.g. k1-data.csv"),
    limit: int = Query(50, ge=10, le=500, description="Rows per page"),
    offset: int = Query(0, ge=0, description="Row offset from the start"),
):
    """Return a paginated slice of a KPI output CSV as JSON."""
    if not _KPI_FILE_RE.match(file):
        raise HTTPException(status_code=400, detail="Invalid KPI file name")
    path = _safe_child(_OUTPUT_DIR, file)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file}")
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read CSV: {exc}")
    total = len(df)
    # offset=0 with default means "last page" (newest rows)
    if offset == 0 and limit <= total:
        slice_df = df.iloc[total - limit:]
        actual_offset = total - limit
    else:
        slice_df = df.iloc[offset: offset + limit]
        actual_offset = offset
    # Convert to native Python types; replace float NaN with None so
    # Starlette's JSONResponse (allow_nan=False) can serialize the result.
    raw_rows = slice_df.values.tolist()
    rows = [
        [None if (isinstance(v, float) and v != v) else v for v in row]
        for row in raw_rows
    ]
    return {
        "columns": list(slice_df.columns),
        "rows": rows,
        "total_rows": total,
        "offset": actual_offset,
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# Dashboard snapshots section
# ---------------------------------------------------------------------------

@router.get("/snapshot-folders")
def list_snapshot_folders():
    """Return available dashboard snapshot folders and active pointer."""
    if not _SNAPSHOTS_DIR.exists():
        return {"active_snapshot": None, "folders": []}

    active_snapshot = None
    active_path = _SNAPSHOTS_DIR / "ACTIVE.json"
    if active_path.exists():
        try:
            active_df = pd.read_json(active_path, typ="series")
            active_snapshot = str(active_df.get("snapshot_id", "")).strip() or None
        except Exception:
            active_snapshot = None

    folders = sorted(
        [d.name for d in _SNAPSHOTS_DIR.iterdir() if d.is_dir()],
        reverse=True,
    )
    return {"active_snapshot": active_snapshot, "folders": folders}


@router.get("/snapshot-files", response_model=List[str])
def list_snapshot_files(
    snapshot_id: str = Query(..., description="Snapshot folder id, e.g. 20260421_112233"),
):
    """Return JSON files under a dashboard snapshot folder."""
    if not _SNAPSHOT_ID_RE.match(snapshot_id):
        raise HTTPException(status_code=400, detail="Invalid snapshot id")

    snapshot_dir = _safe_child(_SNAPSHOTS_DIR, snapshot_id)
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Snapshot folder not found: {snapshot_id}")

    return sorted([f.name for f in snapshot_dir.glob("*.json") if _SNAPSHOT_FILE_RE.match(f.name)])


@router.get("/snapshot-file")
def get_snapshot_file(
    snapshot_id: str = Query(..., description="Snapshot folder id"),
    file: str = Query(..., description="Snapshot JSON file, e.g. team_Annual.json"),
    max_bytes: int = Query(250000, ge=10000, le=1000000, description="Maximum bytes returned"),
):
    """Return snapshot JSON content as text, truncated for large files."""
    if not _SNAPSHOT_ID_RE.match(snapshot_id):
        raise HTTPException(status_code=400, detail="Invalid snapshot id")
    if not _SNAPSHOT_FILE_RE.match(file):
        raise HTTPException(status_code=400, detail="Invalid snapshot file name")

    snapshot_dir = _safe_child(_SNAPSHOTS_DIR, snapshot_id)
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Snapshot folder not found: {snapshot_id}")

    path = _safe_child(snapshot_dir, file)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Snapshot file not found: {file}")

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read snapshot file: {exc}")

    total_bytes = len(raw.encode("utf-8", errors="replace"))
    content = raw
    truncated = False
    if total_bytes > max_bytes:
        content = raw[:max_bytes]
        truncated = True

    return {
        "snapshot_id": snapshot_id,
        "file": file,
        "bytes": total_bytes,
        "truncated": truncated,
        "content": content,
    }


@router.get("/snapshot-file-download")
def download_snapshot_file(
    snapshot_id: str = Query(..., description="Snapshot folder id"),
    file: str = Query(..., description="Snapshot JSON file, e.g. team_Annual.json"),
):
    """Download the raw snapshot JSON file as an attachment."""
    if not _SNAPSHOT_ID_RE.match(snapshot_id):
        raise HTTPException(status_code=400, detail="Invalid snapshot id")
    if not _SNAPSHOT_FILE_RE.match(file):
        raise HTTPException(status_code=400, detail="Invalid snapshot file name")

    snapshot_dir = _safe_child(_SNAPSHOTS_DIR, snapshot_id)
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Snapshot folder not found: {snapshot_id}")

    path = _safe_child(snapshot_dir, file)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Snapshot file not found: {file}")

    return FileResponse(
        str(path),
        media_type="application/json",
        filename=file,
    )


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _summary_stats(values: List[float]) -> Dict[str, float | None]:
    if not values:
        return {"avg": None, "min": None, "max": None}
    return {
        "avg": round(sum(values) / len(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def _first_non_empty_string(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _extract_entity_fields(item: Dict[str, Any], key: str, scope: str) -> Dict[str, str]:
    """Derive lightweight entity metadata from existing payload nodes."""
    normalized_scope = str(scope or "").strip().lower()
    entity = normalized_scope if normalized_scope in ("team", "scrum", "employee") else "unknown"
    safe_key = _first_non_empty_string(key) or "unknown"
    display_name = safe_key

    if normalized_scope == "team":
        team_node = item.get("team")
        if isinstance(team_node, dict):
            display_name = (
                _first_non_empty_string(
                    team_node.get("name"),
                    team_node.get("Name"),
                    item.get("name"),
                    item.get("Name"),
                    safe_key,
                )
                or safe_key
            )
    elif normalized_scope == "scrum":
        scrum_node = item.get("scrum")
        if isinstance(scrum_node, dict):
            display_name = (
                _first_non_empty_string(
                    scrum_node.get("name"),
                    scrum_node.get("Name"),
                    item.get("name"),
                    item.get("Name"),
                    safe_key,
                )
                or safe_key
            )
    elif normalized_scope == "employee":
        employee_node = item.get("employee")
        if isinstance(employee_node, dict):
            display_name = (
                _first_non_empty_string(
                    employee_node.get("Name"),
                    employee_node.get("name"),
                    employee_node.get("SAPID"),
                    employee_node.get("sapid"),
                    item.get("name"),
                    item.get("Name"),
                    safe_key,
                )
                or safe_key
            )

    entity = _first_non_empty_string(entity) or "unknown"
    display_name = _first_non_empty_string(display_name, safe_key) or "unknown"

    return {
        "entity": entity,
        "display_name": display_name,
    }


@router.get("/snapshot-summary")
def get_snapshot_summary(
    snapshot_id: str = Query(..., description="Snapshot folder id"),
    file: str = Query(..., description="Snapshot JSON file, e.g. team_Annual.json"),
    sample_limit: int = Query(30, ge=5, le=100, description="Max sample entries to return"),
):
    """Return a structured summary for a snapshot JSON file.

    This reads and parses the full JSON server-side, so it works even when raw
    preview content is truncated in the UI.
    """
    if not _SNAPSHOT_ID_RE.match(snapshot_id):
        raise HTTPException(status_code=400, detail="Invalid snapshot id")
    if not _SNAPSHOT_FILE_RE.match(file):
        raise HTTPException(status_code=400, detail="Invalid snapshot file name")

    snapshot_dir = _safe_child(_SNAPSHOTS_DIR, snapshot_id)
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Snapshot folder not found: {snapshot_id}")

    path = _safe_child(snapshot_dir, file)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Snapshot file not found: {file}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse snapshot JSON: {exc}")

    if not isinstance(payload, dict):
        return {
            "snapshot_id": snapshot_id,
            "file": file,
            "scope": "unknown",
            "as_of_date": None,
            "period": None,
            "top_level_keys": [],
            "entry_count": 0,
            "status_counts": {"ok": 0, "inactive": 0, "failed": 0, "n_a": 0},
            "score_stats": {"avg": None, "min": None, "max": None},
            "kpi_count_stats": {"avg": None, "min": None, "max": None},
            "member_count_stats": {"avg": None, "min": None, "max": None},
            "red_kpi_stats": {"avg": None, "min": None, "max": None},
            "category_status_counts": {},
            "top_red_entities": [],
            "sample_rows": [],
            "note": "Snapshot payload is not a JSON object",
        }

    if file == "manifest.json":
        return {
            "snapshot_id": snapshot_id,
            "file": file,
            "scope": "manifest",
            "as_of_date": payload.get("as_of_date"),
            "period": None,
            "top_level_keys": list(payload.keys()),
            "entry_count": 0,
            "status_counts": {"ok": 0, "inactive": 0, "failed": 0, "n_a": 0},
            "score_stats": {"avg": None, "min": None, "max": None},
            "kpi_count_stats": {"avg": None, "min": None, "max": None},
            "member_count_stats": {"avg": None, "min": None, "max": None},
            "red_kpi_stats": {"avg": None, "min": None, "max": None},
            "category_status_counts": {},
            "top_red_entities": [],
            "sample_rows": [],
            "manifest": {
                "generated_at": payload.get("generated_at"),
                "source": payload.get("source"),
                "periods": payload.get("periods") if isinstance(payload.get("periods"), list) else [],
                "team_count": payload.get("team_count"),
                "scrum_count": payload.get("scrum_count"),
                "employee_count": payload.get("employee_count"),
            },
        }

    data_node = payload.get("data", {})
    if not isinstance(data_node, dict):
        data_node = {}

    scope = "unknown"
    if file.startswith("team_"):
        scope = "team"
    elif file.startswith("scrum_"):
        scope = "scrum"
    elif file.startswith("employee_"):
        scope = "employee"

    status_counts = {"ok": 0, "inactive": 0, "failed": 0, "n_a": 0}
    category_status_counts: Dict[str, Dict[str, int]] = {}
    score_values: List[float] = []
    total_kpi_values: List[float] = []
    member_count_values: List[float] = []
    red_kpi_values: List[float] = []
    top_red_entities: List[Dict[str, Any]] = []

    sample_rows = []
    for key in list(data_node.keys())[:sample_limit]:
        item = data_node.get(key, {})
        if not isinstance(item, dict):
            item = {}
        entity_fields = _extract_entity_fields(item, key, scope)

        member_or_kpi_count = (
            item.get("team", {}).get("member_count") if isinstance(item.get("team"), dict) else None
        )
        if member_or_kpi_count is None:
            member_or_kpi_count = (
                item.get("scrum", {}).get("member_count") if isinstance(item.get("scrum"), dict) else None
            )
        if member_or_kpi_count is None:
            member_or_kpi_count = item.get("total_kpis")

        if isinstance(item.get("success"), bool):
            status = "ok" if item.get("success") else "failed"
        elif item.get("inactive"):
            status = "inactive"
        else:
            status = "n/a"

        score_val = None
        score_node = item.get("score")
        if isinstance(score_node, dict):
            score_val = _to_float(score_node.get("overall_score"))

        red_kpi_count = 0
        kpi_items = item.get("kpi_performance")
        if isinstance(kpi_items, list):
            for kpi in kpi_items:
                if not isinstance(kpi, dict):
                    continue
                status_raw = str(kpi.get("Status") or kpi.get("rog_status") or "").strip().lower()
                if status_raw == "red":
                    red_kpi_count += 1

        sample_rows.append(
            {
                "key": key,
                "entity": entity_fields["entity"],
                "display_name": entity_fields["display_name"],
                "member_or_kpi_count": member_or_kpi_count,
                "status": status,
                "overall_score": score_val,
                "red_kpis": red_kpi_count,
            }
        )

    for key, raw_item in data_node.items():
        item = raw_item if isinstance(raw_item, dict) else {}
        entity_fields = _extract_entity_fields(item, key, scope)

        if isinstance(item.get("success"), bool):
            status = "ok" if item.get("success") else "failed"
        elif item.get("inactive"):
            status = "inactive"
        else:
            status = "n_a"
        status_counts[status] += 1

        total_kpis = _to_float(item.get("total_kpis"))
        if total_kpis is not None:
            total_kpi_values.append(total_kpis)

        score_node = item.get("score")
        overall_score = None
        if isinstance(score_node, dict):
            overall_score = _to_float(score_node.get("overall_score"))
            if overall_score is not None:
                score_values.append(overall_score)

        member_count = None
        team_node = item.get("team")
        scrum_node = item.get("scrum")
        if isinstance(team_node, dict):
            member_count = _to_float(team_node.get("member_count"))
        if member_count is None and isinstance(scrum_node, dict):
            member_count = _to_float(scrum_node.get("member_count"))
        if member_count is not None:
            member_count_values.append(member_count)

        red_kpi_count = 0
        kpi_items = item.get("kpi_performance")
        if isinstance(kpi_items, list):
            for kpi in kpi_items:
                if not isinstance(kpi, dict):
                    continue
                status_raw = str(kpi.get("Status") or kpi.get("rog_status") or "").strip().lower()
                if status_raw == "red":
                    red_kpi_count += 1
        red_kpi_values.append(float(red_kpi_count))

        if red_kpi_count > 0:
            top_red_entities.append(
                {
                    "key": key,
                    "entity": entity_fields["entity"],
                    "display_name": entity_fields["display_name"],
                    "red_kpis": red_kpi_count,
                    "total_kpis": int(total_kpis) if total_kpis is not None else None,
                    "overall_score": overall_score,
                }
            )

        category_status = item.get("category_status")
        if isinstance(category_status, dict):
            for cat_name, cat_data in category_status.items():
                if not isinstance(cat_data, dict):
                    continue
                cat_key = str(cat_name).strip().lower() or "unknown"
                bucket = category_status_counts.setdefault(
                    cat_key,
                    {"green": 0, "orange": 0, "red": 0, "n_a": 0},
                )
                raw_status = str(cat_data.get("status", "")).strip().lower()
                if raw_status in ("green", "orange", "red"):
                    bucket[raw_status] += 1
                else:
                    bucket["n_a"] += 1

    top_red_entities.sort(
        key=lambda x: (
            int(x.get("red_kpis") or 0),
            -float(x.get("overall_score") or 0.0),
        ),
        reverse=True,
    )

    return {
        "snapshot_id": snapshot_id,
        "file": file,
        "scope": scope,
        "as_of_date": payload.get("as_of_date"),
        "period": payload.get("period"),
        "top_level_keys": list(payload.keys()),
        "entry_count": len(data_node),
        "status_counts": status_counts,
        "score_stats": _summary_stats(score_values),
        "kpi_count_stats": _summary_stats(total_kpi_values),
        "member_count_stats": _summary_stats(member_count_values),
        "red_kpi_stats": _summary_stats(red_kpi_values),
        "category_status_counts": category_status_counts,
        "top_red_entities": top_red_entities[:10],
        "sample_rows": sample_rows,
    }


@router.get("/snapshot-file-formatted")
def get_snapshot_file_formatted(
    snapshot_id: str = Query(..., description="Snapshot folder id"),
    file: str = Query(..., description="Snapshot JSON file"),
    max_chars: int = Query(300000, ge=10000, le=2000000, description="Maximum formatted characters returned"),
):
    """Return pretty-printed snapshot JSON content for human-readable viewing."""
    if not _SNAPSHOT_ID_RE.match(snapshot_id):
        raise HTTPException(status_code=400, detail="Invalid snapshot id")
    if not _SNAPSHOT_FILE_RE.match(file):
        raise HTTPException(status_code=400, detail="Invalid snapshot file name")

    snapshot_dir = _safe_child(_SNAPSHOTS_DIR, snapshot_id)
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Snapshot folder not found: {snapshot_id}")

    path = _safe_child(snapshot_dir, file)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Snapshot file not found: {file}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        formatted = json.dumps(payload, indent=2, ensure_ascii=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to format snapshot JSON: {exc}")

    truncated = False
    if len(formatted) > max_chars:
        formatted = formatted[:max_chars]
        truncated = True

    return {
        "snapshot_id": snapshot_id,
        "file": file,
        "truncated": truncated,
        "content": formatted,
    }


# ---------------------------------------------------------------------------
# Scan reports section
# ---------------------------------------------------------------------------

@router.get("/scan-types", response_model=List[str])
def list_scan_types():
    """Return sorted list of scan sub-folder names under output/scans/."""
    if not _SCANS_DIR.exists():
        return []
    return sorted(d.name for d in _SCANS_DIR.iterdir() if d.is_dir())


@router.get("/scan-files")
def list_scan_files(scan_type: str = Query(..., description="Scan sub-folder, e.g. sast")):
    """Return file names (html/pdf) within a scan sub-folder."""
    if not _SCAN_TYPE_RE.match(scan_type):
        raise HTTPException(status_code=400, detail="Invalid scan type")
    folder = _SCANS_DIR / scan_type
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Scan type not found: {scan_type}")
    result = []
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.suffix.lower() in (".html", ".pdf"):
            result.append({"name": f.name, "type": f.suffix.lower().lstrip(".")})
    return result


@router.get("/scan-file")
def get_scan_file(
    scan_type: str = Query(...),
    file: str = Query(...),
):
    """Serve an HTML or PDF scan report file."""
    if not _SCAN_TYPE_RE.match(scan_type):
        raise HTTPException(status_code=400, detail="Invalid scan type")
    folder = _SCANS_DIR / scan_type
    path = _safe_child(folder, file)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file}")
    suffix = path.suffix.lower()
    if suffix == ".html":
        media_type = "text/html"
    elif suffix == ".pdf":
        media_type = "application/pdf"
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    return FileResponse(str(path), media_type=media_type, filename=path.name)


# ---------------------------------------------------------------------------
# Log viewer section
# ---------------------------------------------------------------------------

@router.get("/logs", response_model=List[str])
def list_logs():
    """Return sorted list of .log file names from dashboard/logs/."""
    if not _LOGS_DIR.exists():
        return []
    return sorted(f.name for f in _LOGS_DIR.glob("*.log") if _LOG_FILE_RE.match(f.name))


@router.get("/log")
def get_log(
    file: str = Query(..., description="Log file name, e.g. backend.log"),
    lines: int = Query(100, ge=10, le=500, description="Number of lines to return"),
    offset: int = Query(0, ge=0, description="Line offset from the end of the file"),
):
    """
    Return *lines* lines from a log file.

    - ``offset=0``     → last *lines* lines (newest)
    - ``offset=N``     → lines ending at position ``total - N`` from the end (older)
    """
    if not _LOG_FILE_RE.match(file):
        raise HTTPException(status_code=400, detail="Invalid log file name")
    path = _safe_child(_LOGS_DIR, file)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Log file not found: {file}")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            all_lines = fh.readlines()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read log: {exc}")

    total = len(all_lines)
    if offset == 0:
        chunk = all_lines[-lines:] if lines <= total else all_lines
    else:
        end = max(0, total - offset)
        start = max(0, end - lines)
        chunk = all_lines[start:end]

    return {
        "lines": [ln.rstrip("\n") for ln in chunk],
        "total_lines": total,
        "offset": offset,
        "returned": len(chunk),
    }
