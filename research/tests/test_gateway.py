import json
from pathlib import Path

from microprice import gateway


def test_json_response_serves_files_and_404s(tmp_path: Path) -> None:
    path = tmp_path / "holdout.json"
    path.write_text(json.dumps({"sessions": []}))
    ok = gateway.json_response(path)
    assert ok.status_code == 200
    assert ok.headers["Content-Type"] == "application/json"
    assert json.loads(ok.body) == {"sessions": []}
    assert gateway.json_response(tmp_path / "missing.json").status_code == 404
