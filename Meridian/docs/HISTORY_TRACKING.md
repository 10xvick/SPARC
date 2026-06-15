# JIRA History Tracking - Implementation Guide

## Overview

This implementation adds comprehensive changelog tracking to capture state changes, assignee changes, and sprint changes for all JIRA issues. This data enables advanced analytics including bug cycle time analysis and replan tracking.

## What Was Implemented

### 1. **Enhanced JIRA Fetch Script** ([jira_fetch.py](../src/jira_fetch.py))

**New Features:**
- ✅ **Changelog Expansion**: API requests now include `expand=changelog` to fetch complete change history
- ✅ **History Parsing**: New `parse_changelog()` method extracts:
  - Status transitions (state changes)
  - Assignee changes
  - Sprint changes (replanning events)
  - Priority changes
- ✅ **Duplicate Prevention**: Tracks unique history entries to avoid duplicates
- ✅ **Incremental Updates**: History data is appended on subsequent runs

**New Files Generated:**
- `output/JIRAIssues_History.csv` - Complete changelog for all tracked fields

**History CSV Columns:**
```
Key | ChangeDate | ChangeType | Field | FromValue | ToValue | Author | IssueType | Priority
```

### 2. **Bug Cycle Time Analysis** ([kpp_bug_cycle_time.py](../src/kpp_bug_cycle_time.py))

Calculates comprehensive cycle time metrics for bugs:

**Metrics Calculated:**
- ⏱️ **Time in Each Status**: Hours spent in New, In Progress, Code Review, Testing, Done, etc.
- 📊 **Total Cycle Time**: From creation to resolution (in days and hours)
- 🔄 **Rework Count**: Number of times a bug returned to a previous status
- 📈 **Transition Count**: Total number of status changes
- 📉 **Summary Statistics**: By priority (mean, median, min, max)

**Output Files:**
- `output/bug_cycle_time.csv` - Detailed cycle time for each bug
- `output/bug_cycle_time_summary.csv` - Aggregated statistics by priority

**Sample Output:**
```
Key       | Priority | Total_Cycle_Time_Days | Rework_Count | Time_in_In_Progress_Hours
-----------------------------------------------------------------------------------------------
AS-123    | High     | 5.2                   | 1            | 32.5
AS-124    | Medium   | 12.8                  | 0            | 18.3
```

### 3. **Replan Tracker Analysis** ([kpp_replan_tracker.py](../src/kpp_replan_tracker.py))

Tracks sprint changes and replanning for Stories and Epics:

**Metrics Calculated:**
- 🔀 **Replan Count**: Number of times an issue was moved between sprints
- 📅 **Sprint Timeline**: Complete history of sprint changes with dates
- 🎯 **Total Sprints**: Unique sprints an issue has been in
- 📊 **Replan Rate**: Percentage of issues that were replanned
- ⚠️ **High Replan Issues**: Issues with >= 3 replans (configurable threshold)

**Output Files:**
- `output/replan_tracker.csv` - Detailed replan data for each Story/Epic/Task
- `output/replan_tracker_summary.csv` - Summary by issue type
- `output/replan_tracker_by_priority.csv` - Breakdown by priority
- `output/replan_tracker_high_replan.csv` - High replan issues

**Sample Output:**
```
Key     | Issue_Type | Replan_Count | Sprint_Timeline
-----------------------------------------------------------------
AS-456  | Story      | 4            | Sprint 1 → Sprint 2 → Sprint 3 → Sprint 5
FH-789  | Epic       | 2            | Sprint 4 → Sprint 6
```

### 4. **Configuration Update** ([jira_config.json](../config/jira_config.json))

Added new configuration parameter:
```json
"historyFile": "output/JIRAIssues_History.csv"
```

## How to Use

### Step 1: Fetch JIRA Data with History

Run the fetch script to collect current issue data AND complete changelog history:

```bash
python src/jira_fetch.py --fetch
```

This will generate:
- `output/JIRAIssues.csv` - Current state of all issues
- `output/JIRAIssues_History.csv` - Complete change history

**Note:** First run may take longer due to changelog fetching. Subsequent runs are incremental.

### Step 2: Analyze Bug Cycle Times

Run the cycle time analysis:

```bash
python src/kpp_bug_cycle_time.py
```

**Output:**
- Detailed cycle times per bug
- Summary statistics by priority
- Top 10 longest cycle times

### Step 3: Analyze Replanning

Run the replan tracker:

```bash
python src/kpp_replan_tracker.py
```

**Output:**
- Replan counts per Story/Epic/Task
- Replan breakdown by priority
- High replan issues (>= 3 replans)
- Overall replan rate

### Step 4: Reset (if needed)

To start fresh and remove all data including history:

```bash
python src/jira_fetch.py --reset
```

This removes:
- `output/JIRAIssues.csv`
- `output/JIRAIssues_History.csv`
- `data/jira_fetch_checkpoint.json`

## Understanding the Data

### Status Transitions (Bug Cycle Time)

The history data captures every status change:

```
AS-123 | 2026-01-15 10:30 | status | New          | In Progress | john.doe
AS-123 | 2026-01-20 14:00 | status | In Progress  | Code Review | jane.smith
AS-123 | 2026-01-22 09:15 | status | Code Review  | In Progress | john.doe  (REWORK!)
AS-123 | 2026-01-25 16:00 | status | In Progress  | Done        | jane.smith
```

**Insights:**
- Time in each status = difference between consecutive timestamps
- Rework = returning to a previously visited status
- Total cycle time = first transition to last transition

### Sprint Changes (Replan Tracking)

The history data captures every sprint change:

```
AS-456 | 2026-01-10 | sprint | -        | Sprint 1 | pm.user
AS-456 | 2026-01-25 | sprint | Sprint 1 | Sprint 2 | pm.user  (REPLAN!)
AS-456 | 2026-02-08 | sprint | Sprint 2 | Sprint 3 | pm.user  (REPLAN!)
```

**Insights:**
- Each sprint change = 1 replan
- Multiple replans indicate scope/priority changes
- Can correlate with priority changes for root cause analysis

### Assignee Changes

Track who worked on what and when:

```
AS-123 | 2026-01-15 | assignee | -           | john.doe   | pm.user
AS-123 | 2026-01-20 | assignee | john.doe    | jane.smith | pm.user
```

**Use Cases:**
- Handoff frequency analysis
- Workload distribution
- Bottleneck identification

## Advanced Analysis Examples

### Example 1: Calculate Average Cycle Time by Status

```python
import pandas as pd

history = pd.read_csv('output/JIRAIssues_History.csv')
status_changes = history[history['Field'] == 'status']

# Group by status and calculate average time
# (requires additional timestamp calculations)
```

### Example 2: Identify Sprint Instability

```python
import pandas as pd

replan_data = pd.read_csv('output/replan_tracker.csv')

# Find sprints with most replanned items
unstable_sprints = replan_data.groupby('Final_Sprint')['Replan_Count'].sum().sort_values(ascending=False)
print("Most unstable sprints:", unstable_sprints.head(10))
```

### Example 3: Correlation Between Priority Changes and Replans

```python
import pandas as pd

history = pd.read_csv('output/JIRAIssues_History.csv')
priority_changes = history[history['Field'] == 'priority']
sprint_changes = history[history['Field'] == 'Sprint']

# Analyze issues with both priority and sprint changes
# (join on Key and compare dates)
```

## Performance Considerations

### Initial Fetch
- **With changelog**: Slower first run (may take several minutes for large projects)
- **API rate limits**: JIRA API may throttle requests; script includes retry logic

### Incremental Updates
- Only fetches changes since last update
- History entries are deduplicated automatically
- Checkpoint system prevents data loss

### Data Volume
- History file grows with each change
- Consider archiving old history data periodically
- Use date filters in analysis scripts for recent data

## Troubleshooting

### Issue: No history data generated

**Solution:**
1. Check that `expand=changelog` is in the API request
2. Verify JIRA permissions allow changelog access
3. Ensure issues have actual history (newly created issues may have minimal history)

### Issue: Duplicate history entries

**Solution:**
- History deduplication is automatic via unique keys
- If duplicates persist, use `--reset` flag and re-fetch

### Issue: Analysis scripts show "No data"

**Solution:**
1. Verify history CSV exists: `ls -la output/JIRAIssues_History.csv`
2. Check issue types: Bug cycle time only analyzes Bugs
3. Check replan tracker: Only analyzes Stories/Epics/Tasks

### Issue: Cycle times seem incorrect

**Solution:**
- Verify timezone handling in JIRA timestamps
- Check for missing status transitions
- Ensure Created date is accurate in issues CSV

## Future Enhancements

Potential additions:
- 📊 **Assignee Flow Analysis**: Track workload distribution and handoffs
- 📈 **Status Flow Diagrams**: Visualize common paths through workflow
- ⚠️ **Bottleneck Detection**: Identify statuses with longest wait times
- 🎯 **Sprint Velocity Impact**: Correlate replans with velocity
- 📉 **Trend Analysis**: Track cycle time trends over time

## API Reference

### JIRA API Fields Used

**Changelog Fields:**
- `changelog.histories[].created` - When change occurred
- `changelog.histories[].author` - Who made the change
- `changelog.histories[].items[].field` - Field that changed
- `changelog.histories[].items[].fromString` - Previous value
- `changelog.histories[].items[].toString` - New value

**Tracked Fields:**
- `status` - Status transitions
- `assignee` - Assignee changes
- `Sprint` - Sprint changes (custom field)
- `priority` - Priority changes

## Support

For questions or issues:
1. Check this documentation
2. Review the code comments in source files
3. Verify JIRA API permissions and configuration
4. Check output files for error messages

---

**Last Updated:** March 2026  
**Version:** 1.0
