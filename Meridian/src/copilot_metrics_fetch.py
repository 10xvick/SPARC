"""
Copilot Usage Metrics Collection Job
=======================================

Collects GitHub Copilot usage metrics from Azure SQL Database.
Initial implementation: Test connectivity and list available tables.

Usage:
    python copilot_metrics_fetch.py
    
Environment Variables (override config file):
    COPILOT_DB_SERVER          - Database server hostname
    COPILOT_DB_PORT            - Database port (default: 1433)
    COPILOT_DB_NAME            - Database name
    COPILOT_DB_USER            - Database user
    COPILOT_DB_PASSWORD        - Database password
"""

import os
import sys
import csv
import json
import logging
from collections import defaultdict
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class CopilotMetricsCollector:
    """Collects Copilot usage metrics from Azure SQL Database"""
    
    DEFAULT_CONFIG_PATH = "config/copilot_metrics_config.json"
    
    def __init__(self, project_root: Optional[str] = None):
        """Initialize the collector with configuration"""
        self.project_root = project_root or os.environ.get("TEAMSIGHT_HOME", "..")
        self.config_path = os.path.join(self.project_root, self.DEFAULT_CONFIG_PATH)
        self.config = self._load_config()
        self.db_connection = None
        self.execution_start = datetime.now()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file and environment variables"""
        config = {}
        
        # Load from config file
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                logger.info(f"Loaded configuration from {self.config_path}")
            else:
                logger.warning(f"Config file not found at {self.config_path}, using defaults")
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            config = self._get_default_config()
        
        # Override with environment variables
        config = self._apply_env_overrides(config)
        
        return config
    
    @staticmethod
    def _get_default_config() -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "database": {
                "server": "metrics-genai.database.windows.net",
                "port": 1433,
                "database": "metrics-genai",
                "user": "srinivas.rao@metrics-genai",
                "password": "",  # Must be set via env or config file
                "authentication": "ActiveDirectoryPassword",
                "encrypt": True,
                "trustServerCertificate": False,
                "hostNameInCertificate": "*.database.windows.net",
                "loginTimeout": 30
            },
            "schedule": {
                "enabled": True,
                "cron_expression": "15 2 * * *",
                "description": "Daily at 2:15 AM local time"
            },
            "features": {
                "test_connectivity": True,
                "list_tables": True,
                "collect_metrics": False,
                "export_format": "csv"
            }
        }
    
    @staticmethod
    def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to config"""
        db_config = config.get("database", {})
        
        # Database server
        if os.environ.get("COPILOT_DB_SERVER"):
            db_config["server"] = os.environ.get("COPILOT_DB_SERVER")
        
        # Database port
        if os.environ.get("COPILOT_DB_PORT"):
            try:
                db_config["port"] = int(os.environ.get("COPILOT_DB_PORT"))
            except ValueError:
                logger.warning("Invalid COPILOT_DB_PORT, using default")
        
        # Database name
        if os.environ.get("COPILOT_DB_NAME"):
            db_config["database"] = os.environ.get("COPILOT_DB_NAME")
        
        # Database user
        if os.environ.get("COPILOT_DB_USER"):
            db_config["user"] = os.environ.get("COPILOT_DB_USER")
        
        # Database password
        if os.environ.get("COPILOT_DB_PASSWORD"):
            db_config["password"] = os.environ.get("COPILOT_DB_PASSWORD")

        # Authentication mode (e.g., ActiveDirectoryPassword, SqlPassword)
        if os.environ.get("COPILOT_DB_AUTHENTICATION"):
            db_config["authentication"] = os.environ.get("COPILOT_DB_AUTHENTICATION")
        
        config["database"] = db_config
        return config
    
    def _log_config_summary(self):
        """Log configuration summary (without sensitive data)"""
        db_config = self.config.get("database", {})
        logger.info("=" * 70)
        logger.info("Copilot Metrics Collection Configuration")
        logger.info("=" * 70)
        logger.info(f"Server: {db_config.get('server')}")
        logger.info(f"Port: {db_config.get('port')}")
        logger.info(f"Database: {db_config.get('database')}")
        logger.info(f"User: {db_config.get('user')}")
        logger.info(f"Driver: pymssql (FreeTDS — no ODBC driver required)")
        logger.info(f"Schedule: {self.config.get('schedule', {}).get('description')}")
        features = self.config.get("features", {})
        logger.info(f"Test Connectivity: {features.get('test_connectivity')}")
        logger.info(f"List Tables: {features.get('list_tables')}")
        logger.info(f"Collect Metrics: {features.get('collect_metrics')}")
        logger.info("=" * 70)
    
    def _get_pymssql_kwargs(self) -> Dict[str, Any]:
        """Build pymssql connection kwargs from configuration.
        
        pymssql uses FreeTDS under the hood — no Microsoft ODBC driver required.
        Works on Linux/Ubuntu out of the box with: pip install pymssql
        """
        db_config = self.config.get("database", {})
        return {
            "server":        db_config.get("server"),
            "port":          int(db_config.get("port", 1433)),
            "database":      db_config.get("database"),
            "user":          db_config.get("user"),
            "password":      db_config.get("password"),
            "tds_version":   "7.4",   # Required for Azure SQL
            "login_timeout": int(db_config.get("loginTimeout", 60)),
            "as_dict":       False,   # Rows as tuples (consistent with existing cursor code)
        }
    
    def test_connectivity(self) -> bool:
        """Test database connectivity using pymssql (FreeTDS — no ODBC driver required)."""
        logger.info("Testing database connectivity via pymssql...")

        try:
            import pymssql
        except ImportError:
            logger.error("pymssql module not found.")
            logger.error("")
            logger.error("To install pymssql:")
            logger.error("  Ubuntu/Debian: sudo apt-get install -y freetds-dev freetds-bin && pip install pymssql")
            logger.error("  macOS:         brew install freetds && pip install pymssql")
            logger.error("  Windows:       pip install pymssql")
            logger.error("")
            return False

        kwargs = self._get_pymssql_kwargs()
        db_config = self.config.get("database", {})

        try:
            self.db_connection = pymssql.connect(**kwargs)
            logger.info("✓ Successfully connected to database")
            logger.info(f"  Server:   {db_config.get('server')}:{db_config.get('port', 1433)}")
            logger.info(f"  Database: {db_config.get('database')}")
            logger.info(f"  User:     {db_config.get('user')}")
            return True

        except pymssql.OperationalError as e:
            logger.error(f"✗ Connection failed (OperationalError): {str(e)[:300]}")
            logger.error("")
            logger.error("Common causes:")
            logger.error("  1. Server IP not whitelisted in Azure SQL firewall")
            logger.error("     → Add this server's public IP in Azure Portal → SQL Server → Networking")
            logger.error("  2. Wrong username/password")
            logger.error("  3. Port 1433 blocked by local firewall — test with: nc -vz metrics-genai.database.windows.net 1433")
            return False
        except pymssql.InterfaceError as e:
            logger.error(f"✗ Connection failed (InterfaceError): {str(e)[:300]}")
            return False
        except Exception as e:
            logger.error(f"✗ Connection failed ({type(e).__name__}): {str(e)[:300]}")
            return False
    
    def list_available_tables(self) -> List[str]:
        """List all available tables in the database"""
        if not self.db_connection:
            logger.warning("Database not connected, skipping table listing")
            return []
        
        logger.info("Retrieving available tables...")
        
        try:
            cursor = self.db_connection.cursor()
            
            # Query to get all user-defined tables
            query = """
            SELECT TABLE_SCHEMA, TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_SCHEMA, TABLE_NAME
            """
            
            cursor.execute(query)
            tables = cursor.fetchall()
            cursor.close()
            
            logger.info(f"✓ Found {len(tables)} tables")
            logger.info("-" * 70)
            
            current_schema = None
            for schema, table_name in tables:
                if schema != current_schema:
                    current_schema = schema
                    logger.info(f"\n[{schema}]")
                logger.info(f"  - {table_name}")
            
            logger.info("-" * 70)
            
            return [f"{schema}.{table_name}" for schema, table_name in tables]
            
        except Exception as e:
            logger.error(f"✗ Failed to retrieve tables: {str(e)[:200]}")
            return []
    
    def get_copilot_tables(self) -> List[str]:
        """Identify Copilot-related tables"""
        if not self.db_connection:
            return []
        
        logger.info("Searching for Copilot-related tables...")
        
        try:
            cursor = self.db_connection.cursor()
            
            # Query to find tables with copilot-related names
            query = """
            SELECT TABLE_SCHEMA, TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            AND (
                TABLE_NAME LIKE '%copilot%'
                OR TABLE_NAME LIKE '%usage%'
                OR TABLE_NAME LIKE '%metrics%'
            )
            ORDER BY TABLE_SCHEMA, TABLE_NAME
            """
            
            cursor.execute(query)
            tables = cursor.fetchall()
            cursor.close()
            
            if tables:
                logger.info(f"✓ Found {len(tables)} Copilot-related tables:")
                for schema, table_name in tables:
                    logger.info(f"  - {schema}.{table_name}")
            else:
                logger.info("No Copilot-related tables found")
            
            return [f"{schema}.{table_name}" for schema, table_name in tables]
            
        except Exception as e:
            logger.error(f"Failed to search for Copilot tables: {str(e)[:200]}")
            return []
    
    # -------------------------------------------------------------------------
    # Period helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_current_periods(ref_date: Optional[date] = None) -> Tuple[str, str, str, str, str]:
        """Return (CurrentDate, Week, Month, Quarter, Year) labels for ref_date.

        Examples (ref_date = 2026-03-10):
            CurrentDate → "20260310"
            Week        → "202611"      (ISO year + zero-padded ISO week)
            Month       → "Mar2026"
            Quarter     → "JFM2026"     (first letters of Jan/Feb/Mar)
            Year        → "FY2025"      (financial year Apr-Mar)
        """
        if ref_date is None:
            ref_date = date.today()

        current_date_str = ref_date.strftime("%Y%m%d")

        # ISO week: use isocalendar() — returns (iso_year, iso_week, iso_weekday)
        iso_year, iso_week, _ = ref_date.isocalendar()
        week_str = f"{iso_year}{iso_week:02d}"

        month_str = ref_date.strftime("%b%Y")

        # Calendar quarter labels (JFM / AMJ / JAS / OND)
        month = ref_date.month
        quarter_map = {
            1: "JFM", 2: "JFM", 3: "JFM",
            4: "AMJ", 5: "AMJ", 6: "AMJ",
            7: "JAS", 8: "JAS", 9: "JAS",
            10: "OND", 11: "OND", 12: "OND",
        }
        quarter_str = f"{quarter_map[month]}{ref_date.year}"

        # Financial year (Apr–Mar): FY is the year the April starts in
        fy_year = ref_date.year if month >= 4 else ref_date.year - 1
        year_str = f"FY{fy_year}"

        return current_date_str, week_str, month_str, quarter_str, year_str

    @staticmethod
    def _fy_date_range(ref_date: Optional[date] = None) -> Tuple[date, date]:
        """Return (fy_start, fy_end) for the financial year containing ref_date."""
        if ref_date is None:
            ref_date = date.today()
        month = ref_date.month
        fy_year = ref_date.year if month >= 4 else ref_date.year - 1
        return date(fy_year, 4, 1), date(fy_year + 1, 3, 31)

    @staticmethod
    def _bool_val(v) -> bool:
        """Normalise SQL bit / Python bool / string 'True'/'1' to Python bool."""
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v != 0
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1")
        return False

    # -------------------------------------------------------------------------
    # Metrics collection
    # -------------------------------------------------------------------------

    def collect_metrics(self) -> bool:
        """Query dbo.copilot_usage_daily and write two output CSV files:

        1. copilot_loc_metrics.csv
           CurrentDate, Week, Month, Quarter, Year, user_login,
           loc_added_weekly, loc_added_monthly, loc_added_annual

        2. copilot_agent_chat_metrics.csv
           CurrentDate, Week, Month, Quarter, Year, user_login,
           used_agent_weekly, used_agent_monthly, used_agent_annual,
           used_chat_weekly,  used_chat_monthly,  used_chat_annual

        Data is filtered to team_name values listed in config['projects'].
        Aggregation window = current financial year (Apr–Mar).
        """
        if not self.db_connection:
            logger.warning("Database not connected — skipping metrics collection")
            return False

        projects = self.config.get("projects", [])
        if not projects:
            logger.warning("No projects in copilot_metrics_config.json — skipping metrics collection")
            return False

        ref_date = date.today()
        current_date_str, week_str, month_str, quarter_str, year_str = self._get_current_periods(ref_date)
        iso_year, iso_week, _ = ref_date.isocalendar()
        curr_year, curr_month = ref_date.year, ref_date.month

        # Annual window: driven by cutoffDate in config (e.g. "2025-03-31" → FY starts 2025-04-01)
        cutoff_str = self.config.get("cutoffDate", "")
        if cutoff_str:
            cutoff = date.fromisoformat(cutoff_str)
            fy_start = cutoff + timedelta(days=1)          # e.g. 2025-04-01
            fy_end   = date(cutoff.year + 1, cutoff.month, cutoff.day)  # e.g. 2026-03-31
            # Use the config FY label while today is within the configured window;
            # once today moves past fy_end (i.e. into the next FY), derive the
            # label from today's calendar so it advances automatically.
            if ref_date <= fy_end:
                year_str = f"FY{cutoff.year}"
            else:
                fy_year = ref_date.year if ref_date.month >= 4 else ref_date.year - 1
                year_str = f"FY{fy_year}"
                # Also advance the query window so April+ data is included
                fy_start = date(fy_year, 4, 1)
                fy_end   = date(fy_year + 1, 3, 31)
            logger.info(f"Annual window: {fy_start} → {fy_end} ({year_str})")
        else:
            fy_start, fy_end = self._fy_date_range(ref_date)
            logger.info(f"Annual window (auto): {fy_start} → {fy_end}")

        logger.info(f"Collecting metrics | ref_date={current_date_str} | week={week_str} | "
                    f"month={month_str} | quarter={quarter_str} | year={year_str}")
        logger.info(f"Filtering to {len(projects)} project(s): {projects}")

        # Build parameterised IN clause (pymssql uses %s placeholders)
        placeholders = ", ".join(["%s"] * len(projects))
        query = f"""
            SELECT
                user_login,
                CAST(day AS DATE)       AS day,
                used_agent,
                used_chat,
                ISNULL(loc_added_sum, 0) AS loc_added_sum
            FROM dbo.copilot_usage_daily
            WHERE team_name IN ({placeholders})
              AND day >= %s
              AND day <= %s
            ORDER BY user_login, day
        """

        try:
            cursor = self.db_connection.cursor()
            params = tuple(projects) + (fy_start, fy_end)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cursor.close()
            logger.info(f"Fetched {len(rows)} rows from dbo.copilot_usage_daily")
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return False

        # -------------------------------------------------------------------
        # Aggregate in Python — no external libraries required
        # -------------------------------------------------------------------
        users: set = set()

        # Months belonging to the same calendar quarter as today
        _qmap = {1:{1,2,3}, 2:{1,2,3}, 3:{1,2,3},
                 4:{4,5,6}, 5:{4,5,6}, 6:{4,5,6},
                 7:{7,8,9}, 8:{7,8,9}, 9:{7,8,9},
                 10:{10,11,12}, 11:{10,11,12}, 12:{10,11,12}}
        curr_quarter_months = _qmap[curr_month]

        loc_week:    Dict[str, int] = defaultdict(int)
        loc_month:   Dict[str, int] = defaultdict(int)
        loc_quarter: Dict[str, int] = defaultdict(int)
        loc_annual:  Dict[str, int] = defaultdict(int)

        # Sets of distinct dates per user where used_agent / used_chat was True
        agent_week_days:    Dict[str, set] = defaultdict(set)
        agent_month_days:   Dict[str, set] = defaultdict(set)
        agent_quarter_days: Dict[str, set] = defaultdict(set)
        agent_annual_days:  Dict[str, set] = defaultdict(set)

        chat_week_days:    Dict[str, set] = defaultdict(set)
        chat_month_days:   Dict[str, set] = defaultdict(set)
        chat_quarter_days: Dict[str, set] = defaultdict(set)
        chat_annual_days:  Dict[str, set] = defaultdict(set)

        # Either agent OR chat used on the day
        either_week_days:    Dict[str, set] = defaultdict(set)
        either_month_days:   Dict[str, set] = defaultdict(set)
        either_quarter_days: Dict[str, set] = defaultdict(set)
        either_annual_days:  Dict[str, set] = defaultdict(set)

        for (user_login, day_val, used_agent_val, used_chat_val, loc_val) in rows:
            if not user_login:
                continue
            users.add(user_login)

            # Normalise day_val to a date object (pymssql may return datetime)
            if isinstance(day_val, datetime):
                day_obj = day_val.date()
            elif isinstance(day_val, date):
                day_obj = day_val
            else:
                try:
                    day_obj = datetime.strptime(str(day_val)[:10], "%Y-%m-%d").date()
                except Exception:
                    continue

            loc_int = int(loc_val or 0)
            is_agent = self._bool_val(used_agent_val)
            is_chat  = self._bool_val(used_chat_val)

            # LOC: sum all rows (no dedup)
            loc_annual[user_login] += loc_int

            in_curr_month   = (day_obj.year == curr_year and day_obj.month == curr_month)
            in_curr_quarter = (day_obj.year == curr_year and day_obj.month in curr_quarter_months)

            d_iso_year, d_iso_week, _ = day_obj.isocalendar()
            in_curr_week = (d_iso_year == iso_year and d_iso_week == iso_week)

            if in_curr_month:   loc_month[user_login]   += loc_int
            if in_curr_quarter: loc_quarter[user_login] += loc_int
            if in_curr_week:    loc_week[user_login]    += loc_int

            # Agent / Chat: track distinct days (max 1 per day per user)
            if is_agent:
                agent_annual_days[user_login].add(day_obj)
                if in_curr_quarter: agent_quarter_days[user_login].add(day_obj)
                if in_curr_month:   agent_month_days[user_login].add(day_obj)
                if in_curr_week:    agent_week_days[user_login].add(day_obj)

            if is_chat:
                chat_annual_days[user_login].add(day_obj)
                if in_curr_quarter: chat_quarter_days[user_login].add(day_obj)
                if in_curr_month:   chat_month_days[user_login].add(day_obj)
                if in_curr_week:    chat_week_days[user_login].add(day_obj)

            if is_agent or is_chat:
                either_annual_days[user_login].add(day_obj)
                if in_curr_quarter: either_quarter_days[user_login].add(day_obj)
                if in_curr_month:   either_month_days[user_login].add(day_obj)
                if in_curr_week:    either_week_days[user_login].add(day_obj)

        logger.info(f"Unique users found: {len(users)}")

        # -------------------------------------------------------------------
        # Write output CSV files
        # -------------------------------------------------------------------
        output_dir = os.path.join(self.project_root, "output")
        os.makedirs(output_dir, exist_ok=True)

        sorted_users = sorted(users)

        # --- File 1: LOC metrics ---
        loc_file = os.path.join(output_dir, "copilot_loc_metrics.csv")
        with open(loc_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "CurrentDate", "Week", "Month", "Quarter", "Year",
                "user_login",
                "loc_added_weekly", "loc_added_monthly", "loc_added_quarterly", "loc_added_annual"
            ])
            for user in sorted_users:
                writer.writerow([
                    current_date_str, week_str, month_str, quarter_str, year_str,
                    user,
                    loc_week[user], loc_month[user], loc_quarter[user], loc_annual[user]
                ])
        logger.info(f"✓ copilot_loc_metrics.csv written — {len(sorted_users)} rows → {loc_file}")

        # --- File 2: Agent / Chat usage metrics ---
        ac_file = os.path.join(output_dir, "copilot_agent_chat_metrics.csv")
        with open(ac_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "CurrentDate", "Week", "Month", "Quarter", "Year",
                "user_login",
                "used_agent_weekly",       "used_agent_monthly",       "used_agent_quarterly",       "used_agent_annual",
                "used_chat_weekly",        "used_chat_monthly",        "used_chat_quarterly",        "used_chat_annual",
                "used_agent_or_chat_weekly", "used_agent_or_chat_monthly", "used_agent_or_chat_quarterly", "used_agent_or_chat_annual"
            ])
            for user in sorted_users:
                writer.writerow([
                    current_date_str, week_str, month_str, quarter_str, year_str,
                    user,
                    len(agent_week_days[user]),    len(agent_month_days[user]),    len(agent_quarter_days[user]),    len(agent_annual_days[user]),
                    len(chat_week_days[user]),     len(chat_month_days[user]),     len(chat_quarter_days[user]),     len(chat_annual_days[user]),
                    len(either_week_days[user]),   len(either_month_days[user]),   len(either_quarter_days[user]),   len(either_annual_days[user])
                ])
        logger.info(f"✓ copilot_agent_chat_metrics.csv written — {len(sorted_users)} rows → {ac_file}")

        return True

    def close_connection(self):
        """Close database connection"""
        if self.db_connection:
            try:
                self.db_connection.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
            finally:
                self.db_connection = None
    
    def run(self) -> int:
        """Main execution method"""
        try:
            self._log_config_summary()
            
            # Test connectivity
            if not self.test_connectivity():
                logger.error("Failed to connect to database")
                return 1
            
            # List available tables (informational — logged only)
            if self.config.get("features", {}).get("list_tables"):
                self.list_available_tables()
                self.get_copilot_tables()

            # Collect metrics → write output CSVs
            if self.config.get("features", {}).get("collect_metrics"):
                self.collect_metrics()
            
            # Summary
            execution_duration = (datetime.now() - self.execution_start).total_seconds()
            logger.info("=" * 70)
            logger.info(f"Execution completed successfully in {execution_duration:.2f} seconds")
            logger.info("=" * 70)
            
            return 0
            
        except Exception as e:
            logger.error(f"Execution failed: {str(e)}", exc_info=True)
            return 1
            
        finally:
            self.close_connection()


def main():
    """Main entry point"""
    project_root = os.environ.get("TEAMSIGHT_HOME", ".")
    
    collector = CopilotMetricsCollector(project_root)
    exit_code = collector.run()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
