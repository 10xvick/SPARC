import json
import urllib.parse
import urllib.request

from app.services.user_service import UserService
from app.services.role_service import RoleService
from app.services.auth_service import AuthService
from app.models.user import TokenData

us = UserService()
rs = RoleService()
a = AuthService()

u = us.get_user_by_sapid('api_user') or us.get_user_by_sapid('admin')
if not u:
    raise SystemExit('No api_user/admin user found')

p = rs.get_permissions_for_role(u.role)
t = a.create_access_token(
    TokenData(
        sub=str(u.id),
        sapid=u.sapid,
        name=u.name,
        role=u.role,
        team_ids=u.team_ids,
        managed_user_ids=u.managed_user_ids,
        permissions=p,
    )
)

for team in ['XHAUL', 'Team XHAUL', 'FSO', 'HCL AION', '']:
    params = {
        'month': '2026-04',
        'team': team,
        'activity_type': 'total_commits',
        'employee_scope': 'active',
    }
    if team == '':
        params.pop('team')

    url = 'http://127.0.0.1:8000/api/reports/git-activity?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {t}'})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode('utf-8', 'replace'))

    print(team or 'ALL', 'rows', len(d.get('data', [])), 'metric', d.get('summary', {}).get('metric_total'), 'cache', d.get('_cache_used'))
