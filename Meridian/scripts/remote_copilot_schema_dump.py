#!/usr/bin/env python3
import json
from pathlib import Path

import pymssql


def main() -> None:
    cfg = json.loads(Path("config/copilot_metrics_config.json").read_text(encoding="utf-8"))
    db = cfg["database"]

    conn = pymssql.connect(
        server=db["server"],
        port=int(db.get("port", 1433)),
        database=db["database"],
        user=db["user"],
        password=db["password"],
        tds_version="7.4",
        login_timeout=int(db.get("loginTimeout", 30)),
        as_dict=True,
    )

    cur = conn.cursor()
    cur.execute(
        """
        SELECT TABLE_SCHEMA, TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_SCHEMA, TABLE_NAME
        """
    )
    tables = cur.fetchall()

    print("TABLES:")
    for table in tables:
        print(f"- {table['TABLE_SCHEMA']}.{table['TABLE_NAME']}")

    for table in tables:
        schema = table["TABLE_SCHEMA"]
        table_name = table["TABLE_NAME"]

        print(f"\nSCHEMA FOR {schema}.{table_name}:")
        cur.execute(
            """
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
            ORDER BY ORDINAL_POSITION
            """,
            (schema, table_name),
        )
        columns = cur.fetchall()

        for col in columns:
            col_len = col["CHARACTER_MAXIMUM_LENGTH"]
            len_suffix = "" if col_len is None else f"({col_len})"
            print(
                f"- {col['COLUMN_NAME']}: {col['DATA_TYPE']}{len_suffix}, nullable={col['IS_NULLABLE']}"
            )

        print(f"\nSAMPLE ROWS FROM {schema}.{table_name} (TOP 5):")
        cur.execute(f"SELECT TOP 5 * FROM [{schema}].[{table_name}]")
        rows = cur.fetchall()

        if not rows:
            print("<no rows>")
            continue

        for idx, row in enumerate(rows, start=1):
            print(f"Row {idx}: {row}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
