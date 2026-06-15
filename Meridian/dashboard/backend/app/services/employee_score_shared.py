"""Shared employee score helper functions used by dashboard and report generation."""

import csv
import math
import os
from datetime import date, datetime
from typing import Any, Optional, Tuple

import pandas as pd


def clean_resource_value(value: Any) -> str:
    """Normalize resource field values for exact matching."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _get_fiscal_year_start(ref_date: date, fiscal_start_month: int = 4) -> date:
    """Return the first day of the fiscal year that contains the reference date."""
    year = ref_date.year
    if ref_date.month >= fiscal_start_month:
        return date(year, fiscal_start_month, 1)
    return date(year - 1, fiscal_start_month, 1)


def _get_fiscal_quarter_start(ref_date: date, fiscal_start_month: int = 4) -> date:
    """Return the first day of the fiscal quarter that contains the reference date."""
    year = ref_date.year
    month = ref_date.month
    fiscal_year = year if month >= fiscal_start_month else year - 1
    months_since_fy_start = (month - fiscal_start_month) % 12
    quarter_num = months_since_fy_start // 3
    quarter_start_month = fiscal_start_month + (quarter_num * 3)

    if quarter_start_month > 12:
        quarter_start_month -= 12
        quarter_start_year = fiscal_year + 1
    else:
        quarter_start_year = fiscal_year

    return date(quarter_start_year, quarter_start_month, 1)


def _weeks_elapsed(start: date, ref: date) -> int:
    """Return the ceiling number of weeks elapsed from start up to and including ref."""
    days = (ref - start).days
    return max(1, math.ceil((days + 1) / 7))


def parse_ref_date(as_of_date: Optional[str]) -> date:
    """Parse a YYYYMMDD string into a date, falling back to today on invalid input."""
    if as_of_date and len(as_of_date) == 8:
        try:
            return datetime.strptime(as_of_date, "%Y%m%d").date()
        except ValueError:
            pass
    return date.today()


def get_prorated_target(
    target_value: float,
    period: str,
    ref_date: date,
    fiscal_start_month: int = 4,
    prorate: bool = True,
    employee_start_date: Optional[date] = None,
) -> float:
    """Return the prorated target used for ROG comparison."""
    if not prorate:
        return target_value

    if period in ("Weekly", "Monthly"):
        return target_value

    if period == "Quarterly":
        quarter_start = _get_fiscal_quarter_start(ref_date, fiscal_start_month)
        effective_start = max(quarter_start, employee_start_date) if employee_start_date else quarter_start
        weeks = min(_weeks_elapsed(effective_start, ref_date), 13)
        return target_value * weeks / 13

    if period == "Annual":
        fiscal_year_start = _get_fiscal_year_start(ref_date, fiscal_start_month)
        effective_start = max(fiscal_year_start, employee_start_date) if employee_start_date else fiscal_year_start
        weeks = min(_weeks_elapsed(effective_start, ref_date), 52)
        return target_value * weeks / 52

    return target_value


def read_employee_kpi_value(
    evaluator,
    kpi_name: str,
    period: str,
    employee_sapid: str,
    employee_name: str,
    as_of_date: Optional[str] = None,
    logger=None,
):
    """Read the latest KPI value for a specific employee using SAPID when available."""
    base_kpi = evaluator.get_base_kpi(kpi_name)
    kpi_file = os.path.join(evaluator.output_dir, f"{base_kpi}-data.csv")

    if not os.path.exists(kpi_file):
        return None

    matched_value = None
    try:
        with open(kpi_file, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if as_of_date:
                    row_date = str(row.get("CurrentDate", "")).strip()
                    if row_date != as_of_date:
                        continue

                row_sapid = clean_resource_value(row.get("SAPID"))
                row_name = clean_resource_value(row.get("Name"))
                if employee_sapid and row_sapid == employee_sapid:
                    value = row.get(period, "")
                elif not row_sapid and row_name == employee_name:
                    value = row.get(period, "")
                else:
                    continue

                if value in (None, ""):
                    continue

                try:
                    matched_value = float(value)
                except ValueError:
                    matched_value = value
    except Exception as exc:
        if logger is not None:
            logger.warning("Could not read KPI data from %s: %s", kpi_file, exc)

    return matched_value


def read_employee_security_kpi_value_and_status(
    evaluator,
    kpi_name: str,
    period: str,
    employee_sapid: str,
    employee_name: str,
    as_of_date: Optional[str] = None,
    logger=None,
) -> Tuple[Optional[float], str]:
    """Read scan KPI value and configuration status for a specific employee."""
    base_kpi = evaluator.get_base_kpi(kpi_name)
    kpi_file = os.path.join(evaluator.output_dir, f"{base_kpi}-data.csv")

    if not os.path.exists(kpi_file):
        return None, "not_configured"

    matched_value = None
    matched_status = "configured"

    try:
        with open(kpi_file, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if as_of_date:
                    row_date = str(row.get("CurrentDate", "")).strip()
                    if row_date != as_of_date:
                        continue

                row_sapid = clean_resource_value(row.get("SAPID"))
                row_name = clean_resource_value(row.get("Name"))
                if employee_sapid and row_sapid == employee_sapid:
                    value = row.get(period, "")
                elif not row_sapid and row_name == employee_name:
                    value = row.get(period, "")
                else:
                    continue

                matched_status = clean_resource_value(row.get("ConfigurationStatus")).lower() or "configured"
                if matched_status == "not_configured":
                    matched_value = None
                    continue

                if value in (None, ""):
                    matched_value = None
                    continue

                try:
                    matched_value = float(value)
                except ValueError:
                    matched_value = None
    except Exception as exc:
        if logger is not None:
            logger.warning("Could not read security KPI data from %s: %s", kpi_file, exc)

    return matched_value, matched_status


def calculate_rog_status(value: float, target: float, goal_type: str) -> str:
    """Calculate ROG status from value, target, and maximize/minimize goal type."""
    if pd.isna(value) or pd.isna(target):
        return "green"
    if target == 0:
        return "green"

    percentage = (value / target) * 100
    if goal_type == "Maximize":
        if percentage >= 100:
            return "green"
        if percentage >= 80:
            return "orange"
        return "red"

    if percentage <= 100:
        return "green"
    if percentage <= 120:
        return "orange"
    return "red"
