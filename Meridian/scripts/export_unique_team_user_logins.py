#!/usr/bin/env python3
"""Export unique team_name and user_login pairs from Copilot usage table.

Reads DB connection settings from config/copilot_metrics_config.json and writes:
    output/copilot_unique_team_user_logins.csv
"""

import csv
import json
from pathlib import Path

import pymssql


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_path = project_root / "config" / "copilot_metrics_config.json"
    output_path = project_root / "output" / "copilot_unique_team_user_logins.csv"

    config = json.loads(config_path.read_text(encoding="utf-8"))
    db = config["database"]

    connection = pymssql.connect(
        server=db["server"],
        port=int(db.get("port", 1433)),
        database=db["database"],
        user=db["user"],
        password=db["password"],
        tds_version="7.4",
        login_timeout=int(db.get("loginTimeout", 30)),
        as_dict=True,
    )

    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT DISTINCT team_name, user_login
        FROM dbo.copilot_usage_daily
        WHERE team_name IS NOT NULL
          AND user_login IS NOT NULL
          AND LTRIM(RTRIM(team_name)) <> ''
          AND LTRIM(RTRIM(user_login)) <> ''
        ORDER BY team_name, user_login
        """
    )
    rows = cursor.fetchall()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(["team_name", "user_login"])
        for row in rows:
            writer.writerow([row["team_name"], row["user_login"]])

    cursor.close()
    connection.close()

    print(f"WROTE_FILE={output_path}")
    print(f"ROW_COUNT={len(rows)}")


if __name__ == "__main__":
    main()
