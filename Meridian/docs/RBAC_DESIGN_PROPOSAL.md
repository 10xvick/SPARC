# TeamSight RBAC Implementation Design Proposal

## 1. Roles & Permissions Matrix

| Role | Employee Dashboard (Own) | Employee Dashboard (Team) | Employee Dashboard (RM's) | Team Dashboard | Scrum Dashboard | Reports | Config/Admin | API Access |
|------|:------------------------:|:------------------------:|:------------------------:|:--------------:|:---------------:|:-------:|:------------:|:----------:|
| **User** | ✓ (Self only) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| **Team Manager** | ✓ (Self) | ✓ (Team) | ✗ | ✓ (Team) | ✓ (Team Scrums) | ✓ | ✗ | ✗ |
| **Lead** | ✓ (Self) | ✓ (Managed reports) | ✓ | ✓ (Their teams) | ✓ (Their scrums) | ✓ | ✗ | ✗ |
| **API User** | N/A | N/A | N/A | N/A | N/A | N/A | N/A | ✓ (Full - restricted later) |
| **Admin** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## 2. User Creation & Role Assignment

### Mapping from Resources.csv

**Row Analysis Sequence:**
1. **Primary Role** (column) → Maps to: Developer, DevOps Engineer, QA Engineer, UI Developer, UI Designer, Data Engineer, Data Scientist, etc.
2. **Team Lead** (column) → If yes, assign **Team Manager** role (in addition to User)
3. **RM** (column) → If yes, assign **Lead** role (in addition to User)

**Role Assignment Logic:**
```
If Team Lead = Yes → Role = "Team Manager"
Else If RM = Yes → Role = "Lead"
Else → Role = "User"
```

**Initial User Creation:**
- Create all 165 resources as users with initial role assignment
- One default **API User** (credentials generated for integrations)
- One default **Admin** user

---

## 3. Data Storage Strategy

### **JSON Files** (Recommended for Simplicity)
**Location:** `data/` directory

**Advantages:**
- Simple, human-readable format
- Easy to backup and version control
- No external database dependency
- Easy to edit manually if needed
- Consistent with project's current approach (CSV configs, JSON scheduler state)
- Low operational overhead

**Files:**
- `data/users.json` - User credentials and metadata
- `data/role_permissions.json` - Permission definitions per role
- `data/api_keys.json` - API tokens (hashed)
- `data/user_sync_history.json` - Audit trail of sync operations (optional)

---

## 4. JSON File Structures

### File 1: `data/users.json`
```json
{
  "users": [
    {
      "id": 1,
      "sapid": "K1001",
      "name": "John Doe",
      "email": "john.doe@company.com",
      "role": "User",
      "password_hash": "$2b$12$...",
      "is_active": true,
      "last_login": "2026-03-17T10:30:00Z",
      "created_at": "2026-03-01T00:00:00Z",
      "updated_at": "2026-03-17T10:30:00Z"
    },
    {
      "id": 2,
      "sapid": "K2001",
      "name": "Alice Smith",
      "email": "alice.smith@company.com",
      "role": "Team Manager",
      "password_hash": "$2b$12$...",
      "is_active": true,
      "last_login": null,
      "team_ids": ["TEAM_A", "TEAM_B"],
      "managed_user_ids": [1, 3, 4],
      "created_at": "2026-03-01T00:00:00Z",
      "updated_at": "2026-03-01T00:00:00Z"
    },
    {
      "id": 3,
      "sapid": "api_user",
      "name": "API User",
      "email": null,
      "role": "API User",
      "password_hash": null,
      "is_active": true,
      "last_login": null,
      "created_at": "2026-03-01T00:00:00Z",
      "updated_at": "2026-03-01T00:00:00Z"
    }
  ]
}
```

### File 2: `data/role_permissions.json`
```json
{
  "roles": {
    "User": {
      "permissions": [
        "view:own_employee_dashboard",
        "update:own_password"
      ]
    },
    "Team Manager": {
      "permissions": [
        "view:own_employee_dashboard",
        "view:team_employee_dashboard",
        "view:team_dashboard",
        "view:scrum_dashboard",
        "view:reports",
        "update:own_password"
      ]
    },
    "Lead": {
      "permissions": [
        "view:own_employee_dashboard",
        "view:managed_employee_dashboard",
        "view:team_dashboard",
        "view:scrum_dashboard",
        "view:reports",
        "update:own_password"
      ]
    },
    "API User": {
      "permissions": [
        "api:read_all",
        "api:write_kpi"
      ]
    },
    "Admin": {
      "permissions": [
        "view:all_dashboards",
        "view:config",
        "view:admin_menu",
        "manage:users",
        "manage:roles",
        "manage:api_keys",
        "update:any_password",
        "api:full_access"
      ]
    }
  }
}
```

### File 3: `data/api_keys.json`
```json
{
  "api_keys": [
    {
      "id": 1,
      "user_id": 3,
      "key_hash": "sha256_hash_of_full_key",
      "key_prefix": "teamsigh",
      "name": "Default API Key",
      "is_active": true,
      "created_at": "2026-03-01T00:00:00Z",
      "last_used": "2026-03-17T15:30:00Z"
    }
  ]
}
```

### File 4: `data/user_sync_history.json` (Optional, for audit trail)
```json
{
  "sync_history": [
    {
      "timestamp": "2026-03-17T10:00:00Z",
      "initiated_by": "admin_user_id",
      "created": 165,
      "updated": 3,
      "deactivated": 1,
      "errors": [],
      "duration_seconds": 2.5
    }
  ]
}
```

---

## 5. Atomic JSON Operations (Critical for Data Safety)

**Problem:** Multiple processes might write to JSON simultaneously, causing data loss.

**Solution:** Atomic write pattern (write to temp file, rename)

```python
# In utils/json_handler.py
import json
import tempfile
from pathlib import Path

def save_json_atomic(filepath: str, data: dict) -> None:
    """Write JSON atomically using temp file + rename"""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file first
    with tempfile.NamedTemporaryFile(
        mode='w', 
        dir=filepath.parent, 
        delete=False, 
        suffix='.tmp'
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp_path = tmp.name
    
    # Atomic rename (OS-level guarantee)
    Path(tmp_path).replace(filepath)

def load_json_safe(filepath: str, default: dict = None) -> dict:
    """Load JSON with fallback"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return default or {}
```

**Usage in services:**
```python
# In user_service.py
class UserService:
    def __init__(self, users_file: str = "data/users.json"):
        self.users_file = users_file
        self.users = load_json_safe(users_file, {"users": []})
    
    def save_users(self):
        save_json_atomic(self.users_file, self.users)
    
    def add_user(self, user: dict):
        self.users["users"].append(user)
        self.save_users()  # Atomic write
```

---

## 6. Authentication & Authorization

### Authentication Flow
1. **Login endpoint:** `POST /api/auth/login`
   - Input: `sapid` + `password`
   - Output: `access_token` (JWT, 1 hour), `refresh_token` (JWT, 7 days), `user` object
   - Users can log in immediately with default or custom password

2. **Token format (JWT payload):**
   ```json
   {
     "sub": "user_id",
     "sapid": "K1234",
     "name": "John Doe",
     "role": "Team Manager",
     "team_ids": ["TEAM_A", "TEAM_B"],
     "managed_user_ids": [5, 6, 7],
     "exp": 1234567890,
     "iat": 1234567800
   }
   ```

3. **Refresh endpoint:** `POST /api/auth/refresh`

### Authorization
**Middleware approach:**
```python
@require_role("Team Manager", "Admin")
@require_permission("view:team_dashboard")
async def get_team_dashboard(request):
    pass
```

**Dynamic permission check:**
```python
@require_permission_dynamic
async def get_employee_dashboard(request, employee_id):
    # Check if user owns dashboard or is team manager/lead/admin
    pass
```

---

## 7. Default Passwords & First-Login Flow

### Password Generation
- Format: `8-character alphanumeric` (e.g., `T9k2xM4p`)
- Generated during user creation and displayed in admin UI (once only)
- Users can log in immediately with default password
- Users can change password anytime via profile settings

### Password Change Endpoints
```
POST /api/auth/change-password
  Input: current_password, new_password
  Permissions: All authenticated users (for self)

POST /api/admin/users/{user_id}/reset-password
  Input: (none, generates new 8-char password)
  Permissions: Admin only
```

---

## 8. User Sync from Resources.csv

### Sync Endpoint
```
POST /api/admin/users/sync
  Input: force_rescan (boolean, default false)
  Output: { created: 10, updated: 5, deactivated: 2, errors: [] }
  Permissions: Admin only
```

### Sync Logic
1. Read current Resources.csv
2. For each resource:
   - If user doesn't exist → Create with role assignment
   - If user exists → Update team/manager mappings if changed
   - If user not in CSV anymore → No action (keep existing users)
3. Return summary

### Sync Execution
- **Manual trigger only:** Admin endpoint `/api/admin/users/sync`
- Can be called manually whenever Resources.csv changes
- Returns summary of created, updated users (no deactivation)
- Note: Users must be manually deactivated or deleted via admin panel if needed

### Manual User Management
- **Create users:** Admin can create users outside of CSV (e.g., contractors, external users)
- **Delete users:** Admin can permanently delete users
- **Edit users:** Admin can modify user info, role, team assignments
- Endpoints:
  - `POST /api/admin/users` - Create manual user
  - `PUT /api/admin/users/{user_id}` - Update user
  - `DELETE /api/admin/users/{user_id}` - Delete user

---

## 9. Custom Roles & Custom Users

### Custom Roles
Admin can define custom roles beyond the five built-in roles (User, Team Manager, Lead, API User, Admin):
- **Create:** `POST /api/admin/roles` - Define new role with selected permissions
- **Update:** `PUT /api/admin/roles/{role_name}` - Modify permissions for a role
- **Delete:** `DELETE /api/admin/roles/{role_name}` - Remove custom role (built-in roles cannot be deleted)
- **List permissions:** `GET /api/admin/roles/available-permissions` - Show all available permissions to choose from

**Example Custom Role:**
```json
{
  "name": "Department Lead",
  "permissions": [
    "view:own_employee_dashboard",
    "view:team_employee_dashboard",
    "view:team_dashboard",
    "view:reports"
  ]
}
```

### Custom Users
Admin can manually create users outside of Resources.csv (e.g., contractors, external consultants):
- **Create:** `POST /api/admin/users` with email, name, role, team assignments
- **Update:** `PUT /api/admin/users/{user_id}` - Modify user details, role, team assignments
- **Delete:** `DELETE /api/admin/users/{user_id}` - Permanently remove user
- **List:** `GET /api/admin/users` - View all users with filtering/pagination
- **Reset password:** `POST /api/admin/users/{user_id}/reset-password` - Generate new 8-char password

**Note:** Users created from Resources.csv and manual users coexist; sync does not remove manual users.

---

## 10. Implementation Architecture

### Backend Structure
```
dashboard/backend/app/
├── models/
│   ├── __init__.py
│   └── user.py              # User, Role, Permission Pydantic models
├── services/
│   ├── auth_service.py      # Login, token generation, password hashing
│   ├── rbac_service.py      # Permission checks, role evaluation, custom roles
│   ├── user_service.py      # Load/save users from JSON
│   ├── user_sync_service.py # Sync from Resources.csv (add-only)
│   └── role_service.py      # Manage custom roles
├── routers/
│   ├── auth.py              # /api/auth/* endpoints
│   └── admin.py             # /api/admin/users/*, /api/admin/roles/* endpoints
├── middleware/
│   └── auth_middleware.py   # JWT validation, role/permission decorators
├── dependencies.py          # Dependency injection for current user
└── utils/
    └── json_handler.py      # Atomic JSON file read/write
```

**How it works:**
- `user_service.py` loads `data/users.json` into memory at startup
- `role_service.py` loads `data/role_permissions.json` with built-in + custom roles
- Changes written back atomically (write to temp file, then rename)
- All permission checks happen in-memory (fast)
- No locking complexity (JSON files are simple)

### Role Storage Structure
```json
data/role_permissions.json
{
  "built_in_roles": {
    "User": { "permissions": [...] },
    "Team Manager": { "permissions": [...] },
    "Lead": { "permissions": [...] },
    "API User": { "permissions": [...] },
    "Admin": { "permissions": [...] }
  },
  "custom_roles": {
    "Department Lead": { "permissions": [...] },
    "Regional Manager": { "permissions": [...] }
  }
}
```

### Frontend Structure
```
dashboard/frontend/src/
├── pages/
│   ├── Auth/
│   │   ├── Login.tsx            # Login form
│   │   └── Logout.tsx
│   └── Admin/
│       ├── UserManagement.tsx   # User CRUD (create, edit, delete, list)
│       └── RoleManagement.tsx   # Role CRUD (create, edit, delete, list)
├── components/
│   └── PrivateRoute.tsx         # Role-based route guarding
├── services/
│   ├── auth.ts                  # Login, logout, token refresh
│   ├── api_client.ts            # Attach JWT to all requests
│   ├── userService.ts           # User CRUD API calls
│   └── roleService.ts           # Role CRUD API calls
└── utils/
    └── permissions.ts           # Check user permissions on frontend
```

---

## 11. Implementation Phases

### Phase 1: Core Infrastructure (This PR)
- ✅ JSON file structure and initialization
- ✅ User/Role/Permission Pydantic models
- ✅ Auth service (password hashing, JWT generation)
- ✅ User service (JSON load/save with atomic writes)
- ✅ Role service (custom role management)
- ✅ Login endpoint
- ✅ User sync from Resources.csv (add-only, no deactivation)
- ✅ Manual user CRUD endpoints
- ✅ Custom role CRUD endpoints
- ✅ Backend decorators/middleware
- ❌ Frontend login page

### Phase 2: Admin UI for User & Role Management
- ✅ User Management page (create, edit, delete, list, reset password)
- ✅ Role Management page (create, edit, delete, list permissions)
- ✅ PrivateRoute protection (Admin-only pages)

### Phase 3: Frontend Integration
- ✅ Login/logout pages
- ✅ PrivateRoute protection
- ✅ Role-based menu hiding
- ✅ Permission-based element rendering

### Phase 4: Role-Specific Views (Later)
- ❌ Team Manager sees only their teams
- ❌ Lead sees only managed employees
- ❌ User sees only themselves

---

## 12. Design Decisions & Alternatives

### Q: Store passwords or use LDAP/SSO?
**Decision: Passwords + bcrypt**
- **Reason:** Works offline, no external dependency, simple to implement
- **Alternative:** LDAP integration (future enhancement)

### Q: Should users be created automatically on first login?
**Decision: No, pre-create from Resources.csv**
- **Reason:** Company structure is source of truth, sync-based approach is cleaner
- **Alternative:** JIT provisioning (more complex)

### Q: JWT or Session-based?
**Decision: JWT (refresh token pattern)**
- **Reason:** Better for future mobile app, easier to scale
- **Alternative:** Session cookies (simpler but less scalable)

### Q: One role per user or multiple roles?
**Decision: Primary role only for Phase 1**
- **Reason:** Simpler implementation, Resources.csv has single Team Lead / RM flags
- **Alternative:** Multi-role (future enhancement)

### Q: Where to check permissions - backend only or frontend + backend?
**Decision: Backend enforces, frontend hints**
- **Reason:** Backend is source of truth, frontend is UX optimization

### Q: Support custom roles and manual users?
**Decision: Yes, full admin control**
- **Reason:** Flexibility for contractors, consultants, custom organizational structures
- **Alternative:** Only built-in roles from Resources.csv (too restrictive)

### Q: Should CSV sync remove users?
**Decision: No, sync only adds/updates (add-only)**
- **Reason:** Allows manual user creation without accidental deletion; admins control deactivation
- **Alternative:** Sync removes users not in CSV (risky if CSV is incomplete)

---

## 13. Why JSON Instead of Database?

**Advantages of JSON approach:**
- ✅ No external dependencies (sqlite/postgres)
- ✅ Human-readable and easy to debug
- ✅ Simple backup: just copy JSON files
- ✅ Version control friendly (git diff shows changes clearly)
- ✅ Can be manually edited if needed
- ✅ Consistent with project's current architecture (CSV configs, scheduler_state.json)
- ✅ Fast for ~165 users + admin operations (loads in memory)
- ✅ Easy to migrate later (JSON → Database is straightforward)

**Trade-offs:**
- ❌ Not ideal for millions of users (acceptable for 165+ some buffer)
- ❌ Concurrent writes could overwrite changes (mitigated by atomic write pattern)
- ❌ No built-in query indexes (not needed for this use case)

**When to migrate to database:**
- If user count grows beyond 10,000
- If API request volume requires query optimization
- If need advanced audit logging with queries

---

## 14. Security Considerations

1. **Password Hashing:** bcrypt with salt (never store plaintext)
2. **Token Expiry:** Access token 1 hour, refresh 7 days
3. **Password Reset:** Only admins can reset, users get one-time token
4. **API Key Storage:** Hash API keys like passwords (SHA256)
5. **Rate Limiting:** Add to login endpoint (prevent brute force)
6. **CORS:** Frontend-only access (no public API for auth endpoints)

---

## 15. Initial Setup Process

1. Generate all JSON files from Resources.csv (one-time setup):
   - Create `data/users.json` with all 165 resources + default admin + API user
   - Each user gets an 8-character default password
   - Create `data/role_permissions.json` with role definitions
   - Create `data/api_keys.json` with default API key
2. Users can log in immediately with their default password
3. Users can change password anytime via profile settings
4. Admin can reset passwords for users via admin endpoint

---

## 16. Continuation Plan

**Approval Needed On:**
1. ✅ JSON file structure and locations
2. ✅ Role definitions and permissions matrix
3. ✅ JWT + refresh token pattern
4. ✅ User sync from Resources.csv (add-only)
5. ✅ Default password format (8 chars)
6. ✅ Custom roles and custom users support
7. ✅ Admin UI for user/role management
8. ✅ Implementation phases

**Suggested Implementation Order:**
1. Create Pydantic models for User, Role, Permission
2. Implement password hashing and JWT generation (auth_service.py)
3. Create JSON file handlers (user_service.py with atomic write)
4. Implement role service (role_service.py, custom role CRUD)
5. Implement login endpoint (`POST /api/auth/login`)
6. Create user CRUD endpoints (`POST /api/admin/users`, `PUT`, `DELETE`, `GET`)
7. Create custom role CRUD endpoints (`POST /api/admin/roles`, `PUT`, `DELETE`, `GET`)
8. Create user sync from Resources.csv (`POST /api/admin/users/sync`)
9. Add auth middleware and role/permission decorators
10. Build frontend login page
11. Build user management page (create, edit, delete, list, password reset)
12. Build role management page (create, edit, delete, list permissions)
13. Test end-to-end on local
14. Deploy to remote

---

**Questions for User (Remaining):**
- Should we add email notifications for password resets?
- Should we track login history for auditing?
