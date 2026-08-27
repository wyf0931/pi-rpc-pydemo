import json
from pathlib import Path

from app.resources import discover_models


def test_discovers_pi_model_catalog(tmp_path: Path):
    (tmp_path / "models.json").write_text(json.dumps({"providers": {
        "example": {"name": "Example Provider", "models": [
            {"id": "example-fast", "name": "Example Fast"},
            {"id": "example-id-only"},
        ]},
        "empty": {"models": []},
    }}), encoding="utf-8")

    assert discover_models(tmp_path) == [{
        "id": "example", "name": "Example Provider", "models": [
            {"id": "example-fast", "name": "Example Fast"},
            {"id": "example-id-only", "name": "example-id-only"},
        ],
    }]
