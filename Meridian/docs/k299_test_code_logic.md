# K299 Test Code Logic (Commits-Only, Deduplicated)

## Purpose
K299 measures **test code lines added** per engineer. It must always be a subset of overall authored code additions (K227) for the same period.

## Data Sources
- `output/github_commit_files.csv` (file-level commit diff rows)
- `output/github_commits.csv` (commit-level metadata used to identify merge commits)
- `config/Resources.csv` (employee mapping)

## Inclusion Rules
A row is included in K299 only when all conditions are met:
1. Row belongs to a **test file**: `category == "test"`.
2. Row belongs to a **non-merge commit**.
3. Row is **deduplicated** at file-change granularity.
4. Row can be mapped to an employee by **author email**.

## Merge Commit Exclusion (Critical)
Merge commits are excluded because they re-surface branch history and inflate file-change totals.

### Detection logic
- Primary: from `github_commits.csv`, exclude SHAs where commit message matches:
  - `^Merge (pull request|branch)`
- Fallback: if `message` exists in `github_commit_files.csv`, apply the same pattern there too.

Result: only authored (non-merge) commits are counted.

## Deduplication Logic
To avoid counting the same file change more than once (for example, when fetch runs across multiple branches or overlaps), K299 deduplicates file rows by:
- `commit_sha`
- `filepath`
- `author_email`

Only the first row for each key is retained.

## Employee Mapping Logic
K299 uses email-based mapping for consistency with K227:
- Resource key: `Resources.csv -> GIT Email`
- Commit-file key: `github_commit_files.csv -> author_email`

Why email mapping:
- `author` can be display name and is not stable/unique.
- `GitHUB Name` may be username-style text and may not match display names.
- Email gives the most reliable one-to-one mapping for KPI aggregation.

## Period Aggregation
After filtering + dedup + employee mapping, K299 sums `lines_added` per SAPID/Name for:
- Weekly
- Monthly
- Quarterly
- Annual

## Expected Relationship to K227
Because K227 counts non-merge authored code additions and K299 is test-only from the same authored universe, we expect:

`K299 <= K227` per user and team for the same period.

## Validation (HCL AION, remote check)
After fixing logic and regenerating KPIs:
- K227 annual total: `38,445`
- K299 annual total: `10,534`
- Members with `K299 > K227`: `0`

This confirms test-code KPI is now a proper subset of total authored code.
