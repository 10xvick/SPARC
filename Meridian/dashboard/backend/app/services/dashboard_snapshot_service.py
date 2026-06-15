"""Dashboard snapshot generation and retrieval service.

Builds pre-aggregated Team and Scrum dashboard payloads from CSV outputs and
serves them through an active snapshot pointer.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

# Add src directory to path to import KppEvaluator
import sys

project_root = Path(__file__).parent.parent.parent.parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from KppEvaluator import KppEvaluator

logger = logging.getLogger(__name__)

PERIODS = ["Weekly", "Quarterly", "Annual"]


class DashboardSnapshotService:
    """Manages dashboard snapshot lifecycle and reads."""

    def __init__(self, project_root_path: Path):
        self.project_root = project_root_path
        self.output_dir = self.project_root / "output"
        self.snapshot_root = self.output_dir / "dashboard_snapshots"
        self.active_pointer_file = self.snapshot_root / "ACTIVE.json"
        self.snapshot_lock_file = self.snapshot_root / ".generation.lock"
        self._lock = threading.Lock()

        # In-memory caches for fast request serving
        self._active_meta_cache: Optional[Dict[str, Any]] = None
        self._payload_cache: Dict[tuple[str, str, str], Dict[str, Any]] = {}

    @staticmethod
    def _normalize_as_of_date(as_of_date: Optional[str]) -> Optional[str]:
        if not as_of_date:
            return None
        value = str(as_of_date).strip()
        if not value:
            return None
        if len(value) == 10 and value[4] == "-" and value[7] == "-":
            value = value.replace("-", "")
        if len(value) == 8 and value.isdigit():
            return value
        return None

    @staticmethod
    def _normalize_resources_df(df: pd.DataFrame) -> pd.DataFrame:
        """Normalize Resources.csv headers and key text fields used for filtering/grouping."""
        df.columns = [str(column).strip() for column in df.columns]
        for column in ["Name", "SAPID", "Team", "Scrum", "Primary Role", "Secondary Role"]:
            if column in df.columns:
                df[column] = df[column].apply(lambda value: str(value).strip() if pd.notna(value) else value)
        return df

    def _latest_available_date(self) -> Optional[str]:
        dates = set()
        for kpi_file in sorted(self.output_dir.glob("k*-data.csv")):
            try:
                df = pd.read_csv(kpi_file, usecols=["CurrentDate"])
                vals = df["CurrentDate"].dropna().astype(str).str.strip()
                for v in vals:
                    if len(v) == 8 and v.isdigit():
                        dates.add(v)
            except Exception:
                continue
        return sorted(dates, reverse=True)[0] if dates else None

    def _read_active_meta(self) -> Optional[Dict[str, Any]]:
        if self._active_meta_cache is not None:
            return self._active_meta_cache

        if not self.active_pointer_file.exists():
            return None

        try:
            pointer = json.loads(self.active_pointer_file.read_text(encoding="utf-8"))
            snapshot_id = pointer.get("snapshot_id")
            if not snapshot_id:
                return None
            manifest_path = self.snapshot_root / snapshot_id / "manifest.json"
            if not manifest_path.exists():
                return None
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["snapshot_id"] = snapshot_id
            self._active_meta_cache = manifest
            return manifest
        except Exception as exc:
            logger.warning("Failed to read active dashboard snapshot metadata: %s", exc)
            return None

    def _clear_caches(self) -> None:
        self._active_meta_cache = None
        self._payload_cache.clear()

    def _snapshot_data_file(self, snapshot_id: str, scope: str, period: str) -> Path:
        return self.snapshot_root / snapshot_id / f"{scope}_{period}.json"

    def _acquire_generation_lock(self, source: str, normalized_date: str):
        os.makedirs(self.snapshot_root, exist_ok=True)
        lock_handle = open(self.snapshot_lock_file, "a+", encoding="utf-8")
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_handle.seek(0)
            lock_info = lock_handle.read().strip()
            lock_handle.close()
            detail = f" ({lock_info})" if lock_info else ""
            raise ValueError(f"Dashboard snapshot generation is already running{detail}")

        lock_handle.seek(0)
        lock_handle.truncate()
        lock_handle.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "source": source,
                    "as_of_date": normalized_date,
                    "started_at": datetime.now().isoformat(),
                }
            )
        )
        lock_handle.flush()
        return lock_handle

    def _load_scope_period_data(self, snapshot_id: str, scope: str, period: str) -> Optional[Dict[str, Any]]:
        cache_key = (snapshot_id, scope, period)
        if cache_key in self._payload_cache:
            return self._payload_cache[cache_key]

        path = self._snapshot_data_file(snapshot_id, scope, period)
        if not path.exists():
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self._payload_cache[cache_key] = payload
            return payload
        except Exception as exc:
            logger.warning("Failed to load snapshot payload %s: %s", path, exc)
            return None

    def get_snapshot_status(self) -> Dict[str, Any]:
        meta = self._read_active_meta()
        if not meta:
            return {
                "active": False,
                "message": "No active dashboard snapshot",
            }
        return {
            "active": True,
            "snapshot_id": meta.get("snapshot_id"),
            "as_of_date": meta.get("as_of_date"),
            "generated_at": meta.get("generated_at"),
            "team_count": meta.get("team_count", 0),
            "scrum_count": meta.get("scrum_count", 0),
            "employee_count": meta.get("employee_count", 0),
            "periods": meta.get("periods", PERIODS),
            "source": meta.get("source", "scheduled"),
        }

    def get_team_payload(self, team_name: str, period: str, as_of_date: Optional[str]) -> Optional[Dict[str, Any]]:
        meta = self._read_active_meta()
        if not meta:
            return None

        request_date = self._normalize_as_of_date(as_of_date) or meta.get("as_of_date")
        if request_date != meta.get("as_of_date"):
            return None

        data = self._load_scope_period_data(meta["snapshot_id"], "team", period)
        if not data:
            return None

        return data.get("data", {}).get(team_name)

    def get_scrum_payload(self, scrum_name: str, period: str, as_of_date: Optional[str]) -> Optional[Dict[str, Any]]:
        meta = self._read_active_meta()
        if not meta:
            return None

        request_date = self._normalize_as_of_date(as_of_date) or meta.get("as_of_date")
        if request_date != meta.get("as_of_date"):
            return None

        data = self._load_scope_period_data(meta["snapshot_id"], "scrum", period)
        if not data:
            return None

        return data.get("data", {}).get(scrum_name)

    def get_employee_payload(self, employee_identifier: str, period: str, as_of_date: Optional[str]) -> Optional[Dict[str, Any]]:
        meta = self._read_active_meta()
        if not meta:
            return None

        request_date = self._normalize_as_of_date(as_of_date) or meta.get("as_of_date")
        if request_date != meta.get("as_of_date"):
            return None

        data = self._load_scope_period_data(meta["snapshot_id"], "employee", period)
        if not data:
            return None

        return data.get("data", {}).get(str(employee_identifier).strip())

    def generate_snapshot(self, as_of_date: Optional[str] = None, source: str = "manual") -> Dict[str, Any]:
        """Build a snapshot and atomically activate it.

        If as_of_date is omitted, uses the latest available KPI CurrentDate.
        """
        with self._lock:
            normalized_date = self._normalize_as_of_date(as_of_date)
            if not normalized_date:
                normalized_date = self._latest_available_date()

            if not normalized_date:
                raise ValueError("No available KPI run date found to build dashboard snapshot")

            lock_handle = self._acquire_generation_lock(source, normalized_date)

            try:
                resources_file = self.project_root / "config" / "Resources.csv"
                jira_issues_file = self.project_root / "output" / "JIRAIssues.csv"
                github_commits_file = self.project_root / "output" / "github_commits.csv"
                roles_file = self.project_root / "config" / "Roles.csv"

                resources_df = self._normalize_resources_df(pd.read_csv(resources_file))
                roles_df = pd.read_csv(roles_file)

                evaluator = KppEvaluator(
                    resources_file=str(resources_file),
                    jira_issues_file=str(jira_issues_file),
                    github_commits_file=str(github_commits_file),
                    output_dir=str(self.output_dir),
                    fiscal_start_month=4,
                )

                # Late imports to avoid import cycles with dashboard endpoint modules.
                from app.api.employee_dashboard import build_employee_dashboard_payload
                from app.api.team_dashboard import aggregate_team_kpis
                from app.api.scrum_dashboard import aggregate_scrum_kpis

                teams = sorted(resources_df["Team"].dropna().astype(str).unique().tolist())
                scrums = sorted(resources_df["Scrum"].dropna().astype(str).unique().tolist())
                employee_count = len(resources_df)

                snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                snapshot_dir = self.snapshot_root / snapshot_id
                os.makedirs(snapshot_dir, exist_ok=True)

                for period in PERIODS:
                    team_payload: Dict[str, Any] = {}
                    scrum_payload: Dict[str, Any] = {}
                    employee_payload: Dict[str, Any] = {}

                    for team_name in teams:
                        team_members_df = resources_df[resources_df["Team"] == team_name]
                        if team_members_df.empty:
                            continue

                        team_members = team_members_df["Name"].tolist()
                        team_scrums = team_members_df["Scrum"].dropna().unique().tolist()
                        member_details = []
                        for _, row in team_members_df.iterrows():
                            member_details.append(
                                {
                                    "name": row["Name"],
                                    "scrum": row["Scrum"] if pd.notna(row["Scrum"]) else "N/A",
                                    "sapid": row["SAPID"] if pd.notna(row["SAPID"]) else "",
                                }
                            )

                        primary_roles = team_members_df["Primary Role"].dropna()
                        secondary_roles = team_members_df["Secondary Role"].dropna()
                        primary_role_distribution = [
                            {"role": role, "count": count}
                            for role, count in primary_roles.value_counts().to_dict().items()
                        ]
                        secondary_role_distribution = [
                            {"role": role, "count": count}
                            for role, count in secondary_roles.value_counts().to_dict().items()
                        ]

                        team_data = aggregate_team_kpis(
                            team_members,
                            team_members_df,
                            evaluator,
                            roles_df,
                            period,
                            normalized_date,
                        )

                        team_payload[team_name] = {
                            "success": True,
                            "team": {
                                "name": team_name,
                                "member_count": len(team_members),
                                "members": team_members,
                                "scrums": team_scrums,
                                "member_details": member_details,
                                "primary_role_distribution": primary_role_distribution,
                                "secondary_role_distribution": secondary_role_distribution,
                            },
                            "period": period,
                            **team_data,
                        }

                    for scrum_name in scrums:
                        scrum_members_df = resources_df[resources_df["Scrum"] == scrum_name]
                        if scrum_members_df.empty:
                            continue

                        scrum_members = scrum_members_df["Name"].tolist()
                        member_details = []
                        for _, row in scrum_members_df.iterrows():
                            member_details.append(
                                {
                                    "name": row["Name"],
                                    "sapid": row["SAPID"] if pd.notna(row["SAPID"]) else "",
                                }
                            )

                        primary_roles = scrum_members_df["Primary Role"].dropna()
                        secondary_roles = scrum_members_df["Secondary Role"].dropna()
                        primary_role_distribution = [
                            {"role": role, "count": count}
                            for role, count in primary_roles.value_counts().to_dict().items()
                        ]
                        secondary_role_distribution = [
                            {"role": role, "count": count}
                            for role, count in secondary_roles.value_counts().to_dict().items()
                        ]

                        scrum_data = aggregate_scrum_kpis(
                            scrum_members,
                            scrum_members_df,
                            evaluator,
                            roles_df,
                            period,
                            normalized_date,
                        )

                        scrum_payload[scrum_name] = {
                            "success": True,
                            "scrum": {
                                "name": scrum_name,
                                "member_count": len(scrum_members),
                                "members": scrum_members,
                                "member_details": member_details,
                                "primary_role_distribution": primary_role_distribution,
                                "secondary_role_distribution": secondary_role_distribution,
                            },
                            "period": period,
                            **scrum_data,
                        }

                    for _, employee_row in resources_df.iterrows():
                        employee_key = str(employee_row.get("SAPID", "")).strip() or str(employee_row.get("Name", "")).strip()
                        if not employee_key:
                            continue
                        employee_payload[employee_key] = build_employee_dashboard_payload(
                            employee_row,
                            evaluator,
                            roles_df,
                            period,
                            normalized_date,
                        )

                    team_file = self._snapshot_data_file(snapshot_id, "team", period)
                    scrum_file = self._snapshot_data_file(snapshot_id, "scrum", period)
                    employee_file = self._snapshot_data_file(snapshot_id, "employee", period)
                    team_file.write_text(
                        json.dumps({"as_of_date": normalized_date, "period": period, "data": team_payload}),
                        encoding="utf-8",
                    )
                    scrum_file.write_text(
                        json.dumps({"as_of_date": normalized_date, "period": period, "data": scrum_payload}),
                        encoding="utf-8",
                    )
                    employee_file.write_text(
                        json.dumps({"as_of_date": normalized_date, "period": period, "data": employee_payload}),
                        encoding="utf-8",
                    )

                manifest = {
                    "generated_at": datetime.now().isoformat(),
                    "as_of_date": normalized_date,
                    "periods": PERIODS,
                    "team_count": len(teams),
                    "scrum_count": len(scrums),
                    "employee_count": employee_count,
                    "source": source,
                }
                (snapshot_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

                # Atomically update active pointer
                os.makedirs(self.snapshot_root, exist_ok=True)
                fd, tmp_path = tempfile.mkstemp(prefix="active_", suffix=".json", dir=str(self.snapshot_root))
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        json.dump({"snapshot_id": snapshot_id}, handle)
                    os.replace(tmp_path, self.active_pointer_file)
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

                self._clear_caches()
                logger.info(
                    "Dashboard snapshot generated and activated: id=%s as_of_date=%s source=%s",
                    snapshot_id,
                    normalized_date,
                    source,
                )
                status = self.get_snapshot_status()
                status["success"] = True
                return status
            finally:
                try:
                    lock_handle.seek(0)
                    lock_handle.truncate()
                finally:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                    lock_handle.close()


_snapshot_service: Optional[DashboardSnapshotService] = None


def get_dashboard_snapshot_service() -> DashboardSnapshotService:
    global _snapshot_service
    if _snapshot_service is None:
        _snapshot_service = DashboardSnapshotService(project_root)
    return _snapshot_service
