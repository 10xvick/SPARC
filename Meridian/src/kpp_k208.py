#!/usr/bin/env python3
"""
KPP K208 - Copilot LOC Team Average
Aggregates Copilot LOC (k1 data) at team level and divides by total team size
(all team members in Resources.csv, including those with no Copilot mapping).
The resulting average is assigned to every individual in the team.
"""

import pandas as pd
import os
from datetime import date


def get_description():
    """Return KPI description."""
    return "Copilot LOC Team Average - Aggregates Copilot LOC per team and averages by team headcount"


def k208(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K208: Team-level average Copilot LOC, assigned back to each individual.

    Numerator  : sum of k1 Weekly/Monthly/Quarterly/Annual for team members
                 who appear in k1-data.csv.
    Denominator: total number of team members in Resources.csv for that team
                 (includes members with no Copilot licence / not_mapped).

    Args:
        resources_file (str): Path to Resources.csv
        jira_issues_file (str): Path to JIRAIssues.csv (unused, kept for interface compatibility)
        output_dir (str): Directory for output files
        fiscal_start_month (int): Fiscal year start month (default: 4 for April)
        current_date (date): Reporting date (default: today)

    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k208-data.csv')
    k1_file     = os.path.join(output_dir, 'k1-data.csv')

    if current_date is None:
        current_date = date.today()

    current_date_str = current_date.strftime('%Y%m%d')

    print(f"\n{'='*60}")
    print(f"KPP K208 - Copilot LOC Team Average")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")

    # ── 1. Load Resources (all members, for team sizes & metadata) ────────────
    print("Loading resources data...")
    try:
        df_res = pd.read_csv(resources_file)
        df_res['SAPID'] = df_res['SAPID'].fillna(0).astype(int).astype(str)
        # Drop -NA- team members from team-level computation
        df_res = df_res[df_res['Team'].notna() & (df_res['Team'] != '-NA-')]
        print(f"  ✓ Loaded {len(df_res)} resources (excluding -NA- team)")
    except Exception as e:
        print(f"  ✗ Error loading resources file: {e}")
        return False

    # ── 2. Compute team headcounts (denominator – includes unmapped members) ──
    team_size = df_res.groupby('Team')['SAPID'].count().to_dict()
    print(f"  Teams found: {', '.join(f'{t}({n})' for t, n in sorted(team_size.items()))}")

    # ── 3. Load k1-data.csv ───────────────────────────────────────────────────
    print("Loading K1 (Copilot LOC) data...")
    if not os.path.exists(k1_file):
        print(f"  ✗ k1-data.csv not found at {k1_file}. Run k1 first.")
        return False

    try:
        df_k1 = pd.read_csv(k1_file)
        df_k1['SAPID'] = df_k1['SAPID'].astype(str)
        df_k1['CurrentDate'] = df_k1['CurrentDate'].astype(str)
        # Use only the latest date's records
        latest_date = df_k1['CurrentDate'].max()
        df_k1 = df_k1[df_k1['CurrentDate'] == latest_date]
        print(f"  ✓ Loaded {len(df_k1)} K1 records for date {latest_date}")
    except Exception as e:
        print(f"  ✗ Error loading k1-data.csv: {e}")
        return False

    if df_k1.empty:
        print("  ⚠ No K1 data found")
        return False

    # Capture period labels from k1 data (same for all rows)
    first_row  = df_k1.iloc[0]
    week_label = first_row['Week']
    month_label = first_row['Month']
    quarter_label = first_row['Quarter']
    year_label = first_row['Year']

    # ── 4. Merge k1 data with resources to get Team for each k1 row ──────────
    sapid_to_team = df_res.set_index('SAPID')['Team'].to_dict()
    df_k1['Team'] = df_k1['SAPID'].map(sapid_to_team)

    # Only keep rows where team is known
    df_k1_with_team = df_k1[df_k1['Team'].notna()]

    # ── 5. Sum k1 values per team (numerator) ────────────────────────────────
    team_sums = df_k1_with_team.groupby('Team')[['Weekly', 'Monthly', 'Quarterly', 'Annual']].sum()

    # ── 6. Build output – one row per employee, value = team_sum / team_size ──
    result = []
    for _, emp in df_res.iterrows():
        team = emp['Team']
        n    = team_size.get(team, 1)  # denominator

        if team in team_sums.index:
            sums = team_sums.loc[team]
            weekly    = round(sums['Weekly']    / n, 2)
            monthly   = round(sums['Monthly']   / n, 2)
            quarterly = round(sums['Quarterly'] / n, 2)
            annual    = round(sums['Annual']    / n, 2)
        else:
            # No Copilot data at all for this team
            weekly = monthly = quarterly = annual = 0.0

        result.append({
            'CurrentDate': current_date_str,
            'Week':        week_label,
            'Month':       month_label,
            'Quarter':     quarter_label,
            'Year':        year_label,
            'SAPID':       emp['SAPID'],
            'Name':        emp['Name'],
            'Weekly':      weekly,
            'Monthly':     monthly,
            'Quarterly':   quarterly,
            'Annual':      annual,
        })

    new_df = pd.DataFrame(result)
    column_order = [
        'CurrentDate', 'Week', 'Month', 'Quarter', 'Year',
        'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
    ]
    new_df = new_df[column_order]

    # ── 7. Merge with existing file ───────────────────────────────────────────
    if os.path.exists(output_file):
        try:
            existing_df = pd.read_csv(output_file)
            existing_df['SAPID'] = existing_df['SAPID'].astype(str)
            existing_df['CurrentDate'] = existing_df['CurrentDate'].astype(str)
            new_df['SAPID'] = new_df['SAPID'].astype(str)
            new_df['CurrentDate'] = new_df['CurrentDate'].astype(str)

            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=['CurrentDate', 'SAPID'], keep='last')
            combined_df = combined_df.sort_values(['CurrentDate', 'SAPID'])
            combined_df.to_csv(output_file, index=False)
            print(f"  ✓ Updated {output_file} with {len(new_df)} records")
        except Exception as e:
            print(f"  ⚠ Error reading existing file, creating new: {e}")
            new_df.to_csv(output_file, index=False)
            print(f"  ✓ Created {output_file} with {len(new_df)} records")
    else:
        new_df.to_csv(output_file, index=False)
        print(f"  ✓ Created {output_file} with {len(new_df)} records")

    # ── 8. Print per-team summary ─────────────────────────────────────────────
    print(f"\n  Team averages (Annual LOC / headcount):")
    for team in sorted(team_size.keys()):
        n = team_size[team]
        if team in team_sums.index:
            annual_sum = team_sums.loc[team, 'Annual']
            avg = round(annual_sum / n, 1)
        else:
            annual_sum = 0
            avg = 0.0
        print(f"    {team:<20} headcount={n:>3}  sum={annual_sum:>8.0f}  avg={avg:>8.1f}")

    print(f"{'='*60}\n")
    return True
