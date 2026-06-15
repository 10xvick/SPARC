"""
Update Resources.csv with copilot_user column.

Uses the same matching strategy as audit_copilot_users.py:
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
OUTPUT_CSV    = os.path.join(BASE_DIR, "config", "Resources.csv")  # Overwrite original

# ── 1. Load the set of user_logins from the metrics file ─────────────────────
metrics_logins = set()
with open(METRICS_CSV, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        login = row.get("user_login", "").strip()
        if login:
            metrics_logins.add(login)

print(f"Loaded {len(metrics_logins)} unique user_logins from copilot_agent_chat_metrics.csv")

# ── 2. Build mapping from email/github to user_login ───────────────────────────
mapping = {}  # (sapid, name) -> user_login

with open(RESOURCES_CSV, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        sapid      = row.get("SAPID",       "").strip()
        name       = row.get("Name",        "").strip()
        email      = row.get("EMail",       "").strip()
        github     = row.get("GitHUB Name", "").strip()

        candidates = []
        if email and "@" in email:
            local = email.split("@")[0].replace(".", "-").replace("_", "-")
            candidates.append(local)
            candidates.append(local + "_hclsw")
        if github:
            candidates.append(github.strip())
            candidates.append(github.strip() + "_hclsw")

        matched_login = None
        for candidate in candidates:
            if candidate in metrics_logins:
                matched_login = candidate
                break

        mapping[(sapid, name)] = matched_login or "not_mapped"

# ── 3. Read Resources.csv, add copilot_user column, and write back ────────────
rows = []
fieldnames = None

with open(RESOURCES_CSV, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        sapid = row.get("SAPID", "").strip()
        name  = row.get("Name",  "").strip()
        row["copilot_user"] = mapping.get((sapid, name), "not_mapped")
        rows.append(row)

# Add copilot_user to fieldnames if not present
if "copilot_user" not in fieldnames:
    fieldnames = list(fieldnames) + ["copilot_user"]

# ── 4. Write updated Resources.csv ────────────────────────────────────────────
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

# ── 5. Print statistics ───────────────────────────────────────────────────────
matched_count = sum(1 for v in mapping.values() if v != "not_mapped")
not_mapped_count = len(mapping) - matched_count

print(f"Updated {len(rows)} resources in Resources.csv")
print(f"  - Mapped: {matched_count}")
print(f"  - Not mapped: {not_mapped_count}")
print(f"Saved to: {OUTPUT_CSV}")
