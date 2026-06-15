import json
from app.api import reports

print("project_root=", str(reports.project_root))
print("cache_file=", str(reports.GIT_ACTIVITY_CACHE_LATEST_FILE))
print("cache_exists=", reports.GIT_ACTIVITY_CACHE_LATEST_FILE.exists())

try:
    cache = reports._load_git_activity_cache()
    print("cache_loaded=", cache is not None)
    if isinstance(cache, dict):
        print("cache_keys=", sorted(list(cache.keys())))
        print("selected_month=", cache.get("selected_month"))
        data = cache.get("data")
        print("data_rows=", len(data) if isinstance(data, list) else "n/a")
except Exception as exc:
    print("cache_error=", repr(exc))
