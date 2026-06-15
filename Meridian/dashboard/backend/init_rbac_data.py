#!/usr/bin/env python3
"""
Initialize RBAC data files from Resources.csv.
Creates users.json, role_permissions.json, and api_keys.json.

Usage:
    python init_rbac_data.py [--force]
"""
import os
import sys
import pandas as pd
from datetime import datetime
import secrets

# Add dashboard/backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'dashboard', 'backend'))

from app.services.auth_service import AuthService
from app.utils.json_handler import save_json_atomic, ensure_dir

# Configuration
RESOURCES_CSV = "config/Resources.csv"
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
ROLE_PERMISSIONS_FILE = os.path.join(DATA_DIR, "role_permissions.json")
API_KEYS_FILE = os.path.join(DATA_DIR, "api_keys.json")

BUILT_IN_PERMISSIONS = {
    "view:own_employee_dashboard": "View own employee dashboard",
    "view:team_employee_dashboard": "View team employee dashboards",
    "view:managed_employee_dashboard": "View managed employees dashboards",
    "view:team_dashboard": "View team dashboard",
    "view:scrum_dashboard": "View scrum dashboard",
    "view:reports": "View reports",
    "view:config": "View configuration",
    "view:admin_menu": "View admin menu",
    "manage:users": "Manage users",
    "manage:roles": "Manage roles",
    "manage:api_keys": "Manage API keys",
    "update:own_password": "Update own password",
    "update:any_password": "Update any user password",
    "api:read_all": "API read all",
    "api:write_kpi": "API write KPI",
    "api:full_access": "API full access",
}

BUILT_IN_ROLES = {
    "User": [
        "view:own_employee_dashboard",
        "update:own_password"
    ],
    "Team Manager": [
        "view:own_employee_dashboard",
        "view:team_employee_dashboard",
        "view:team_dashboard",
        "view:scrum_dashboard",
        "view:reports",
        "update:own_password"
    ],
    "Lead": [
        "view:own_employee_dashboard",
        "view:managed_employee_dashboard",
        "view:team_dashboard",
        "view:scrum_dashboard",
        "update:own_password"
    ],
    "API User": [
        "api:read_all",
        "api:write_kpi"
    ],
    "Admin": [
        "view:own_employee_dashboard",
        "view:team_employee_dashboard",
        "view:managed_employee_dashboard",
        "view:team_dashboard",
        "view:scrum_dashboard",
        "view:reports",
        "view:config",
        "view:admin_menu",
        "manage:users",
        "manage:roles",
        "manage:api_keys",
        "update:own_password",
        "update:any_password",
        "api:full_access"
    ],
    "Admin Viewer": [
        "view:own_employee_dashboard",
        "view:team_employee_dashboard",
        "view:managed_employee_dashboard",
        "view:team_dashboard",
        "view:scrum_dashboard",
        "view:reports",
        "view:config",
        "view:admin_menu",
        "api:read_all"
    ]
}


def determine_role(row: pd.Series) -> str:
    """Determine user role based on available CSV columns."""
    reporting = pd.to_numeric(row.get("Reporting", 0), errors="coerce")
    reporting_count = int(reporting) if pd.notna(reporting) else 0
    primary_role = str(row.get("Primary Role", "")).strip().lower()

    if reporting_count > 0 and "manager" in primary_role:
        return "Team Manager"
    if reporting_count > 0:
        return "Lead"
    return "User"


def init_users_from_csv(force: bool = False) -> None:
    """Initialize users.json from Resources.csv"""
    if os.path.exists(USERS_FILE) and not force:
        print(f"✓ {USERS_FILE} already exists (use --force to overwrite)")
        return
    
    print(f"Initializing {USERS_FILE} from {RESOURCES_CSV}...")
    
    try:
        df = pd.read_csv(RESOURCES_CSV)
    except FileNotFoundError:
        print(f"✗ Error: {RESOURCES_CSV} not found")
        sys.exit(1)
    
    users = []
    user_id = 1
    now = datetime.now().isoformat()
    user_id_by_name = {}
    manager_name_by_user_id = {}
    
    # Load all resources as users
    for idx, row in df.iterrows():
        sapid = str(row.get("SAPID", "")).strip()
        name = str(row.get("Name", "")).strip()
        team = str(row.get("Team", "")).strip()
        
        if not sapid or not name:
            print(f"  ⚠ Row {idx}: Skipping - missing SAPID or Name")
            continue
        
        role = determine_role(row)
        password = AuthService.generate_default_password()
        manager_name = str(row.get("Manager Name", "")).strip()
        manager_name_norm = manager_name.lower()
        email_value = str(row.get("EMail", "")).strip()
        email = email_value if email_value and email_value.lower() != "nan" else f"{name.lower().replace(' ', '.')}@company.com"
        
        users.append({
            "id": user_id,
            "sapid": sapid,
            "name": name,
            "email": email,
            "role": role,
            "password_hash": AuthService.hash_password(password),
            "is_active": True,
            "team_ids": [team] if team else [],
            "managed_user_ids": [],
            "source": "resources_csv",
            "last_login": None,
            "created_at": now,
            "updated_at": now
        })
        user_id_by_name[name.lower()] = user_id
        manager_name_by_user_id[user_id] = manager_name_norm
        user_id += 1

    # Build managed_user_ids based on Manager Name links
    manager_to_reports = {}
    for report_user_id, manager_name_norm in manager_name_by_user_id.items():
        if not manager_name_norm:
            continue
        manager_id = user_id_by_name.get(manager_name_norm)
        if not manager_id:
            continue
        manager_to_reports.setdefault(manager_id, set()).add(report_user_id)

    for user in users:
        report_ids = sorted(manager_to_reports.get(user["id"], set()))
        user["managed_user_ids"] = report_ids
        if user["role"] == "User" and report_ids:
            user["role"] = "Lead"
    
    # Add default admin user
    admin_password = AuthService.generate_default_password()
    users.append({
        "id": user_id,
        "sapid": "admin",
        "name": "Administrator",
        "email": "admin@company.com",
        "role": "Admin",
        "password_hash": AuthService.hash_password(admin_password),
        "is_active": True,
        "team_ids": [],
        "managed_user_ids": [],
        "source": "manual",
        "last_login": None,
        "created_at": now,
        "updated_at": now
    })
    print(f"  ℹ Default admin user created (SAPID: admin)")
    admin_user_id = user_id
    user_id += 1
    
    # Add default API user
    api_user_password = AuthService.generate_default_password()
    users.append({
        "id": user_id,
        "sapid": "api_user",
        "name": "API User",
        "email": None,
        "role": "API User",
        "password_hash": AuthService.hash_password(api_user_password),
        "is_active": True,
        "team_ids": [],
        "managed_user_ids": [],
        "source": "manual",
        "last_login": None,
        "created_at": now,
        "updated_at": now
    })
    api_user_id = user_id
    print(f"  ℹ Default API user created (SAPID: api_user)")
    
    data = {"users": users}
    save_json_atomic(USERS_FILE, data)
    print(f"✓ Created {USERS_FILE} with {len(users)} users")
    print(f"  ℹ Admin default password: {admin_password}")
    print(f"  ℹ API user default password: {api_user_password}")

    return {
        "admin_user_id": admin_user_id,
        "api_user_id": api_user_id
    }


def init_role_permissions(force: bool = False) -> None:
    """Initialize role_permissions.json"""
    if os.path.exists(ROLE_PERMISSIONS_FILE) and not force:
        print(f"✓ {ROLE_PERMISSIONS_FILE} already exists (use --force to overwrite)")
        return
    
    print(f"Initializing {ROLE_PERMISSIONS_FILE}...")
    
    data = {
        "built_in_roles": BUILT_IN_ROLES,
        "custom_roles": {}
    }
    
    save_json_atomic(ROLE_PERMISSIONS_FILE, data)
    print(f"✓ Created {ROLE_PERMISSIONS_FILE} with {len(BUILT_IN_ROLES)} built-in roles")


def init_api_keys(api_user_id: int, force: bool = False) -> None:
    """Initialize api_keys.json"""
    if os.path.exists(API_KEYS_FILE) and not force:
        print(f"✓ {API_KEYS_FILE} already exists (use --force to overwrite)")
        return
    
    print(f"Initializing {API_KEYS_FILE}...")
    
    # Generate default API key
    import hashlib
    api_key = "teamsight_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    data = {
        "api_keys": [
            {
                "id": 1,
                "user_id": api_user_id,
                "key_hash": key_hash,
                "key_prefix": api_key[:12],
                "name": "Default API Key",
                "is_active": True,
                "created_at": datetime.now().isoformat(),
                "last_used": None
            }
        ]
    }
    
    save_json_atomic(API_KEYS_FILE, data)
    print(f"✓ Created {API_KEYS_FILE}")
    print(f"  ℹ Default API Key: {api_key}")
    print(f"  ⚠ Save this key securely - it won't be displayed again")


def main():
    force = "--force" in sys.argv
    
    print("\n🔐 Initializing RBAC data files...\n")
    
    # Ensure data directory exists
    ensure_dir(USERS_FILE)
    
    init_data = init_users_from_csv(force)
    print()
    init_role_permissions(force)
    print()
    if init_data and isinstance(init_data, dict):
        init_api_keys(init_data.get("api_user_id", 1), force)
    else:
        # If users file already existed and wasn't recreated, resolve API user id from file
        from app.utils.json_handler import load_json_safe
        existing_users = load_json_safe(USERS_FILE, {"users": []}).get("users", [])
        api_user = next((u for u in existing_users if u.get("sapid") == "api_user"), None)
        init_api_keys(api_user.get("id", 1) if api_user else 1, force)
    
    print("\n✓ RBAC initialization complete!\n")
    print("Next steps:")
    print("1. Log in with admin user (SAPID: admin)")
    print("2. In the User Management page, sync users from Resources.csv if needed")
    print("3. Assign Team Managers and Leads")
    print("4. Create custom roles as needed\n")


if __name__ == "__main__":
    main()
