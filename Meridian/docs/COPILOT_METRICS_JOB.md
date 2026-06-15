# Copilot Usage Metrics Collection Job

## Overview

This scheduled job collects GitHub Copilot usage metrics from an Azure SQL Database. The job runs automatically every day at **2:15 AM local time** (cron: `15 2 * * *`).

## Current Features

The initial implementation includes:
- **Database Connectivity Test**: Verifies connection to the Azure SQL Database
- **Table Discovery**: Lists all available tables in the database
- **Copilot Table Detection**: Identifies tables related to Copilot usage metrics
- **Configurable Database Parameters**: All connection parameters can be customized

## Configuration

### Configuration File

Database parameters are stored in `config/copilot_metrics_config.json`:

```json
{
  "database": {
    "server": "metrics-genai.database.windows.net",
    "port": 1433,
    "database": "metrics-genai",
    "user": "srinivas.rao@metrics-genai",
    "password": "StrongPassword@123!",
    "encrypt": true,
    "trustServerCertificate": false,
    "hostNameInCertificate": "*.database.windows.net",
    "loginTimeout": 30
  },
  "schedule": {
    "enabled": true,
    "cron_expression": "15 2 * * *",
    "description": "Daily at 2:15 AM local time"
  },
  "features": {
    "test_connectivity": true,
    "list_tables": true,
    "collect_metrics": false,
    "export_format": "csv"
  }
}
```

### Environment Variable Overrides

All database parameters can be overridden via environment variables:

| Environment Variable | Config Key | Example |
|----------------------|-----------|---------|
| `COPILOT_DB_SERVER` | `database.server` | `metrics-genai.database.windows.net` |
| `COPILOT_DB_PORT` | `database.port` | `1433` |
| `COPILOT_DB_NAME` | `database.database` | `metrics-genai` |
| `COPILOT_DB_USER` | `database.user` | `srinivas.rao@metrics-genai` |
| `COPILOT_DB_PASSWORD` | `database.password` | `StrongPassword@123!` |

Example:
```bash
export COPILOT_DB_PASSWORD="MySecurePassword123!"
export COPILOT_DB_USER="my.email@company.com"
python src/copilot_metrics_fetch.py
```

## Installation Requirements

### System Dependencies

The job requires ODBC drivers to connect to SQL Server:

**macOS:**
```bash
brew install unixodbc msodbcsql17
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install unixodbc msodbcsql17
```

**Windows:**
- Download and install [ODBC Driver 17 for SQL Server](https://www.microsoft.com/en-us/download/details.aspx?id=56567)

### Python Packages

The required Python packages are listed in `requirements.txt`:
```
pyodbc>=5.0.0
```

Install with:
```bash
pip install -r requirements.txt
```

## Manual Execution

### Quick Test
```bash
cd /path/to/TeamSight
source .venv/bin/activate  # or use your venv activation
python src/copilot_metrics_fetch.py
```

### With Environment Overrides
```bash
COPILOT_DB_PASSWORD="your_password" python src/copilot_metrics_fetch.py
```

### From Backend Venv
```bash
cd /path/to/TeamSight/dashboard/backend
source venv/bin/activate
python ../../src/copilot_metrics_fetch.py
```

## Scheduled Execution

The job is automatically scheduled in the dashboard scheduler service. View status and logs:

```bash
# Check if job is scheduled
curl http://localhost:8000/api/jobs/copilot_metrics_fetch

# View recent job executions
curl http://localhost:8000/api/jobs/list

# View logs
tail -f dashboard/logs/backend.log | grep copilot_metrics_fetch
```

## Configuration Changes

Changes to database parameters take effect immediately on the next job execution:

1. Edit `config/copilot_metrics_config.json`
2. Backend automatically reloads configuration
3. Next scheduled run (2:15 AM) uses new parameters

**Note**: If you change database credentials frequently, use environment variables instead of editing the config file.

## Output

The job produces console output in the backend logs showing:

```
======================================================================
Copilot Metrics Collection Configuration
======================================================================
Server: metrics-genai.database.windows.net
Port: 1433
Database: metrics-genai
User: srinivas.rao@metrics-genai
Encrypt: True
Schedule: Daily at 2:15 AM local time
Test Connectivity: True
List Tables: True
Collect Metrics: False
======================================================================
Testing database connectivity...
✓ Successfully connected to database
  Server: metrics-genai.database.windows.net
  Database: metrics-genai
Retrieving available tables...
✓ Found 45 tables
[dbo]
  - AspNetRoleClaims
  - AspNetRoles
  - AspNetUserClaims
  ...
[metrics]
  - CopilotUsage
  - CopilotAcceptance
  - ...

Searching for Copilot-related tables...
✓ Found 3 Copilot-related tables:
  - metrics.CopilotUsage
  - metrics.CopilotAcceptance
  - metrics.CopilotMetricsDaily
  
======================================================================
Execution completed successfully in 5.23 seconds
======================================================================
```

## Future Enhancements

The framework supports extending this job with additional features:

1. **Metrics Collection** (`collect_metrics: true`):
   - Query Copilot usage tables
   - Transform and aggregate data
   - Generate weekly/monthly reports

2. **Data Export** (`export_format: csv|json`):
   - Export metrics to files in `output/` directory
   - Generate timestamped backup files

3. **Advanced Queries**:
   - Filter by date ranges
   - Aggregate by developer/team
   - Calculate KPIs from raw metrics

4. **Integration with KPI System**:
   - Create dedicated KPI script (`src/kpp_kXXX.py`) for Copilot metrics
   - Register in `KppEvaluator.py`
   - Add to `config/Roles.csv`

### Adding Metrics Collection

To enable metrics collection:

1. Edit `config/copilot_metrics_config.json`:
   ```json
   {
     "features": {
       "collect_metrics": true,
       "export_format": "csv"
     }
   }
   ```

2. Modify `src/copilot_metrics_fetch.py` - add metrics query logic in the `run()` method

3. Extend the SQL queries to extract developer usage data

## Troubleshooting

### Connection Errors

**Error**: `Connection failed (Operational): ...`
- Verify network connectivity to `metrics-genai.database.windows.net`
- Check if Azure SQL firewall rules allow your IP
- Verify credentials in `config/copilot_metrics_config.json`

**Error**: `ODBC drivers not found`
- Install required ODBC drivers (see Installation Requirements section)
- Verify installation: `odbcinst -j` on Linux/macOS

### Performance Issues

If the job takes longer than 15 minutes:
- Check network latency to database
- Verify database is responding normally
- Profile table queries in Azure portal

### Job Not Running

Check scheduler status:
```bash
# View job configuration
curl http://localhost:8000/api/jobs/copilot_metrics_fetch

# Check if scheduler is running
curl http://localhost:8000/api/health
```

## Related Files

- **Script**: `src/copilot_metrics_fetch.py`
- **Configuration**: `config/copilot_metrics_config.json`
- **Scheduler Integration**: `dashboard/backend/app/services/scheduler.py`
- **Job Models**: `dashboard/backend/app/models/job.py`
- **Logs**: `dashboard/logs/backend.log`

## Job Details

| Property | Value |
|----------|-------|
| Job ID | `copilot_metrics_fetch` |
| Job Type | `copilot_metrics_fetch` |
| Schedule | Daily at 2:15 AM (`15 2 * * *`) |
| Timeout | 15 minutes |
| Enabled | Yes (by default) |

## Disabling the Job

To temporarily disable the job without removing it:

1. Edit `config/copilot_metrics_config.json`:
   ```json
   {
     "schedule": {
       "enabled": false,
       ...
     }
   }
   ```

2. Or via API endpoint (when implemented):
   ```bash
   curl -X POST http://localhost:8000/api/jobs/copilot_metrics_fetch/disable
   ```

## Support

For issues or enhancements:
1. Check the troubleshooting section above
2. Review logs in `dashboard/logs/backend.log`
3. Verify configuration in `config/copilot_metrics_config.json`
4. Test connectivity manually with: `python src/copilot_metrics_fetch.py`
