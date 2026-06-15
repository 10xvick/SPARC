# UDE Installation Data Ingestor - Sample Program

This directory contains **sample integration code** demonstrating how to submit UDE (Unified Development Environment) installation data to the TeamSight API.

## Overview

The `ude_ingest_sample.py` script shows external integrators how to:

1. **Read UDE installation data** from CSV files (employee installations, version availability)
2. **Map user IDs to employee records** using the TeamSight Resources.csv reference
3. **Transform raw data** into properly formatted installation event records
4. **Authenticate with the API** using JWT tokens
5. **Submit batches of records** to the TeamSight UDE Installation API
6. **Save generated payloads** to disk for verification and debugging

---

## Quick Start

### Prerequisites

```bash
# Python 3.10+ required
python3 --version

# Install the requests library (if not already installed)
pip install requests
```

### Running the Sample (Dry-Run Mode)

Test the data transformation without submitting to the API:

```bash
python3 scripts/ude_ingest_sample.py \
  --resources config/Resources.csv \
  --ude-data "data/UDE - UDE_sheet.csv" \
  --extension-data "data/UDE - Extension Availability.csv" \
  --api-url http://10.222.2.217:8000 \
  --api-user api_user \
  --api-password dummy_password_for_dry_run \
  --output-dir ./ude_payloads_test \
  --dry-run
```

This will:
- ✅ Load and validate all CSV files
- ✅ Transform data into API format
- ✅ Save generated JSON payloads to `./ude_payloads_test/`
- ❌ **NOT** authenticate or submit to the API

---

### Running the Sample (Live Submission)

Submit data to your remote API:

```bash
python3 scripts/ude_ingest_sample.py \
  --resources config/Resources.csv \
  --ude-data "data/UDE - UDE_sheet.csv" \
  --extension-data "data/UDE - Extension Availability.csv" \
  --api-url http://10.222.2.217:8000 \
  --api-user api_user \
  --api-password <actual_api_password> \
  --output-dir ./ude_payloads
```

This will:
- ✅ Load and validate all CSV files
- ✅ Transform data into API format
- ✅ Save generated JSON payloads to `./ude_payloads/`
- ✅ Authenticate with the API
- ✅ Submit all records in a single batch request

---

## Command-Line Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--resources` | ✓ | — | Path to `Resources.csv` (employee master data) |
| `--ude-data` | ✓ | — | Path to `UDE - UDE_sheet.csv` (installations) |
| `--extension-data` | — | `None` | Path to `UDE - Extension Availability.csv` (versions) |
| `--api-url` | ✓ | — | Base URL of TeamSight API (e.g., `http://10.222.2.217:8000`) |
| `--api-user` | — | `api_user` | API username for authentication |
| `--api-password` | ✓ | — | API password for authentication |
| `--output-dir` | — | `./ude_payloads` | Directory to save generated JSON files |
| `--dry-run` | — | `false` | Test mode: generate payloads but don't submit |

---

## Input Files

### Resources.csv
**Purpose:** Employee master data and UDEID mapping.

**Key columns (must be present):**
- `UDEID` — User identifier from UDE system (maps to User_ID in UDE_sheet.csv)
- `SAPID` — TeamSight employee ID (looked up from UDEID)

**Example:**
```
Ref,Name,SAPID,UDEID,...
1,John Doe,52090140,john.doe,...
2,Jane Smith,52090141,jane.smith,...
```

### UDE - UDE_sheet.csv
**Purpose:** Installation records for each employee/device/version.

**Required columns:**
- `User_ID` — UDE user identifier (matches UDEID in Resources.csv)
- `UDE_extension_version` — Version string (e.g., "1.8.2")
- `Extension_installation_upgradation_date` — Installation date (YYYY-MM-DD format)

**Example:**
```
User_ID,UDE_extension_version,Extension_installation_upgradation_date
john.doe,1.8.2,2026-04-20
jane.smith,1.8.1,2026-04-15
john.doe,1.7.5,2026-01-10
```

### UDE - Extension Availability.csv (Optional)
**Purpose:** Metadata about UDE versions (release dates, etc.).

**Key columns:**
- `UDE_extension_version` — Version string
- `Extension_availability_date` — Release date (YYYY-MM-DD format)

**Example:**
```
UDE_extension_version,Extension_availability_date
1.8.2,2026-03-20
1.8.1,2026-02-15
1.7.5,2025-12-10
```

If this file is not provided, the `release_date` field will be `null` in the API payload.

---

## Output Files

The script saves generated payloads to help verify data transformation and API submission.

### Sample Output Structure

```
./ude_payloads/
├── ude_ingest_payload_20260422_204500.json    ← Full API request payload
└── ude_ingest_summary_20260422_204500.json     ← Metadata and statistics
```

### Payload File Format

```json
{
  "report_date": "2026-04-22",
  "source_system": "UDE-Sample-Ingestor",
  "installations": [
    {
      "install_event_id": "EVT-20260420-a1b2-1882-000",
      "ude_id": "UDE-john.doe",
      "sapid": "52090140",
      "device_id": "LAPTOP-HCL-JOHNDOE00042",
      "version": "1.8.2",
      "installed_date": "2026-04-20",
      "employee_name": "john.doe",
      "device_label": "Primary Laptop",
      "release_name": "UDE-Release-1.8.2",
      "release_date": "2026-03-20",
      "status": "installed"
    },
    ...
  ]
}
```

### Summary File Format

```json
{
  "timestamp": "2026-04-22T20:45:00.123456",
  "report_date": "2026-04-22",
  "total_records_in_csv": 500,
  "records_processed": 492,
  "records_skipped": 8,
  "skipped_users": [
    "unknown.user.1",
    "invalid.id",
    ...
  ],
  "first_record_sample": { ... }
}
```

---

## Data Transformation Logic

### User ID Mapping

The script maps `User_ID` from the UDE CSV to employee records:

1. **Look up** `User_ID` value in Resources.csv `UDEID` column
2. **Extract** `SAPID` and other employee details from the matching row
3. **If not found**, skip the record and log a warning

### Device ID Generation

Since the UDE CSV doesn't provide device-level information, the script generates a stable device ID:

```python
device_id = f"LAPTOP-HCL-{user_initials}{random_hash:05d}"
```

**Why?** This demonstrates how to handle scenarios with multiple devices per employee.

In a production implementation, the UDE system would provide the actual device/machine ID.

### Event ID Generation

Each installation record gets a unique, reproducible event ID:

```python
event_id = f"EVT-{date_compact}-{user_hash}-{version_hash}-{index}"
```

**Why?** The event ID serves as a deduplication key. If the same event is submitted twice, the API will update the record in place (upsert). This ensures idempotence.

### Release Date Lookup

If the Extension_Availability.csv is provided, the script looks up the release date for each version:
- Found → included in payload as `release_date`
- Not found → included as `null`

---

## API Request Format

The script submits data using the **Batch Ingest** endpoint.

### Endpoint

```
POST /api/ude/installations
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

### Request Payload

```json
{
  "report_date": "2026-04-22",
  "source_system": "UDE-Sample-Ingestor",
  "installations": [
    { "install_event_id": "EVT-...", ... },
    { "install_event_id": "EVT-...", ... },
    ...
  ]
}
```

### Response

```json
{
  "accepted": 492,
  "skipped": 0,
  "errors": []
}
```

- `accepted` — number of records successfully processed
- `skipped` — number of records rejected (e.g., duplicate SAPID)
- `errors` — array of validation errors (if any)

---

## Common Use Cases

### Test the Data Transformation (No API Call)

```bash
python3 scripts/ude_ingest_sample.py \
  --resources config/Resources.csv \
  --ude-data "data/UDE - UDE_sheet.csv" \
  --extension-data "data/UDE - Extension Availability.csv" \
  --api-url http://dummy.url \
  --api-user api_user \
  --api-password dummy \
  --output-dir ./ude_debug \
  --dry-run
```

Then inspect `./ude_debug/ude_ingest_payload_*.json` to see the generated data.

### Submit Data to Remote Server

```bash
python3 scripts/ude_ingest_sample.py \
  --resources config/Resources.csv \
  --ude-data "data/UDE - UDE_sheet.csv" \
  --extension-data "data/UDE - Extension Availability.csv" \
  --api-url http://10.222.2.217:8000 \
  --api-user api_user \
  --api-password $API_PASSWORD \
  --output-dir ./ude_payloads
```

### Submit Only Version Availability Data

To submit only the version metadata (without employees), create a minimal CSV:

```csv
User_ID,UDE_extension_version,Extension_installation_upgradation_date
admin,1.8.2,2026-03-20
admin,1.8.1,2026-02-15
admin,1.7.5,2025-12-10
```

---

## Error Handling

### Unmapped User IDs

If a `User_ID` from the UDE CSV doesn't exist in Resources.csv:
- **Record is skipped** with a warning
- **Summary file** includes skipped users list
- **API is not called** for that record

Example warning:
```
[WARNING] Row 42: SAPID not found for User_ID 'unknown.user' — skipping
```

### Incomplete Rows

Records with missing required fields are skipped:
- `User_ID` is empty
- `UDE_extension_version` is empty
- `Extension_installation_upgradation_date` is empty

### API Errors

If the API returns an error:
- **Error details** are logged
- **Payload is saved** for debugging
- **Exit code 1** indicates failure

---

## Integration with External Systems

To integrate your own UDE system with TeamSight:

1. **Convert your data** to CSV format matching the schema above
2. **Place files** in appropriate data directories
3. **Run this sample** (or adapt the code) with your files
4. **Verify output** JSON payloads in the output directory
5. **Submit to API** using the same endpoint

### Python Integration Example

```python
from ude_ingest_sample import UDEAPIClient, create_installation_records

# Your custom data loading
my_records = load_my_ude_data()
udeid_to_sapid = load_my_mappings()

# Generate API-format records
api_records, skipped = create_installation_records(
    my_records,
    udeid_to_sapid,
    version_metadata,
    report_date="2026-04-22"
)

# Submit to API
client = UDEAPIClient("http://10.222.2.217:8000", "api_user", "password")
client.authenticate()
client.ingest(api_records, "2026-04-22")
```

---

## Authentication

The sample uses **JWT Bearer tokens** for API authentication.

### Token Acquisition

1. User provides `--api-user` and `--api-password`
2. Sample calls `POST /api/auth/login` with credentials
3. API responds with `access_token` (JWT)
4. Sample includes bearer token in all subsequent requests

### Token Scope

The API user must have one of these roles:
- `Admin` (full access)
- `API User` (UDE ingest only)

**Note:** The sample does not handle token refresh. For production integrations, implement refresh-token logic if calls exceed token TTL.

---

## Logging

The script provides detailed logging to help with debugging.

### Log Levels

| Level | Example |
|-------|---------|
| **INFO** | file loaded, records processed, success messages |
| **WARNING** | unmapped users, missing optional data |
| **ERROR** | authentication failure, file not found, API errors |

### Example Output

```
2026-04-22 20:45:00 [INFO] UDE Installation Data Ingestor - Sample Program
2026-04-22 20:45:00 [INFO] Resources: config/Resources.csv
2026-04-22 20:45:00 [INFO] ✓ Loaded 165 UDEID → SAPID mappings from Resources.csv
2026-04-22 20:45:01 [INFO] ✓ Loaded 500 UDE installation records
2026-04-22 20:45:01 [INFO] ✓ Generated 492 installation records
2026-04-22 20:45:01 [WARNING] ⚠ Skipped 8 records (unmapped or incomplete)
2026-04-22 20:45:01 [INFO] ✓ Payload saved to: ./ude_payloads/ude_ingest_payload_20260422_204501.json
2026-04-22 20:45:02 [INFO] ✓ Authenticated with API (user: api_user)
2026-04-22 20:45:03 [INFO] ✓ Ingest successful!
2026-04-22 20:45:03 [INFO]   Accepted: 492
2026-04-22 20:45:03 [INFO]   Skipped: 0
```

---

## Troubleshooting

### "SAPID not found for User_ID..."

**Cause:** The `User_ID` in the UDE CSV doesn't match any `UDEID` in Resources.csv.

**Solution:**
1. Verify spelling of `User_ID` matches `UDEID` exactly (case-sensitive)
2. Check if the employee is in Resources.csv at all
3. Inspect the summary file for the full list of skipped users

### "Authentication failed"

**Cause:** Invalid credentials or API endpoint unreachable.

**Solution:**
1. Verify `--api-url` is correct and reachable (test with curl)
2. Verify `--api-user` and `--api-password` are correct
3. Check if the API server is running: `ssh root@10.222.2.217 "cd /opt/teamsight/teamsight/dashboard && ./manage.sh status"`

### "No valid installation records generated"

**Cause:** All records were skipped (no mappings found or invalid data).

**Solution:**
1. Run in `--dry-run` mode to inspect the summary file
2. Check the `skipped_users` list
3. Verify Resources.csv has UDEID column matching your data
4. Verify UDE CSV has required columns (User_ID, version, date)

### Records submitted but API returns errors

**Solution:**
1. Inspect the payload file saved to disk
2. Check the error details in API response
3. Look for validation issues (missing SAPID, invalid date format, etc.)
4. Review the API specification: [docs/UDE_INSTALLATION_API_SPEC.md](../docs/UDE_INSTALLATION_API_SPEC.md)

---

## Next Steps

1. **Test locally** with `--dry-run` to verify data transformation
2. **Inspect generated JSONs** in the output directory
3. **Review the API specification** (docs/UDE_INSTALLATION_API_SPEC.md)
4. **Run live submission** with the remote API endpoint
5. **Query results** using the GET endpoints:
   ```
   GET http://10.222.2.217:8000/api/ude/installations?sapid=52090140
   ```

---

## Support

For questions about this sample program:
1. Review the inline code comments (heavily documented)
2. Check the API specification: [docs/UDE_INSTALLATION_API_SPEC.md](../docs/UDE_INSTALLATION_API_SPEC.md)
3. Contact the TeamSight platform team

---

## License

This sample code is provided as-is for integration reference. Modify freely for your use case.
