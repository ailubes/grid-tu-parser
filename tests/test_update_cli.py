import os
import subprocess
import sys
from pathlib import Path


def test_update_cli_requires_database_url_before_importing_driver():
    script = Path(__file__).parents[1] / "scripts" / "update_grid_data.py"
    env = dict(os.environ)
    env.pop("DATABASE_URL", None)
    completed = subprocess.run(
        [sys.executable, str(script), "--base-url", "https://example.test"],
        cwd=Path(__file__).parents[1],
        env=env,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 2
    assert "DATABASE_URL" in completed.stderr


def test_update_cli_help_works_without_database_driver():
    script = Path(__file__).parents[1] / "scripts" / "update_grid_data.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=Path(__file__).parents[1],
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0
    assert "daily grid tu pipeline" in completed.stdout.lower()
