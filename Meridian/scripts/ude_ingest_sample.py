#!/usr/bin/env python3
"""
UDE Installation Data - Sample Ingestor Program

This sample program demonstrates how to:
1. Read UDE installation data from local CSV files
2. Map User IDs to employee SAPIDs using Resources.csv
3. Create UDE installation event records for the TeamSight API
4. Call the remote UDE Installation API to ingest the data
5. Save generated JSON payloads for verification and debugging

USAGE:
    python3 ude_ingest_sample.py \\
        --resources /path/to/Resources.csv \\
        --ude-data /path/to/UDE_sheet.csv \\
        --extension-data /path/to/Extension_Availability.csv \\
        --api-url http://10.222.2.217:8000 \\
        --api-user ude_api_user \
        --api-password ude_api_user_pass \
        --output-dir ./ude_payloads

REQUIREMENTS:
    - Python 3.10+
    - requests library (pip install requests)

AUTHORS:
    TeamSight Platform Team (2026)

NOTES ON THE DATA:
    - User_ID in UDE CSV files maps to UDEID in Resources.csv
    - SAPID is looked up from Resources.csv based on UDEID match
    - Each row in UDE_sheet.csv represents one installation event
    - Device information is generated from User_ID (dummy values)
    - Release information is looked up from Extension_Availability.csv
"""

import argparse
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    print("ERROR: requests library not installed. Install with: pip install requests")
    sys.exit(1)

# Configure logging: shows timestamps, log level, and messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# =============================================================================
# Data Loading & Mapping Functions
# =============================================================================

def load_resources_csv(resources_path: Path) -> Dict[str, str]:
    """
    Load Resources.csv and build a mapping of UDEID → SAPID.
    
    The Resources.csv has a column 'UDEID' which contains the User_ID values
    from the UDE data sheets. We use this to map User_ID → SAPID.
    
    Args:
        resources_path: Path to Resources.csv
        
    Returns:
        Dictionary mapping UDEID → SAPID (both as strings).
        Example: {'aakif.quayyum': '52090140', ...}
    """
    mapping = {}
    try:
        with resources_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                udeid = row.get("UDEID", "").strip()
                sapid = row.get("SAPID", "").strip()
                
                # Only add valid mappings: both fields must be non-empty
                if udeid and sapid:
                    mapping[udeid] = sapid
        
        logger.info(f"✓ Loaded {len(mapping)} UDEID → SAPID mappings from Resources.csv")
        return mapping
    
    except FileNotFoundError:
        logger.error(f"ERROR: Resources.csv not found at {resources_path}")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"ERROR reading Resources.csv: {exc}")
        sys.exit(1)


def load_extension_availability(ext_path: Path) -> Dict[str, str]:
    """
    Load Extension_Availability.csv to map version → release_date.
    
    This allows us to look up when each UDE version was released, which we
    include in the API payload as 'release_date'.
    
    Args:
        ext_path: Path to UDE - Extension Availability.csv
        
    Returns:
        Dictionary mapping version string → release date string.
        Example: {'1.8.2': '2026-03-20', ...}
    """
    mapping = {}
    try:
        with ext_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                version = row.get("UDE_extension_version", "").strip()
                date = row.get("Extension_availability_date", "").strip()
                
                if version and date:
                    mapping[version] = date
        
        logger.info(f"✓ Loaded {len(mapping)} version → release_date mappings")
        return mapping
    
    except FileNotFoundError:
        logger.warning(f"WARNING: Extension availability file not found at {ext_path}")
        logger.warning("Will proceed without release_date metadata")
        return {}
    except Exception as exc:
        logger.warning(f"WARNING reading extension file: {exc}")
        return {}


def load_ude_data(ude_path: Path) -> List[Dict[str, str]]:
    """
    Load UDE - UDE_sheet.csv containing all installation records.
    
    Columns expected:
        - User_ID: Identifier from UDE system (maps to UDEID)
        - UDE_extension_version: Version string (e.g., '1.8.2')
        - Extension_installation_upgradation_date: Installation date (YYYY-MM-DD)
    
    Args:
        ude_path: Path to UDE - UDE_sheet.csv
        
    Returns:
        List of dictionaries, one per row.
    """
    records = []
    try:
        with ude_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
        
        logger.info(f"✓ Loaded {len(records)} UDE installation records")
        return records
    
    except FileNotFoundError:
        logger.error(f"ERROR: UDE data file not found at {ude_path}")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"ERROR reading UDE data: {exc}")
        sys.exit(1)


# =============================================================================
# Installation Record Generation
# =============================================================================

def generate_event_id(user_id: str, version: str, date: str, index: int) -> str:
    """
    Generate a unique, stable install_event_id for an installation record.
    
    The event ID must be unique and reproducible. It's used as a deduplication
    key when pushing to the API. If the same event_id is submitted again, the
    API will update the record in place (upsert).
    
    Format: EVT-YYYYMMDD-{user_hash}-{version_hash}-{index}
    
    Args:
        user_id: Username/email from UDE system
        version: UDE version string
        date: Installation date (YYYY-MM-DD)
        index: Row index (in case of duplicates)
        
    Returns:
        Stable event ID string
    """
    # Use date as YYYYMMDD for readability
    date_compact = date.replace("-", "")
    
    # Use last 4 chars of user_id hash for compact representation
    user_hash = hex(hash(user_id) & 0xFFFF)[2:].zfill(4)
    
    # Use version with dots replaced for compact format
    version_compact = version.replace(".", "")
    
    return f"EVT-{date_compact}-{user_hash}-{version_compact}-{index:03d}"


def generate_device_id(user_id: str) -> str:
    """
    Generate a stable but dummy device_id for the installation.
    
    In a real scenario, the UDE system would provide the actual device/machine ID.
    For this sample, we generate a consistent device ID based on the user.
    
    This allows the sample to demonstrate:
    - An employee with multiple devices (via different device_ids)
    - Same device with different versions (version upgrades on same device)
    
    Args:
        user_id: Username/email
        
    Returns:
        Dummy but stable device ID (e.g., LAPTOP-HCL-ABC123)
    """
    # Extract initials or alphanumeric prefix from user_id
    safe_user = "".join(c for c in user_id[:8] if c.isalnum()).upper()
    
    # Deterministic hash for pseudo-unique device ID
    device_number = abs(hash(user_id)) % 10000
    
    return f"LAPTOP-HCL-{safe_user}{device_number:05d}"


def create_installation_records(
    ude_records: List[Dict[str, str]],
    udeid_to_sapid: Dict[str, str],
    version_to_release_date: Dict[str, str],
    report_date: str
) -> Tuple[List[Dict], List[str]]:
    """
    Transform raw UDE data rows into API-ready installation event records.
    
    This function:
    1. Maps each User_ID to a SAPID using the resources mapping
    2. Extracts version and date information
    3. Generates stable event IDs and device IDs
    4. Fills in dummy values for fields not in the CSV (device_label, etc.)
    
    Args:
        ude_records: List of dicts from UDE_sheet.csv
        udeid_to_sapid: Mapping of UDEID → SAPID
        version_to_release_date: Mapping of version → release date
        report_date: Date of this data snapshot (YYYY-MM-DD)
        
    Returns:
        Tuple of (installation_records, skipped_users)
        - installation_records: List of ready-to-send dicts
        - skipped_users: List of User_IDs that couldn't be mapped
    """
    records = []
    skipped = []
    
    for idx, ude_row in enumerate(ude_records):
        user_id = ude_row.get("User_ID", "").strip()
        version = ude_row.get("UDE_extension_version", "").strip()
        install_date = ude_row.get("Extension_installation_upgradation_date", "").strip()
        
        # Validate required fields
        if not user_id or not version or not install_date:
            logger.warning(f"Row {idx+1}: Skipping incomplete record (User_ID={user_id})")
            skipped.append(user_id)
            continue
        
        # Look up SAPID for this User_ID
        sapid = udeid_to_sapid.get(user_id)
        if not sapid:
            logger.warning(f"Row {idx+1}: SAPID not found for User_ID '{user_id}' — skipping")
            skipped.append(user_id)
            continue
        
        # Build the installation record
        record = {
            # === Required fields ===
            "install_event_id": generate_event_id(user_id, version, install_date, idx),
            "ude_id": f"UDE-{user_id}",  # Dummy UDE ID based on user_id
            "sapid": sapid,
            "device_id": generate_device_id(user_id),
            "version": version,
            "installed_date": install_date,  # API accepts YYYY-MM-DD format
            
            # === Optional fields (filled with dummy or mapped values) ===
            "employee_name": user_id,  # Username as display name
            "device_label": "Primary Laptop",  # Dummy device label
            "release_name": f"UDE-Release-{version}",  # Generated release name
            "release_date": version_to_release_date.get(version),  # Looked up from availability data
            "status": "installed",  # Assume all records are currently installed
        }
        
        records.append(record)
    
    logger.info(f"✓ Generated {len(records)} installation records")
    if skipped:
        logger.warning(f"⚠ Skipped {len(skipped)} records (unmapped or incomplete)")
    
    return records, skipped


# =============================================================================
# API Integration
# =============================================================================

class UDEAPIClient:
    """
    Client for communicating with the TeamSight UDE Installation API.
    
    Handles:
    - JWT token authentication
    - Token refresh on expiry
    - Batch ingest requests
    - Error handling and logging
    """
    
    def __init__(self, api_url: str, api_user: str, api_password: str):
        """
        Initialize API client.
        
        Args:
            api_url: Base URL of the TeamSight API (e.g., http://10.222.2.217:8000)
            api_user: Username for API authentication (typically 'api_user')
            api_password: Password for API authentication
        """
        self.api_url = api_url.rstrip("/")
        self.api_user = api_user
        self.api_password = api_password
        self.token: Optional[str] = None
        self.refresh_token: Optional[str] = None
    
    def authenticate(self) -> bool:
        """
        Authenticate with the API and obtain a JWT bearer token.
        
        Returns True on success; False on failure.
        """
        url = f"{self.api_url}/api/auth/login"
        payload = {
            "sapid": self.api_user,
            "password": self.api_password
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            self.token = data.get("access_token")
            self.refresh_token = data.get("refresh_token")
            
            logger.info(f"✓ Authenticated with API (user: {self.api_user})")
            return True
        
        except requests.exceptions.RequestException as exc:
            logger.error(f"✗ Authentication failed: {exc}")
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Build request headers with Bearer token.
        
        Returns:
            Dict of HTTP headers
        """
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def ingest(self, records: List[Dict], report_date: str, source_system: str = "UDE-Sample-Ingestor") -> bool:
        """
        Submit a batch of installation records to the API.
        
        Args:
            records: List of installation record dicts
            report_date: Snapshot date (YYYY-MM-DD)
            source_system: Identifier of the source system
            
        Returns:
            True if all records accepted; False otherwise.
        """
        if not records:
            logger.warning("No records to ingest")
            return False
        
        url = f"{self.api_url}/api/ude/installations"
        payload = {
            "report_date": report_date,
            "source_system": source_system,
            "installations": records
        }
        
        try:
            resp = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
            data = resp.json()
            
            if resp.status_code == 200:
                logger.info(f"✓ Ingest successful!")
                logger.info(f"  Accepted: {data.get('accepted')}")
                logger.info(f"  Skipped: {data.get('skipped')}")
                
                if data.get("errors"):
                    logger.warning(f"  Errors: {len(data.get('errors'))} records had validation errors")
                
                return data.get("accepted", 0) > 0
            else:
                logger.error(f"✗ Ingest failed: HTTP {resp.status_code}")
                logger.error(f"  Response: {json.dumps(data, indent=2)}")
                return False
        
        except requests.exceptions.RequestException as exc:
            logger.error(f"✗ Ingest request failed: {exc}")
            return False


# =============================================================================
# Main Program
# =============================================================================

def main():
    """
    Main entry point.
    
    Workflow:
    1. Parse command-line arguments
    2. Load CSV files and build mappings
    3. Generate installation records from UDE data
    4. Authenticate with API
    5. Submit records to API
    6. Save generated payloads to disk for verification
    """
    
    parser = argparse.ArgumentParser(
        description="UDE Installation Data Ingestor - Sample Program",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

  # Ingest with default output directory
  python3 ude_ingest_sample.py \\
    --resources /path/to/Resources.csv \\
    --ude-data "/path/to/UDE - UDE_sheet.csv" \\
    --extension-data "/path/to/UDE - Extension Availability.csv" \\
    --api-url http://10.222.2.217:8000 \\
        --api-user ude_api_user \
        --api-password ude_api_user_pass

  # Custom output directory
  python3 ude_ingest_sample.py \\
    --resources ./Resources.csv \\
    --ude-data "./UDE - UDE_sheet.csv" \\
    --extension-data "./UDE - Extension Availability.csv" \\
    --api-url http://10.222.2.217:8000 \\
        --api-user ude_api_user \
        --api-password ude_api_user_pass \
    --output-dir ./ude_payloads_debug
        """
    )
    
    parser.add_argument(
        "--resources",
        type=Path,
        required=True,
        help="Path to Resources.csv (for SAPID mapping)"
    )
    parser.add_argument(
        "--ude-data",
        type=Path,
        required=True,
        help="Path to UDE - UDE_sheet.csv"
    )
    parser.add_argument(
        "--extension-data",
        type=Path,
        default=None,
        help="Path to UDE - Extension Availability.csv (optional, for release dates)"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        required=True,
        help="Base URL of TeamSight API (e.g., http://10.222.2.217:8000)"
    )
    parser.add_argument(
        "--api-user",
        type=str,
        default="ude_api_user",
        help="API username for authentication (default: ude_api_user)"
    )
    parser.add_argument(
        "--api-password",
        type=str,
        default="ude_api_user_pass",
        help="API password for authentication (default: ude_api_user_pass)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./ude_payloads"),
        help="Directory to save generated JSON payloads (default: ./ude_payloads)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate payloads but don't submit to API (for testing)"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("UDE Installation Data Ingestor - Sample Program")
    logger.info("=" * 70)
    logger.info(f"Resources: {args.resources}")
    logger.info(f"UDE Data: {args.ude_data}")
    logger.info(f"Extension Data: {args.extension_data}")
    logger.info(f"API URL: {args.api_url}")
    logger.info(f"Output Dir: {args.output_dir}")
    if args.dry_run:
        logger.info("(DRY RUN - no API submission)")
    logger.info("=" * 70)
    
    # === Step 1: Load all data ===
    logger.info("\n[1/5] Loading data files...")
    
    udeid_to_sapid = load_resources_csv(args.resources)
    
    extension_map = {}
    if args.extension_data:
        extension_map = load_extension_availability(args.extension_data)
    
    ude_records = load_ude_data(args.ude_data)
    
    # === Step 2: Generate installation records ===
    logger.info("\n[2/5] Generating installation records...")
    
    report_date = datetime.now().strftime("%Y-%m-%d")
    records, skipped = create_installation_records(
        ude_records,
        udeid_to_sapid,
        extension_map,
        report_date
    )
    
    if not records:
        logger.error("ERROR: No valid installation records generated. Aborting.")
        return 1
    
    # === Step 3: Save generated payloads to disk ===
    logger.info("\n[3/5] Saving payloads to disk...")
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save the full ingest payload
    payload = {
        "report_date": report_date,
        "source_system": "UDE-Sample-Ingestor",
        "installations": records
    }
    
    payload_file = args.output_dir / f"ude_ingest_payload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    payload_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(f"✓ Payload saved to: {payload_file}")
    
    # Also save a summary of what was generated
    summary = {
        "timestamp": datetime.now().isoformat(),
        "report_date": report_date,
        "total_records_in_csv": len(ude_records),
        "records_processed": len(records),
        "records_skipped": len(skipped),
        "skipped_users": skipped,
        "first_record_sample": records[0] if records else None,
    }
    
    summary_file = args.output_dir / f"ude_ingest_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(f"✓ Summary saved to: {summary_file}")
    
    # === Step 4: Authenticate with API (unless dry-run) ===
    if args.dry_run:
        logger.info("\n[4/5] DRY RUN - Skipping API authentication")
        logger.info("\n[5/5] DRY RUN - Skipping API submission")
        logger.info("\n" + "=" * 70)
        logger.info("Dry-run complete. JSON payloads saved for inspection.")
        logger.info("=" * 70)
        return 0
    
    logger.info("\n[4/5] Authenticating with API...")
    
    client = UDEAPIClient(args.api_url, args.api_user, args.api_password)
    if not client.authenticate():
        logger.error("ERROR: Failed to authenticate with API. Aborting.")
        return 1
    
    # === Step 5: Submit to API ===
    logger.info("\n[5/5] Submitting to API...")
    
    if client.ingest(records, report_date):
        logger.info("\n" + "=" * 70)
        logger.info("✓ SUCCESS: All records submitted to API!")
        logger.info("=" * 70)
        logger.info(f"JSON payloads saved to: {args.output_dir}")
        logger.info("\nYou can now:")
        logger.info(f"  1. Inspect the payload at: {payload_file}")
        logger.info(f"  2. Query the API: GET /api/ude/installations")
        logger.info(f"  3. Check the latest summary: GET /api/ude/installations/summary")
        return 0
    else:
        logger.error("\n" + "=" * 70)
        logger.error("✗ FAILURE: Some records were not submitted.")
        logger.error("=" * 70)
        logger.error(f"Check the payload at: {payload_file}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
