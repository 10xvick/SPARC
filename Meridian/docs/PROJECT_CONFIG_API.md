# Project Configuration API Documentation

## Overview
The Project Configuration API allows you to manage GitHub repositories and JIRA projects through the TeamSight dashboard. This enables dynamic configuration of data sources without manually editing JSON configuration files.

## Base URL
```
http://127.0.0.1:8000/api/project-config
```

## Endpoints

### 1. Get Current Configuration
**GET** `/`

Returns the current GitHub and JIRA configurations.

**Response:**
```json
{
  "github_config": {
    "default": {...},
    "repositories": {...},
    "outputFile": "...",
    "checkpointFile": "...",
    "exportFormat": "csv"
  },
  "jira_config": {
    "default": {...},
    "projects": {...},
    "outputFile": "...",
    "checkpointFile": "...",
    "historyFile": "..."
  }
}
```

### 2. Get Default Configurations
**GET** `/defaults`

Returns default configurations and lists of currently configured repositories and projects.

**Response:**
```json
{
  "github_defaults": {
    "githubToken": "ghp_...",
    "githubApiBaseUrl": "https://github01.hclpnp.com/api/v3"
  },
  "jira_defaults": {
    "jiraServer": "https://hclsw-jiracentral-eng.atlassian.net",
    "userId": "user@example.com",
    "apiToken": "ATATT...",
    "maxResults": 50,
    "cutoffDate": "2025-03-31"
  },
  "github_repositories": ["owner/repo1", "owner/repo2"],
  "jira_projects": ["AS", "PCS", "DES"],
  "jira_prefix_team_mapping": {
    "AS": "HCL AION",
    "FSO": "FSO",
    "OOSM": "OOSM"
  }
}
```

### 3. Onboard New Project
**POST** `/onboard`

Onboard a new project by adding GitHub repositories and/or JIRA projects.

**Request Body:**
```json
{
  "project_name": "MyProject",
  "github_repos": [
    "organization/repository-1",
    "organization/repository-2"
  ],
  "jira_projects": ["PROJ1", "PROJ2"],
  "jira_prefix_team_mapping": {
    "PROJ1": "Team A",
    "PROJ2": "Team B"
  },
  "github_custom_config": {
    "githubToken": "ghp_...",
    "githubApiBaseUrl": "https://api.github.com"
  },
  "jira_custom_config": {
    "jiraServer": "https://mycompany.atlassian.net",
    "userId": "user@company.com",
    "apiToken": "ATATT...",
    "maxResults": 50,
    "cutoffDate": "2025-03-31"
  }
}
```

**Notes:**
- `project_name`: Required, unique identifier for the project
- `github_repos`: Optional, list of repositories in "owner/repo" format
- `jira_projects`: Optional, list of JIRA project keys (uppercase)
- `jira_prefix_team_mapping`: Required for each provided JIRA project key during onboarding
- `github_custom_config`: Optional, custom GitHub configuration (uses default if not provided)
- `jira_custom_config`: Optional, custom JIRA configuration (uses default if not provided)

**Response:**
```json
{
  "success": true,
  "message": "Project 'MyProject' onboarded successfully",
  "github": {
    "added": ["organization/repository-1"],
    "existing": ["organization/repository-2"],
    "total_repositories": 28
  },
  "jira": {
    "added": ["PROJ1"],
    "existing": ["PROJ2"],
    "total_projects": 11,
    "prefix_team_mappings_updated": 2
  }
}
```

### 4. Update GitHub Repository Configuration
**PUT** `/github/repository/{owner}/{repo}`

Update configuration for a specific GitHub repository.

**Request Body:**
```json
{
  "custom_field": "custom_value"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Configuration updated for repository owner/repo",
  "repository": "owner/repo",
  "config": {...}
}
```

### 5. Remove GitHub Repository
**DELETE** `/github/repository/{owner}/{repo}`

Remove a GitHub repository from configuration.

**Response:**
```json
{
  "success": true,
  "message": "Repository owner/repo removed successfully"
}
```

### 6. Update JIRA Project Configuration
**PUT** `/jira/project/{project_key}`

Update configuration for a specific JIRA project.

**Request Body:**
```json
{
  "custom_field": "custom_value"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Configuration updated for JIRA project PROJ1",
  "project_key": "PROJ1",
  "config": {...}
}
```

### 7. Remove JIRA Project
**DELETE** `/jira/project/{project_key}`

Remove a JIRA project from configuration.

**Response:**
```json
{
  "success": true,
  "message": "JIRA project PROJ1 removed successfully"
}
```

### 8. Update GitHub Default Configuration
**PUT** `/github/defaults`

Update the default GitHub configuration used for all repositories.

**Request Body:**
```json
{
  "githubToken": "ghp_newtoken",
  "githubApiBaseUrl": "https://github.company.com/api/v3"
}
```

**Response:**
```json
{
  "success": true,
  "message": "GitHub default configuration updated successfully",
  "config": {...}
}
```

### 9. Update JIRA Default Configuration
**PUT** `/jira/defaults`

Update the default JIRA configuration used for all projects.

**Request Body:**
```json
{
  "jiraServer": "https://company.atlassian.net",
  "userId": "user@company.com",
  "apiToken": "ATATT...",
  "maxResults": 100,
  "cutoffDate": "2026-01-01"
}
```

**Response:**
```json
{
  "success": true,
  "message": "JIRA default configuration updated successfully",
  "config": {...}
}
```

## Validation Rules

### GitHub Repository Format
- Must match pattern: `owner/repo`
- Example: `SPARC-Development-Lab/aion-core`

### JIRA Project Key Format
- Must start with uppercase letter
- Can contain only uppercase letters and numbers
- Examples: `AS`, `PCS`, `DES`, `OOSM`

## Error Responses

All endpoints may return error responses with the following format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

Common HTTP status codes:
- `400` - Bad Request (invalid format, validation error)
- `404` - Not Found (repository/project not found)
- `500` - Internal Server Error (file system error, JSON parsing error)

## Usage in Frontend

The Project Onboarding page is accessible from:
```
http://localhost:5173/admin/project-onboarding
```

Or via the "Project Onboarding" button in the System Administration page.

## Configuration Files

The API modifies the following configuration files:
- `/config/github_config.json` - GitHub repositories and credentials
- `/config/jira_config.json` - JIRA projects, credentials, and prefix-to-team mapping (`prefix_team_mapping`)

### KPI Mapping Note (Team-Level KPIs)

When this API is used to maintain source-to-team mappings (for example scan project → teams),
the corresponding KPI implementation must follow the team-level KPI rules in:

- `docs/README.md` → **Adding a New KPI (Implementation Checklist)**
- `docs/README.md` → **Team-Level KPI Handling (Required Pattern)**

In short: use configuration-driven mapping, aggregate multiple mapped sources per KPI rule,
and assign the resulting team value to all team members.

**Important:** After onboarding new projects, you should run the data fetch jobs to collect data from the newly added sources.

## Security Notes

⚠️ **Important Security Considerations:**
1. API tokens are stored in plain text in configuration files
2. The API returns sensitive tokens in responses
3. This API should only be accessible to administrators
4. Consider implementing authentication/authorization
5. In production, use environment variables or secrets management for credentials

## Example Workflows

### Onboard a New Project with Multiple Repositories
```bash
curl -X POST http://127.0.0.1:8000/api/project-config/onboard \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "NewProject",
    "github_repos": [
      "company/frontend-app",
      "company/backend-api",
      "company/mobile-app"
    ],
    "jira_projects": ["FRONT", "BACK", "MOB"]
  }'
```

### Update Default GitHub Token
```bash
curl -X PUT http://127.0.0.1:8000/api/project-config/github/defaults \
  -H "Content-Type: application/json" \
  -d '{
    "githubToken": "ghp_new_token_here",
    "githubApiBaseUrl": "https://github01.hclpnp.com/api/v3"
  }'
```

### View All Configured Projects
```bash
curl http://127.0.0.1:8000/api/project-config/defaults | jq
```
