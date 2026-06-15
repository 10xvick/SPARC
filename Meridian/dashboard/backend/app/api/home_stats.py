"""
API endpoints for home page statistics
"""
from fastapi import APIRouter
from typing import Dict, List, Any
import csv
import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/home", tags=["home"])


def load_resources() -> pd.DataFrame:
    """Load resources CSV file."""
    # Path from dashboard/backend/app/api/home_stats.py to config/Resources.csv
    csv_path = Path(__file__).parent.parent.parent.parent.parent / "config" / "Resources.csv"
    try:
        df = pd.read_csv(csv_path)
        df.columns = [str(column).strip() for column in df.columns]
        for column in ["Team", "Scrum", "Primary Role", "Secondary Role", "Name", "SAPID"]:
            if column in df.columns:
                df[column] = df[column].apply(lambda value: str(value).strip() if pd.notna(value) else value)
        return df
    except Exception as e:
        logger.error(f"Error loading Resources.csv: {e}")
        return pd.DataFrame()


@router.get("/statistics")
def get_home_statistics() -> Dict[str, Any]:
    """
    Get statistics for the home page dashboard.
    Returns counts and distribution data for teams, scrums, roles, and employees.
    """
    try:
        # Load resources
        resources_df = load_resources()
        
        if resources_df.empty:
            return {
                "success": False,
                "error": "Failed to load resources data"
            }
        
        # Calculate counts
        teams = resources_df["Team"].dropna().unique()
        teams_count = len([t for t in teams if t != "-NA-"])
        
        scrums = resources_df["Scrum"].dropna().unique()
        scrums_count = len(scrums)
        
        primary_roles = resources_df["Primary Role"].dropna().unique()
        primary_roles_count = len([r for r in primary_roles if r != "-"])
        
        secondary_roles = resources_df["Secondary Role"].dropna().unique()
        secondary_roles_count = len([r for r in secondary_roles if r != "-"])
        
        employees_count = len(resources_df)
        
        # Calculate primary role distribution
        primary_role_counts = resources_df[
            (resources_df["Primary Role"].notna()) & 
            (resources_df["Primary Role"] != "-")
        ]["Primary Role"].value_counts()
        
        primary_role_distribution = [
            {"name": role, "count": int(count)}
            for role, count in primary_role_counts.items()
        ]
        
        # Calculate secondary role distribution
        secondary_role_counts = resources_df[
            (resources_df["Secondary Role"].notna()) & 
            (resources_df["Secondary Role"] != "-")
        ]["Secondary Role"].value_counts()
        
        secondary_role_distribution = [
            {"name": role, "count": int(count)}
            for role, count in secondary_role_counts.items()
        ]
        
        return {
            "success": True,
            "statistics": {
                "teams": teams_count,
                "scrums": scrums_count,
                "roles": max(primary_roles_count, secondary_roles_count),
                "employees": employees_count
            },
            "primary_role_distribution": primary_role_distribution,
            "secondary_role_distribution": secondary_role_distribution
        }
        
    except Exception as e:
        logger.error(f"Error getting home statistics: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/available-dates")
def get_available_dates() -> Dict[str, List[str]]:
    """
    Return distinct KPI run dates (CurrentDate column) found in output CSV files,
    sorted descending so the most recent date is first.
    Scans all k*-data.csv files to collect the union of all run dates.
    """
    output_dir = Path(__file__).parent.parent.parent.parent.parent / "output"
    dates: set = set()
    for kpi_file in sorted(output_dir.glob("k*-data.csv")):
        try:
            with open(kpi_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    date_val = str(row.get("CurrentDate", "")).strip()
                    if date_val and date_val.isdigit():
                        dates.add(date_val)
        except Exception:
            continue
    return {"dates": sorted(dates, reverse=True)}
