from pathlib import Path


def test_daily_workflow_uses_secret_runs_tests_and_pipeline():
    path = Path('.github/workflows/update-grid-data.yml')
    text = path.read_text(encoding='utf-8')
    lowered = text.lower()

    assert 'cron: "0 0 * * *"' in text or "cron: '0 0 * * *'" in text
    assert 'workflow_dispatch:' in text
    assert 'pull_request:' in text
    assert 'secrets.DATABASE_URL' in text
    assert 'pytest' in text
    assert 'python scripts/update_grid_data.py' in text
    assert "if: github.event_name != 'pull_request'" in text
    assert 'supabase.co' not in lowered
    assert 'postgresql://postgres:' not in lowered


def test_project_declares_psycopg_runtime_dependency():
    pyproject = Path('pyproject.toml').read_text(encoding='utf-8')
    assert 'psycopg[binary]' in pyproject
