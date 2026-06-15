# TeamSight

Python scripts to fetch commit details from GitHub Enterprise repositories and JIRA issues.

## Contents

- [GitHub Commits Fetcher](#github-commits-fetcher)
- [JIRA Issues Fetcher](#jira-issues-fetcher)

---

## GitHub Commits Fetcher

Python script to fetch commit details from GitHub Enterprise repositories with support for per-repository configuration.

### Features

✅ Fetch commits from multiple repositories
✅ Per-repository GitHub token and API URL support
✅ Filter commits by date range
✅ Export to CSV, Excel, or Google Sheets
✅ List all accessible repositories
✅ Test API connection
✅ Checkpoint-based resumption

## Installation

1. Install required packages:
```bash
pip install -r requirements.txt

# Optional: For Excel export
pip install pandas openpyxl

# Optional: For Google Sheets export
pip install gspread oauth2client
```

## Configuration

The script uses a configuration file (`github_config.json`) to manage settings for multiple repositories.

### Configuration File Structure

Create `github_config.json`:

```json
{
  "default": {
    "githubToken": "your_github_token",
    "githubApiBaseUrl": "https://github01.hclpnp.com/api/v3"
  },
  "repositories": {
    "owner/repo1": {},
    "owner/repo2": {
      "githubToken": "different_token",
      "githubApiBaseUrl": "https://github.com/api/v3"
    },
    "owner/repo3": {}
  },
  "outputFile": "github_commits.csv",
  "exportFormat": "csv"
}
```

**Configuration Hierarchy:**
1. Repository-specific settings (highest priority)
2. Default settings in config file
3. Environment variables / built-in defaults (lowest priority)

### Getting a GitHub Personal Access Token

1. Go to https://github01.hclpnp.com/settings/tokens
2. Click "Generate new token" (classic)
3. Give it a name and select scopes: `repo` (Full control of private repositories)
4. Click "Generate token" and copy it
5. Paste it in the `GITHUB_TOKEN` variable

## Usage

### Test Connection
```bash
python github_fetch.py test
```

### List All Accessible Repositories
```bash
python github_fetch.py list
```
This will show all repositories you have access to and save them to `accessible_repositories.json`

### Fetch All Commits
```bash
python github_fetch.py fetch
```
Fetches commits from all repositories in REPOSITORY_LIST and exports to the configured format.

### Fetch Recent Commits
```bash
# Last 7 days (default)
python github_fetch.py recent

# Last 14 days
python github_fetch.py recent 14

# Last 30 days
python github_fetch.py recent 30
```

## Export Formats

### CSV (Default)
- No additional dependencies
- Outputs to `github_commits.csv`
- Easy to open in Excel, Google Sheets, or any text editor

### Excel
- Requires: `pip install pandas openpyxl`
- Outputs to `github_commits.xlsx`
- Better formatting and compatibility with Microsoft Excel

### Google Sheets
- Requires: `pip install gspread oauth2client`
- Requires Google Cloud credentials (see below)
- Automatically creates/updates a Google Sheet

#### Setting up Google Sheets Export

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google Sheets API and Google Drive API
4. Create Service Account credentials:
   - Go to "Credentials" → "Create Credentials" → "Service Account"
   - Download the JSON key file
   - Save it as `google_credentials.json` in the same directory as the script
5. Share your Google Sheet with the service account email (found in the JSON file)

## Examples

```bash
# Quick start
python github_fetch.py test
python github_fetch.py list
python github_fetch.py fetch

# Get recent activity
python github_fetch.py recent 7

# Export to Excel instead of CSV
# (Edit EXPORT_FORMAT = 'excel' in the script first)
python github_fetch.py fetch
```

## Output Files

- `github_commits.csv` - Commit data in CSV format
- `github_commits.xlsx` - Commit data in Excel format (if using Excel export)
- `accessible_repositories.json` - List of all accessible repositories
- `recent_commits_Ndays.csv` - Recent commits from last N days

## Scheduling

### Linux/Mac (cron)
```bash
# Edit crontab
crontab -e

# Run every day at 9 AM
0 9 * * * cd /path/to/script && python github_fetch.py fetch

# Run every Monday at 8 AM
0 8 * * 1 cd /path/to/script && python github_fetch.py recent 7
```

### Windows (Task Scheduler)
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (daily, weekly, etc.)
4. Action: Start a program
   - Program: `python`
   - Arguments: `C:\path\to\github_fetch.py fetch`
   - Start in: `C:\path\to\`

## Troubleshooting

**Connection refused / Timeout**
- Check if you can access https://github01.hclpnp.com from your machine
- Verify the API base URL is correct
- Check if you need to be on VPN

**401 Unauthorized**
- Verify your GitHub token is correct and not expired
- Check token has `repo` scope permissions

**404 Not Found**
- Verify repository owner and name are correct
- Check if you have access to the repository

**Rate Limiting**
- GitHub Enterprise typically has higher rate limits than github.com
- Add delays between requests if needed
- Check your rate limit: `curl -H "Authorization: Bearer YOUR_TOKEN" https://github01.hclpnp.com/api/v3/rate_limit`

## Features

✅ Fetch commits from multiple repositories
✅ Filter commits by date range
✅ Export to CSV, Excel, or Google Sheets
✅ List all accessible repositories
✅ Test API connection

---

## JIRA Issues Fetcher

Python script to fetch JIRA issues from multiple projects with support for incremental updates, per-project configuration, and checkpoint-based resumption.

### Features

✅ Fetch issues from multiple JIRA projects
✅ Per-project JIRA server and credentials support
✅ Incremental updates - only fetches changed issues
✅ Checkpoint-based resumption - resume from where it stopped
✅ Filter issues by update date (cutoff date)
✅ Export to CSV with automatic de-duplication
✅ Command-line argument support for flexibility

### Installation

```bash
pip install -r requirements.txt
```

Required packages:
- `requests>=2.31.0`

### Configuration

The script uses a configuration file (`jira_config.json`) to manage settings for multiple projects.

#### Configuration File Structure

Create `jira_config.json`:

```json
{
  "default": {
    "jiraServer": "https://your-jira-server.atlassian.net",
    "userId": "your-email@example.com",
    "apiToken": "your-jira-api-token",
    "maxResults": 50,
    "cutoffDate": "2025-03-31"
  },
  "projects": {
    "PROJECT1": {},
    "PROJECT2": {
      "jiraServer": "https://different-server.atlassian.net",
      "userId": "different-email@example.com",
      "apiToken": "different-api-token"
    },
    "PROJECT3": {}
  },
  "outputFile": "JIRAIssues.csv",
  "checkpointFile": "jira_fetch_checkpoint.json"
}
```

**Configuration Hierarchy:**
1. Command-line arguments (highest priority)
2. Project-specific settings in config file
3. Default settings in config file
4. Built-in defaults (lowest priority)

#### Getting a JIRA API Token

1. Log in to your JIRA account
2. Go to Account Settings → Security
3. Create and manage API tokens
4. Click "Create API token"
5. Give it a name and copy the generated token
6. Use your email as `userId` and the token as `apiToken`

### Usage

#### Basic Commands

```bash
# Show help
python jira_fetch.py --help

# Fetch JIRA issues (uses jira_config.json)
python jira_fetch.py --fetch

# Reset data (clears CSV and checkpoint files)
python jira_fetch.py --reset
```

#### Advanced Options

```bash
# Use custom configuration file
python jira_fetch.py --fetch configFile=custom_config.json

# Override output file
python jira_fetch.py --fetch outputFile=MyJIRA.csv

# Override specific projects
python jira_fetch.py --fetch projects=PROJECT1,PROJECT2,PROJECT3

# Override cutoff date
python jira_fetch.py --fetch cutoffDate=2025-01-01

# Override max results per request
python jira_fetch.py --fetch maxResults=100

# Combine multiple overrides
python jira_fetch.py --fetch outputFile=custom.csv projects=FH,HR maxResults=75
```

### How It Works

1. **Initialization**: Loads existing CSV data and checkpoint file
2. **Per-Project Fetching**: 
   - Uses project-specific JIRA server and credentials if configured
   - Falls back to default settings if not specified
   - Fetches issues in batches (pagination)
3. **Incremental Updates**:
   - Existing issues are updated if they changed
   - New issues are added only if updated after cutoff date
   - No duplicates - JIRA ID is unique key
4. **Checkpoint Management**:
   - Saves progress after each batch
   - Stores per-project pagination tokens
   - Can resume if interrupted
5. **CSV Export**: Writes complete data to CSV file

### Output Format

CSV file with columns:
- Issue Type
- Key (JIRA ID)
- Components
- Parent
- Priority
- Status
- Story Points
- Assignee
- Summary
- Time Spent
- Customers
- Labels
- Updated
- Updated by
- Created
- Sprint.endDate
- Reporter
- Linked Issues
- Sprint

### Checkpoint System

The script maintains a checkpoint file (`jira_fetch_checkpoint.json`) that stores:
- Current project being processed
- Pagination tokens for each project
- Allows resumption from exact point of interruption

Example checkpoint:
```json
{
  "currentProjectIndex": 2,
  "projectTokens": {
    "PROJECT1": "",
    "PROJECT2": "",
    "PROJECT3": "EJYBGPSDoMvLMyI9cHJvamVjdD0..."
  }
}
```

### Per-Project Configuration Examples

#### Single JIRA Server (All Projects)
```json
{
  "default": {
    "jiraServer": "https://company.atlassian.net",
    "userId": "user@company.com",
    "apiToken": "token123"
  },
  "projects": {
    "FH": {},
    "HR": {},
    "PCS": {}
  }
}
```

#### Multiple JIRA Servers
```json
{
  "default": {
    "jiraServer": "https://main-jira.atlassian.net",
    "userId": "user@company.com",
    "apiToken": "token123"
  },
  "projects": {
    "PROJECT1": {},
    "PROJECT2": {},
    "PROJECT3": {
      "jiraServer": "https://legacy-jira.company.com",
      "userId": "legacy-user@company.com",
      "apiToken": "legacy-token456"
    }
  }
}
```

### Troubleshooting

**No data fetched / 0 rows**
- Check if issues were updated after the cutoff date
- Verify project keys are correct
- Ensure API token has proper permissions

**Authentication errors (400/401)**
- Verify JIRA server URL is correct
- Check userId (email) and apiToken are valid
- Ensure API token hasn't expired

**Reserved JQL word error (e.g., "AS")**
- Already handled - project names are automatically quoted in JQL queries

**Script stops/interrupted**
- Safe to restart - will resume from checkpoint
- Data is saved incrementally after each batch

**Rate limiting**
- Script includes 10-second delays on errors
- Adjust with timeout settings if needed

### Automation

#### Linux/Mac (cron)
```bash
# Edit crontab
crontab -e

# Run daily at 2 AM
0 2 * * * cd /path/to/TeamSight && ./.venv/bin/python src/jira_fetch.py --fetch

# Run every 6 hours
0 */6 * * * cd /path/to/TeamSight && ./.venv/bin/python src/jira_fetch.py --fetch
```

#### Windows (Task Scheduler)
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (daily, weekly, etc.)
4. Action: Start a program
   - Program: `python`
  - Arguments: `src\jira_fetch.py --fetch`
  - Start in: `C:\path\to\TeamSight`

### Migration from Google Apps Script

This Python script replicates the functionality of the `JIRAIssuesRawAPIdata.gs` Apps Script:
- ✅ Incremental updates (updates existing rows)
- ✅ State management (checkpoint file vs Script Properties)
- ✅ Pagination support (nextPageToken)
- ✅ Per-project processing with resumption
- ✅ Same output format and headers
- ✅ Reset functionality

## License

This project is for internal use.
✅ Detailed error messages
✅ Progress indicators
✅ Works with GitHub Enterprise

## API Rate Limits

GitHub Enterprise typically allows:
- 5,000 requests per hour for authenticated users
- The script shows progress and handles errors gracefully
- Rate limit resets every hour

---

## KPI Evaluator (k3 Function)

Python module to aggregate story points completed per employee with support for multiple time period aggregations.

### Features

✅ Aggregates story points from completed JIRA issues
✅ Maps JIRA assignees to employee data using Resources.csv
✅ Multiple time period aggregations:
  - **Weekly**: Year and week number (e.g., 202601, 202612)
  - **Monthly**: Month and year (e.g., Feb2026, Mar2026)
  - **Quarterly**: Quarter abbreviation and year (e.g., JFM2026, AMJ2026, JAS2026, OND2026)
  - **Annual**: Fiscal year based on configurable start month (default: April)
✅ Append/override logic - updates existing entries for the same date and employee
✅ Exports to CSV format

### Configuration

The KppEvaluator requires:
- **Resources.csv**: Employee configuration with SAPID, Name, and JIRA Name mapping
- **JIRAIssues.csv**: JIRA issues data with Story Points and completion status
- **Output directory**: Where k3.csv will be created/updated

### Usage

#### As a Standalone Script
```bash
python src/KppEvaluator.py
```

This will:
1. Read Resources.csv from `config/` directory
2. Read JIRAIssues.csv from `output/` directory
3. Generate/update k3.csv in `output/` directory
4. Use current date for reporting

#### As a Python Module
```python
from KppEvaluator import KppEvaluator
from datetime import date

# Create evaluator instance
evaluator = KppEvaluator(
    resources_file='config/Resources.csv',
    jira_issues_file='output/JIRAIssues.csv',
    output_dir='output',
    fiscal_start_month=4  # April (default)
)

# Run k3 function with current date
evaluator.k3()

# Or run with a specific date
evaluator.k3(current_date=date(2026, 3, 5))
```

### Output Format

The k3.csv file contains the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| CurrentDate | Date of report generation (YYYYMMDD) | 20260305 |
| Week | Current week number (YYYYWW) | 202610 |
| Month | Current month (MonYYYY) | Mar2026 |
| Quarter | Current quarter (QQQYYYY) | JFM2026 |
| Year | Current fiscal year | FY2025 |
| SAPID | Employee SAP ID | 52347348.0 |
| Name | Employee name | Lalit Adelu Sharlawar |
| Weekly | Story points completed in current week | 7.0 |
| Monthly | Story points completed in current month | 7.0 |
| Quarterly | Story points completed in current quarter | 6.0 |
| Annual | Story points completed in current fiscal year | 6.0 |

**Note:** The Weekly, Monthly, Quarterly, and Annual columns show only the story points for the **current** time period (based on CurrentDate), not all-time totals.

### Quarter Abbreviations

- **JFM**: January, February, March (Q1)
- **AMJ**: April, May, June (Q2)
- **JAS**: July, August, September (Q3)
- **OND**: October, November, December (Q4)

### Fiscal Year

The fiscal year is calculated based on the `fiscal_start_month` parameter (default: April):
- If the current month >= fiscal start month: FY = current year
- If the current month < fiscal start month: FY = current year - 1

Example with April as fiscal start:
- March 2026 → FY2025
- April 2026 → FY2026

### Append/Override Behavior

When running k3() multiple times:
- If an entry exists for the same **CurrentDate** and **SAPID**, it will be **overridden**
- Entries with different dates or employee IDs will be **preserved**
- This allows daily updates without duplicating data

### Example Workflow

1. Fetch JIRA issues:
   ```bash
   python src/jira_fetch.py -f
   ```

2. Run KPI evaluation:
   ```bash
   python src/KppEvaluator.py
   ```

3. View the output:
   ```bash
   cat output/k3.csv
   ```

---

## Adding a New KPI (Implementation Checklist)

Use this checklist whenever adding a new KPI (example: `k301` DAST Gating Issues).

### 1) Choose KPI ID and role mapping

- Add a new row in `config/Roles.csv` with:
  - `Index` (new KPI ID, e.g., `k301`)
  - `Role` (or `All` if KPI applies to everyone)
  - `KPP Goals`, `Measurement Criteria`, `Tool`, `Measure`
  - `Type` / `Aggregation Type`
  - `Weekly Target`, `Quarterly Target`, `Annual Target`
  - `Goal Type`

### 2) Create KPI implementation script

- Add new file: `src/kpp_k<id>.py`
- Follow existing output schema exactly:
  - `CurrentDate, Week, Month, Quarter, Year, SAPID, Name, Weekly, Monthly, Quarterly, Annual`
- Keep output file format stable: `output/k<id>-data.csv`

### 3) Register KPI in orchestrator

Update `src/KppEvaluator.py`:

- Add import: `from kpp_k<id> import k<id>`
- Add function entry in `self.kpi_functions`
- Add dispatch branch in `run_kpi()` for required inputs
  - JIRA-based KPIs
  - GitHub-based KPIs
  - Mixed/custom-source KPIs

### 4) Validate and execute

- Run standalone KPI script once (sanity check)
- Run `KppEvaluator` for the KPI
- Confirm CSV is generated in `output/`
- Restart backend after `Roles.csv` / `KppEvaluator.py` changes:
  - `./dashboard/manage.sh restart backend`

---

## Team-Level KPI Handling (Required Pattern)

Use this pattern for any KPI whose value is computed at team level but must be assigned to members.

### Mapping and aggregation rules

1. Compute score per source unit (for example, per scan project).
2. Map source units to team(s) through configuration (do not hardcode in script).
3. If multiple source units map to one team, aggregate using the KPI rule (for k301: **sum**).
4. Assign the same team score to every member whose `Team` in `Resources.csv` matches.

### Period value rules

- `Weekly`: current run’s team-level computed value.
- `Monthly/Quarterly/Annual`: use median of weekly KPI values within:
  - current month,
  - current quarter,
  - current fiscal year.

### Team-level KPI files to add/modify

Required files:

- Add: `src/kpp_k<id>.py`
- Modify: `src/KppEvaluator.py`
- Modify: `config/Roles.csv`

Optional (if KPI depends on configurable source-to-team mapping):

- Add/Modify: `config/<kpi_source_config>.json` (example: `config/security_scan_config.json`)

Optional (if onboarding UI/API must manage mapping):

- Modify: `dashboard/backend/app/api/project_config.py`
- Modify: `dashboard/frontend/src/pages/ProjectOnboardingPage.tsx`

---

## Team-Level Security Gating KPIs (k301, k302, k303, k304)

Four scan-driven team-level KPIs are implemented using the same architecture and period logic:

- `k301` — **DAST Gating Issues**
  - Source: `output/scans/dast/*.html`
  - Parser input: **Summary of security issues** section
  - Metric: `High + Medium` only (Low/Informational ignored)
  - Team mapping: `config/security_scan_config.json` → `projects[].teams`
  - Aggregation when multiple projects map to one team: **sum**

- `k302` — **SAST Gating Issues**
  - Source: `output/scans/sast/*.html`
  - Parser input: **Summary of security issues** section
  - Metric: `High + Medium` only (Low/Informational ignored)
  - Team mapping: `config/security_scan_config.json` → `projects[].teams`
  - Aggregation when multiple projects map to one team: **sum**

- `k303` — **SCA Gating Issues**
  - Source: `output/scans/sca/*.html`
  - Parser input: **Summary of security issues** section
  - Metric: `High + Medium` only (Critical/Low/Informational ignored)
  - Team mapping: `config/security_scan_config.json` → `projects[].teams`
  - Aggregation when multiple projects map to one team: **sum**

- `k304` — **MEND Gating Issues**
  - Source: `output/scans/mend/*.pdf`
  - Parser input: Mend PDF Severity Distribution (`Critical`, `High`, `Med`, `Low`)
  - Metric: `High + Medium` only (Critical/Low ignored)
  - Team mapping: `config/security_scan_config.json` → `projects[].teams`
  - Aggregation when multiple projects map to one team: **sum**

### Shared output behavior

- Output files:
  - `output/k301-data.csv`
  - `output/k302-data.csv`
  - `output/k303-data.csv`
  - `output/k304-data.csv`
- Member assignment: all members in the mapped team receive the same team score.
- Period values:
  - `Weekly`: current run score.
  - `Monthly/Quarterly/Annual`: median of weekly values within current month/quarter/fiscal year.

### Role definitions

- KPI definitions live in `config/Roles.csv` with:
  - `k301` (DAST Gating Issues)
  - `k302` (SAST Gating Issues)
  - `k303` (SCA Gating Issues)
  - `k304` (MEND Gating Issues)
  - `Type=NL`, `Aggregation Type=ANL`, targets as configured in Roles.
