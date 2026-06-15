"""
Shared KPI utility functions used across dashboard API endpoints.

Prorated target logic
---------------------
KPI values are cumulative over the selected period. Comparing a
few days of accumulated value against the full-period target
creates spurious "all red" dashboards early in the period.

Solution: before the ROG status comparison, scale the target
value by the fraction of the period that has elapsed (using
ceiling-week granularity as the smallest unit):

    Weekly  : no prorating – target used as-is
    Monthly : no prorating – uses Weekly Target as a proxy
    Quarterly: target × ceil(weeks_since_quarter_start) / 13
    Annual  : target × ceil(weeks_since_year_start)   / 52

"Weeks elapsed" is rounded **up** so that even a single day in a
new week counts as one full week.  The prorated factor is capped
at 1.0 so the target never exceeds the configured value.

Note: the returned *display* target is always the original
(un-prorated) value; only the ROG-status comparison uses the
prorated target.
"""
import math
from datetime import date, datetime
from typing import Optional

FISCAL_START_MONTH: int = 4  # April


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_fiscal_year_start(ref_date: date, fiscal_start_month: int = FISCAL_START_MONTH) -> date:
    """Return the first day of the fiscal year that contains *ref_date*."""
    year = ref_date.year
    if ref_date.month >= fiscal_start_month:
        return date(year, fiscal_start_month, 1)
    return date(year - 1, fiscal_start_month, 1)


def _get_fiscal_quarter_start(ref_date: date, fiscal_start_month: int = FISCAL_START_MONTH) -> date:
    """Return the first day of the fiscal quarter that contains *ref_date*."""
    year = ref_date.year
    month = ref_date.month

    if month < fiscal_start_month:
        fiscal_year = year - 1
    else:
        fiscal_year = year

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
    """
    Return the ceiling number of weeks elapsed from *start* up to and
    including *ref*.  Minimum return value is 1.

    Examples (fiscal year starts April 1):
        April 1  → 1  (day 1 of week 1)
        April 7  → 1  (last day of week 1)
        April 8  → 2  (first day of week 2)
        April 14 → 2
        April 15 → 3
    """
    days = (ref - start).days          # 0-based (0 = same day)
    return max(1, math.ceil((days + 1) / 7))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_ref_date(as_of_date: Optional[str]) -> date:
    """
    Parse an *as_of_date* string in YYYYMMDD format into a :class:`date`.
    Falls back to :func:`date.today` when the argument is absent or invalid.
    """
    if as_of_date and len(as_of_date) == 8:
        try:
            return datetime.strptime(as_of_date, '%Y%m%d').date()
        except ValueError:
            pass
    return date.today()


def get_prorated_target(
    target_value: float,
    period: str,
    ref_date: date,
    fiscal_start_month: int = FISCAL_START_MONTH,
    prorate: bool = True,
    employee_start_date: Optional[date] = None,
) -> float:
    """
    Return the prorated target for ROG-status comparison.

    The *display* target shown to users should remain the original
    *target_value*; this function returns only a comparison value.

    Args:
        target_value: Original configured target from Roles.csv.
        period: One of "Weekly", "Monthly", "Quarterly", "Annual".
        ref_date: The reference date (as-of date or today).
        fiscal_start_month: Month number when the fiscal year starts (default 4 = April).
        prorate: If False, return target_value unchanged (e.g. for gating,
                 percentage, or score KPIs where prorating is not meaningful).
        employee_start_date: If provided (and later than period start), use this
                 as the effective start date so mid-year joiners get a fair target.

    Returns:
        Prorated target for comparison.  Always <= target_value when prorate=True.
    """
    if not prorate:
        return target_value

    if period in ('Weekly', 'Monthly'):
        # Weekly targets need no prorating.
        # Monthly period uses Weekly Target as a proxy — also no prorating.
        return target_value

    if period == 'Quarterly':
        q_start = _get_fiscal_quarter_start(ref_date, fiscal_start_month)
        effective_start = max(q_start, employee_start_date) if employee_start_date else q_start
        weeks = min(_weeks_elapsed(effective_start, ref_date), 13)
        return target_value * weeks / 13

    if period == 'Annual':
        fy_start = _get_fiscal_year_start(ref_date, fiscal_start_month)
        effective_start = max(fy_start, employee_start_date) if employee_start_date else fy_start
        weeks = min(_weeks_elapsed(effective_start, ref_date), 52)
        return target_value * weeks / 52

    # Unknown period — return original target unchanged
    return target_value
