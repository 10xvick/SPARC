#!/usr/bin/env python3
"""
JIRA Epic Tree cache generation job.

Creates precomputed CSV/JSON files under output/EpicTree:
- epics.csv (list screen data)
- one CSV per epic for Epic Insights workspace data
- transitions/<issue_key>.json per issue for fast Issue Transition History display
"""

import argparse
import importlib.util
import sys
from pathlib import Path

from KppEvaluator import _resolve_project_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate precomputed CSV cache for JIRA Epic Tree report"
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="TeamSight project root containing config/ and output/",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Target EpicTree output folder (default: <project-root>/output/EpicTree)",
    )

    args = parser.parse_args()
    project_root = _resolve_project_root(args.project_root)

    backend_root = project_root / "dashboard" / "backend"
    if not backend_root.exists():
        print(f"Epic Tree cache job failed: backend path not found at {backend_root}")
        return 1

    reports_module_path = backend_root / "app" / "api" / "reports.py"
    if not reports_module_path.exists():
        print(f"Epic Tree cache job failed: reports module missing at {reports_module_path}")
        return 1

    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    spec = importlib.util.spec_from_file_location("teamsight_reports_module", reports_module_path)
    if spec is None or spec.loader is None:
        print("Epic Tree cache job failed: unable to create module spec for reports API")
        return 1

    reports_module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(reports_module)
    except Exception as exc:
        print(f"Epic Tree cache job failed: unable to load reports module: {exc}")
        return 1

    generate_jira_epic_tree_cache = getattr(reports_module, "generate_jira_epic_tree_cache", None)
    if not callable(generate_jira_epic_tree_cache):
        print("Epic Tree cache job failed: generate_jira_epic_tree_cache is unavailable")
        return 1

    output_dir = None
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()

    try:
        print("[EpicTreeCacheJob] starting cache generation", flush=True)
        result = generate_jira_epic_tree_cache(
            project_root=project_root,
            output_dir=output_dir,
            show_progress=True,
        )
    except Exception as exc:
        print(f"Epic Tree cache job failed: {exc}")
        return 1

    print(
        "Epic Tree cache generated successfully "
        f"(epics={result.get('epic_count', 0)}, "
        f"workspace_files={result.get('workspace_file_count', 0)}, "
        f"output_dir={result.get('output_dir', '')})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
