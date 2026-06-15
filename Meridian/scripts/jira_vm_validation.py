import requests
from requests.auth import HTTPBasicAuth

# ==========================================================
# HARD-CODED CONFIGURATION
# ==========================================================

JIRA_URL = "http://cloud.appscan.com" #"https://hclsw-jiracentral-eng.atlassian.net"
USER_ID = "user@domain.com.example"
API_TOKEN = "your_api_token_here"

PROJECTS = [
    "AS",
    "FH",
    "HR",
    "PCS",
    "FSO",
    "OOSM",
    "DES",
    "ITRW",
    "ERXTX",
    "IT",
    "XITRP"
]

# ==========================================================

print("=" * 80)
print("JIRA VM VALIDATION")
print("=" * 80)

for project in PROJECTS:

    print(f"\nProject: {project}")

    url = f"{JIRA_URL}/rest/api/3/search/jql"

    payload = {
        "jql": f'project="{project}" ORDER BY updated DESC',
        "maxResults": 1,
        "fields": [
            "summary",
            "status",
            "assignee",
            "issuetype"
        ]
    }

    try:

        response = requests.post(
            url,
            auth=HTTPBasicAuth(USER_ID, API_TOKEN),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )

        print("Status:", response.status_code)

        if response.status_code != 200:
            print("FAILED")
            print(response.text[:300])
            continue

        data = response.json()

        issues = data.get("issues", [])

        print("SUCCESS")
        print("Issues Returned:", len(issues))

        if issues:

            issue = issues[0]

            print("Issue Key :", issue["key"])
            print(
                "Issue Type:",
                issue["fields"]["issuetype"]["name"]
            )
            print(
                "Status    :",
                issue["fields"]["status"]["name"]
            )

            print(
                "Summary   :",
                issue["fields"]["summary"][:100]
            )

    except Exception as ex:
        print("ERROR:", ex)

print("\n" + "=" * 80)
print("JIRA VM VALIDATION COMPLETE")
print("=" * 80)