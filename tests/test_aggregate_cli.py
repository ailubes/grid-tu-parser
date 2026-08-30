import csv
import json
import subprocess
import sys
from pathlib import Path


def test_aggregate_cli_reads_parsed_json_and_writes_node_csv(tmp_path: Path):
    input_path = tmp_path / "parsed.json"
    output_path = tmp_path / "nodes.csv"
    input_path.write_text(json.dumps([
        {
            "source": "test",
            "source_url": "https://example.test",
            "source_page": 1,
            "fetched_at": "2026-08-30T00:00:00+00:00",
            "tu_number": "1",
            "tu_date": "2026-08-01",
            "installation_type": "Виробництво",
            "activity_type": "generation",
            "requested_power_kw": 2500,
            "connection_type": "нестандартне",
            "rem": "TEST",
            "connection_point_raw": "PS-A",
            "voltage_raw": "10",
            "canonical_node_id": "PS-A",
            "confidence": 0.95,
            "needs_review": False,
            "flags": [],
        },
        {
            "source": "test",
            "source_url": "https://example.test",
            "source_page": 1,
            "fetched_at": "2026-08-30T00:00:00+00:00",
            "tu_number": "2",
            "tu_date": "2026-08-02",
            "installation_type": "Споживання",
            "activity_type": "consumption",
            "requested_power_kw": 500,
            "connection_type": "нестандартне",
            "rem": "TEST",
            "connection_point_raw": "PS-A",
            "voltage_raw": "10",
            "canonical_node_id": "PS-A",
            "confidence": 0.9,
            "needs_review": True,
            "flags": ["example"],
        },
    ], ensure_ascii=False), encoding="utf-8")

    script = Path(__file__).parents[1] / "scripts" / "aggregate_nodes.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--input", str(input_path), "--output", str(output_path), "--as-of", "2026-08-30"],
        cwd=Path(__file__).parents[1],
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    rows = list(csv.DictReader(output_path.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["canonical_node_id"] == "PS-A"
    assert float(rows[0]["generation_mw"]) == 2.5
    assert float(rows[0]["load_mw"]) == 0.5
    assert int(rows[0]["review_count"]) == 1
    assert "generation_pressure" in rows[0]
