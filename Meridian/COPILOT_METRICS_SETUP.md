# Copilot Usage Metrics Collection Job - Setup Complete

## Summary

A new scheduled job has been successfully created to collect GitHub Copilot usage metrics from an Azure SQL Database.

## What Was Created

### 1. Configuration File
**File**: `config/copilot_metrics_config.json`

Defines database connection parameters and job features:
- Database: metrics-genai.database.windows.net:1433
- User: srinivas.rao@metrics-genai
- Encryption: Enabled (SSL)
- All parameters configurable via environment variables

### 2. Python Script
**File**: `src/copilot_metrics_fetch.py`

Implements the metrics collection logic:
- Tests database connectivity
- Lists all available tables with schemas
- Identifies Copilot-related tables
- Clear error messages with installation instructions for ODBC drivers
- Configuration loading from JSON with environment variable overrides
- Comprehensive logging output

### 3. Documentation
**File**: `docs/COPILOT_METRICS_JOB.md`

Complete reference guide including:
- Feature overview
- Configuration options
- System dependencies and installation
- Manual execution examples
- Environment variable options
- Troubleshooting guide
- Future enhancement possibilities

## Job Configuration

| Property | Value |
|----------|-------|
| Job ID | `copilot_metrics_fetch` |
| Job Type | `COPILOT_METRICS_FETCH` (enum) |
| Schedule | Daily at 2:15 AM (cron: `15 2 * * *`) |
| Timeout | 15 minutes |
| Status | ENABLED |
| Registered | Yes - in scheduler |

## Files Modified

1. **requirements.txt**
   - Added: `pyodbc>=5.0.0`

2. **dashboard/backend/app/models/job.py**
   - Added `COPILOT_METRICS_FETCH` to `JobType` enum

3. **dashboard/backend/app/services/scheduler.py**
   - Registered job configuration in `_initialize_jobs()` method
   - Job scheduled with APScheduler

4. **data/scheduler_state.json**
   - Auto-persisted job state with schedule

## Verification

✓ Backend restarted successfully  
✓ Job registered and scheduled  
✓ Job state persisted to disk  
✓ dependencies installed (pyodbc)  
✓ Logs confirm: "Scheduled job copilot_metrics_fetch"

## How to Test

### Local Immediate Execution
```bash
cd /Users/dbsrinivasrao/Desktop/TeamSight
./.venv/bin/python src/copilot_metrics_fetch.py
```

### With Custom Credentials
```bash
COPILOT_DB_PASSWORD="YourPassword" \
  ./.venv/bin/python src/copilot_metrics_fetch.py
```

### View Scheduled Execution Status
```bash
./dashboard/manage.sh logs backend | grep copilot_metrics
```

## Current Features (Enabled)

1. **Connectivity Test**
   - Validates connection to Azure SQL Database
   - Reports server name and database
   - Clear error messages if connection fails

2. **Table Discovery**
   - Lists all tables organized by schema
   - Displays table names and schema information
   - Reports total table count

3. **Copilot Detection**
   - Searches for Copilot-related tables (names containing: copilot, usage, metrics)
   - Lists matching tables with schema
   - Useful for identifying metrics data sources

## Database Configuration Options

### Option 1: Edit Configuration File
```bash
# Edit directly
vim config/copilot_metrics_config.json
```

### Option 2: Environment Variables
```bash
export COPILOT_DB_PASSWORD="secure_password"
export COPILOT_DB_USER="your.email@company.com"
```

### Option 3: Contact Azure SQL Administrator
- Ensure your network IP is in firewall allowlist
- Verify SSL/TLS connectivity is enabled

## Next Steps

### For Initial Testing
1. Run the script manually to verify connectivity
2. Review table discovery output
3. Identify Copilot-related tables for metrics collection

### For Production Deployment
1. Install ODBC drivers on remote Linux server
   ```bash
   apt-get install unixodbc msodbcsql17
   ```
2. Ensure pyodbc is installed in backend venv
3. Verify config file is deployed
4. Monitor first execution at 2:15 AM

### For Future Enhancement
The framework supports:
- SQL query execution and result collection
- CSV/JSON export format
- Integration with KPI system
- Team/developer aggregation

Enable via configuration:
```json
{
  "features": {
    "collect_metrics": true,
    "export_format": "csv"
  }
}
```

## Monitoring

### Check Job Execution History
```bash
cat data/scheduler_state.json | python3 -m json.tool | grep -A 20 copilot_metrics_fetch
```

### View Real-time Logs
```bash
./dashboard/manage.sh follow backend | grep copilot
```

### Verify Job is Registered
```bash
curl -s http://localhost:8000/api/jobs | grep -i copilot
```

## System Requirements

### Python Package
- ✓ pyodbc>=5.0.0 (installed and added to requirements.txt)

### System ODBC Drivers
Required on remote Linux server:
```bash
apt-get install unixodbc msodbcsql17
```

## Directory Structure

```
TeamSight/
├── config/
│   └── copilot_metrics_config.json          (NEW)
├── src/
│   └── copilot_metrics_fetch.py             (NEW)
├── docs/
│   └── COPILOT_METRICS_JOB.md               (NEW)
├── dashboard/backend/app/
│   ├── models/
│   │   └── job.py                           (MODIFIED - added enum)
│   └── services/
│       └── scheduler.py                     (MODIFIED - registered job)
├── requirements.txt                         (MODIFIED - added pyodbc)
└── data/
    └── scheduler_state.json                 (MODIFIED - persisted state)
```

## Support & Troubleshooting

See `docs/COPILOT_METRICS_JOB.md` for:
- Detailed installation instructions by OS
- Connection error troubleshooting
- Performance optimization tips
- Advanced configuration options

---

**Status**: ✓ COMPLETE - Job is registered and scheduled
**First Execution**: Tomorrow at 2:15 AM
**Current State**: Active - waiting for scheduled trigger
