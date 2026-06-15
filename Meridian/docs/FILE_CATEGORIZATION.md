# File Categorization Guide

## Overview

The GitHub fetch now generates two CSV files:
1. **github_commits.csv** - Commit-level data (unchanged)
2. **github_commit_files.csv** - File-level details with categorization

## File Categories

### UI/Frontend Categories:

#### 1. **ui_screen** (is_screen=True)
**High-confidence screen files:**
- Files in `/screens/`, `/pages/`, `/views/` folders
- Files ending with: `*Screen.jsx`, `*Page.tsx`, `*View.swift`, `*Activity.java`, `*Fragment.kt`
- Android layouts: `res/layout/*.xml`
- iOS UI: `*.storyboard`, `*.xib`

**Medium-confidence screen files:**
- Frontend files (`.jsx`, `.tsx`, `.vue`) with screen-like names
- Contains "screen", "page", or "view" in filename
- NOT in `/components/` folder

#### 2. **ui_component** (is_screen=False)
Frontend components:
- `.jsx`, `.tsx`, `.vue`, `.dart`, `.svelte` files
- In `/components/`, `/widgets/`, `/ui/` folders
- Shared/reusable UI elements (Button, Modal, etc.)

#### 3. **ui_style** (is_screen=False)
Stylesheets counting as UI work:
- `.css`, `.scss`, `.sass`, `.less`, `.styl`
- In `/screens/`, `/pages/`, `/components/`, `/ui/` folders

### Other Categories:

- **backend**: Server-side code (`.py`, `.java`, `.go`, etc.) or in `/api/`, `/services/`
- **test**: Files in test folders or with `.test.`, `.spec.` in name (EXCLUDED)
- **config**: Configuration files (`.json`, `.yaml`, `.xml`)
- **documentation**: Documentation files (`.md`, `.txt`)
- **excluded**: Build artifacts, node_modules, dist folders
- **other**: Everything else

## CSV Structure

### github_commit_files.csv columns:

| Column | Description |
|--------|-------------|
| commit_sha | Git commit hash |
| date | Commit date |
| author | Author name |
| author_email | Author email |
| repository | Repository name (owner/repo) |
| jira_id | Linked JIRA issue IDs |
| filename | Base filename (e.g., "LoginScreen.jsx") |
| filepath | Full file path |
| file_extension | Extension (e.g., ".jsx") |
| status | modified/added/removed/renamed |
| lines_added | Lines added in this file |
| lines_deleted | Lines deleted in this file |
| lines_changed | Total lines changed |
| category | Main category (ui_screen, ui_component, backend, etc.) |
| subcategory | Technology (react, vue, flutter, android, ios, etc.) |
| is_screen | Boolean: True if this is a screen file |
| confidence | high/medium/low categorization confidence |

## Example Analysis

### Count screens developed by person:
```python
import pandas as pd
df = pd.read_csv('github_commit_files.csv')
screens = df[(df['is_screen'] == True) & (df['confidence'].isin(['high', 'medium']))]
screens_by_author = screens.groupby('author')['filepath'].nunique()
print(screens_by_author.sort_values(ascending=False))
```

### UI work by technology:
```python
ui_work = df[df['category'].isin(['ui_screen', 'ui_component', 'ui_style'])]
tech_summary = ui_work.groupby('subcategory').agg({
    'lines_added': 'sum',
    'lines_deleted': 'sum',
    'filepath': 'count'
})
print(tech_summary)
```

### Screen files in specific JIRA issue:
```python
issue_screens = df[df['jira_id'].str.contains('OOSM-1234', na=False) & (df['is_screen'] == True)]
print(issue_screens[['filepath', 'lines_added', 'lines_deleted', 'confidence']])
```

## Usage

The file will be automatically generated during:
- `python github_fetch.py fetch` - Full/incremental fetch
- `python github_fetch.py recent N` - Recent N days

Both commands create:
- `output/github_commits.csv`
- `output/github_commit_files.csv`

## Notes

- Test files are automatically excluded from categorization
- Build artifacts (node_modules, dist, build) are excluded
- Medium confidence screens are included (configurable in code)
- Stylesheets in UI folders count as UI work
- Shared components (Button, Modal) are NOT counted as screens
