from pathlib import Path

from setuptools import setup


def _load_requirements(requirements_path: Path) -> list[str]:
    requirements: list[str] = []
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirements.append(line)
    return requirements


ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
DOCS_README = ROOT / "docs" / "README.md"
REQUIREMENTS_FILE = ROOT / "requirements.txt"

py_modules = sorted(path.stem for path in SRC_DIR.glob("*.py") if path.name != "__init__.py")

setup(
    name="teamsight",
    version="3.0.15",
    description="TeamSight KPI evaluator and data fetcher CLI tools",
    long_description=DOCS_README.read_text(encoding="utf-8") if DOCS_README.exists() else "TeamSight",
    long_description_content_type="text/markdown",
    author="TeamSight",
    package_dir={"": "src"},
    py_modules=py_modules,
    install_requires=_load_requirements(REQUIREMENTS_FILE),
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "teamsight-kpi=KppEvaluator:main",
            "teamsight-jira-fetch=jira_fetch:main",
            "teamsight-github-fetch=github_fetch:main",
        ]
    },
    include_package_data=False,
)
