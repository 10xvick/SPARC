#!/usr/bin/env python3
"""
Security Scan Report Downloader

Downloads SAST, SCA, DAST, and Mend security reports from Nexus repositories.
Projects and their report URLs are driven by config/security_scan_config.json —
add or remove projects there (or via the Onboarding UI) without touching this script.

Output structure:
    output/scans/sast/   – HTML SAST reports for each project
    output/scans/sca/    – HTML SCA reports for each project
    output/scans/dast/   – HTML DAST reports for each project
    output/scans/mend/   – PDF Mend reports for each project

Usage:
    python src/security_scan_fetch.py
"""

import json
import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Project root resolution (consistent with other src/ scripts)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCAN_CONFIG_FILE = PROJECT_ROOT / "config" / "security_scan_config.json"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 60


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_scan_config() -> dict:
    """Load and return the security_scan_config.json contents."""
    if not SCAN_CONFIG_FILE.exists():
        logger.error(f"Scan config file not found: {SCAN_CONFIG_FILE}")
        sys.exit(1)
    try:
        with open(SCAN_CONFIG_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.error(f"Failed to read scan config: {exc}")
        sys.exit(1)


def build_report_list(config: dict) -> list[tuple[str, str]]:
    """
    Convert config['projects'] into a flat list of (output_relative_path, url)
    tuples used by the downloader.
    """
    reports: list[tuple[str, str]] = []
    for project in config.get("projects", []):
        pid = project.get("id", "").strip().lower()
        if not pid:
            logger.warning(f"Skipping project with missing id: {project}")
            continue
        for report in project.get("reports", []):
            rtype = report.get("type", "").strip().lower()
            url = report.get("url", "").strip()
            filename = report.get("filename", "").strip()
            if not (rtype and url and filename):
                logger.warning(f"Skipping incomplete report entry for project '{pid}': {report}")
                continue
            reports.append((f"{rtype}/{filename}", url))
    return reports


def get_nexus_check_urls(config: dict) -> list[tuple[str, str]]:
    """Return (label, check_url) pairs from nexus_domains in config."""
    checks = []
    for label, base in config.get("nexus_domains", {}).items():
        checks.append((label.upper(), base.rstrip("/") + "/"))
    return checks


def _get_requests():
    """Lazy import of requests (available in the backend venv)."""
    try:
        import requests
        return requests
    except ImportError:
        logger.error("'requests' library is not installed. Run: pip install requests")
        sys.exit(1)


def _prepare_output_dirs(scans_root: Path, report_types: set[str]) -> None:
    """Create output sub-directories for each report type."""
    for subdir in report_types:
        (scans_root / subdir).mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory ready: {scans_root}")


def _check_connectivity(requests_mod, url: str, label: str, auth: tuple) -> bool:
    """Return True if the Nexus endpoint is reachable and credentials are valid."""
    try:
        resp = requests_mod.get(
            url,
            auth=auth,
            verify=False,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            logger.info(f"[CHECK] {label} → OK (HTTP 200)")
            return True
        else:
            logger.warning(f"[CHECK] {label} → HTTP {resp.status_code}")
            return False
    except Exception as exc:
        logger.warning(f"[CHECK] {label} → connection error: {exc}")
        return False


def _download_file(requests_mod, dest: Path, url: str, auth: tuple) -> bool:
    """
    Download *url* to *dest* with up to MAX_RETRIES attempts.
    Returns True on success, False on failure.
    """
    # Pre-flight HEAD check
    try:
        head = requests_mod.head(
            url,
            auth=auth,
            verify=False,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if head.status_code != 200:
            logger.error(f"  ✗ Pre-flight failed for {dest.name}: HTTP {head.status_code} → {url}")
            return False
    except Exception as exc:
        logger.error(f"  ✗ Pre-flight error for {dest.name}: {exc}")
        return False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"  ↓ Downloading ({attempt}/{MAX_RETRIES}): {dest.name}")
            resp = requests_mod.get(
                url,
                auth=auth,
                verify=False,
                timeout=REQUEST_TIMEOUT_SECONDS,
                stream=True,
            )
            resp.raise_for_status()

            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)

            file_size_kb = dest.stat().st_size / 1024
            logger.info(f"  ✓ Saved: {dest.relative_to(PROJECT_ROOT)}  ({file_size_kb:.1f} KB)")
            return True

        except Exception as exc:
            logger.warning(f"  ⚠ Attempt {attempt} failed for {dest.name}: {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

    logger.error(f"  ✗ FAILED after {MAX_RETRIES} retries: {url}")
    return False


def main() -> None:
    """Entry point — load config then download all configured security scan reports."""
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("Security Scan Report Downloader — starting")
    logger.info(f"Project root: {PROJECT_ROOT}")

    # ── Load config ───────────────────────────────────────────────────────
    config = load_scan_config()
    creds = config.get("credentials", {})
    username = creds.get("username", "admin")
    password = creds.get("password", "")
    auth = (username, password)

    reports = build_report_list(config)
    if not reports:
        logger.warning("No report entries found in config — nothing to download.")
        return

    check_urls = get_nexus_check_urls(config)
    project_names = [p.get("name", p.get("id", "?")) for p in config.get("projects", [])]
    report_types = {r[0].split("/")[0] for r in reports}

    logger.info(f"Projects configured: {', '.join(project_names)}")
    logger.info(f"Total reports: {len(reports)}")

    requests_mod = _get_requests()

    # Suppress urllib3 InsecureRequestWarning (self-signed certs on Nexus)
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

    # ── Prepare output directories ────────────────────────────────────────
    scans_root = PROJECT_ROOT / "output" / "scans"
    _prepare_output_dirs(scans_root, report_types)

    # ── Connectivity checks (non-fatal — continue even if one domain is down) ──
    logger.info("--- Connectivity checks ---")
    for label, check_url in check_urls:
        ok = _check_connectivity(requests_mod, check_url, label, auth)
        if not ok:
            logger.warning(f"{label} Nexus unreachable — reports on this domain will likely fail")

    # ── Download all reports ──────────────────────────────────────────────
    logger.info("--- Downloading reports ---")
    total = len(reports)
    succeeded = 0
    failed_files: list[str] = []

    for idx, (rel_path, url) in enumerate(reports, start=1):
        dest = scans_root / rel_path
        logger.info(f"[{idx}/{total}] {rel_path}")

        ok = _download_file(requests_mod, dest, url, auth)
        if ok:
            succeeded += 1
        else:
            failed_files.append(rel_path)

    # ── Summary ───────────────────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 60)
    logger.info(f"Done — {succeeded}/{total} reports downloaded successfully  ({elapsed:.1f}s)")

    if failed_files:
        logger.warning(f"{len(failed_files)} file(s) failed:")
        for f in failed_files:
            logger.warning(f"  ✗ {f}")
        sys.exit(1)
    else:
        logger.info("All reports downloaded successfully.")


if __name__ == "__main__":
    main()
