"""
Audit: map Resources.csv entries to copilot_agent_chat_metrics.csv user_logins.

Matching strategy (tried in order):
  1. email_local_part.replace('.', '-')             e.g.  aakif-quayyum
  2. above + "_hclsw"                               e.g.  aakif-quayyum_hclsw
  3. GitHUB Name column (as-is)                     e.g.  aakif-quayyum
  4. GitHUB Name + "_hclsw"                         e.g.  aakif-quayyum_hclsw
"""

import csv
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_CSV = os.path.join(BASE_DIR, "config", "Resources.csv")
METRICS_CSV   = os.path.join(BASE_DIR, "output", "copilot_agent_chat_metrics.csv")

# ── 1. Load the set of user_logins from the metrics file ─────────────────────
metrics_logins = set()
with open(METRICS_CSV, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        login = row.get("user_login", "").strip()
        if login:
            metrics_logins.add(login)

# ── 2. Iterate Resources.csv and try to match ────────────────────────────────
found_rows     = []   # (sapid, name, matched_login, match_method)
not_found_rows = []   # (sapid, name, candidates_tried)

with open(RESOURCES_CSV, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        sapid      = row.get("SAPID",       "").strip()
        name       = row.get("Name",        "").strip()
        email      = row.get("EMail",       "").strip()
        github     = row.get("GitHUB Name", "").strip()

        candidates = []
        if email and "@" in email:
            local = email.split("@")[0].replace(".", "-").replace("_", "-")
            candidates.append((local,            "email → login"))
            candidates.append((local + "_hclsw", "email → login_hclsw"))
        if github:
            candidates.append((github.strip(),            "GitHUB Name"))
            candidates.append((github.strip() + "_hclsw", "GitHUB Name_hclsw"))

        matched = None
        for candidate, method in candidates:
            if candidate in metrics_logins:
                matched = (candidate, method)
                break

        if matched:
            found_rows.append((sapid, name, matched[0], matched[1]))
        else:
            tried = ", ".join(c for c, _ in candidates) if candidates else "(none)"
            not_found_rows.append((sapid, name, tried))

# ── 3. Print results ──────────────────────────────────────────────────────────
col_w = [10, 36, 38, 22]

def hdr(title):
    total = sum(col_w)
    print()
    print("─" * total)
    print(f" {title}")
    print("─" * total)
    print(f"{'SAPID':<{col_w[0]}}{'Name':<{col_w[1]}}{'user_login':<{col_w[2]}}{'match_method':<{col_w[3]}}")
    print("─" * total)

hdr(f"MATCHED  ({len(found_rows)} resources found in copilot_agent_chat_metrics.csv)")
for sapid, name, login, method in found_rows:
    print(f"{sapid:<{col_w[0]}}{name:<{col_w[1]}}{login:<{col_w[2]}}{method:<{col_w[3]}}")

total_w = sum(col_w[:3])
print()
print("─" * total_w)
print(f" NOT FOUND  ({len(not_found_rows)} resources missing from copilot_agent_chat_metrics.csv)")
print("─" * total_w)
print(f"{'SAPID':<{col_w[0]}}{'Name':<{col_w[1]}}{'candidates tried'}")
print("─" * total_w)
for sapid, name, tried in not_found_rows:
    print(f"{sapid:<{col_w[0]}}{name:<{col_w[1]}}{tried}")

print()
print("─" * total_w)
print(f" Total resources: {len(found_rows) + len(not_found_rows)} | "
      f"Matched: {len(found_rows)} | Not found: {len(not_found_rows)}")
print("─" * total_w)

