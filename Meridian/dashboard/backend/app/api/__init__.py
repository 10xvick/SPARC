"""
API routes package initialization.

Deliberately empty — routers are imported directly in main.py.
Eager re-exports here caused transitive UploadFile imports (employees.py,
roles.py) which trigger FastAPI's python-multipart check even in non-web
contexts such as jira_epic_tree_cache_job loading reports.py via importlib.
"""

