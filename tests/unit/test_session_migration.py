import json
from pathlib import Path

from app.session_migration import migrate_session_cwds


def test_migrate_session_cwd_preserves_transcript_and_creates_backup(tmp_path: Path):
    session = tmp_path / "session.jsonl"
    header = {
        "type": "session",
        "version": 3,
        "id": "session-1",
        "cwd": "/old/workspace",
    }
    body = {"type": "message", "message": {"role": "user", "content": "hello"}}
    session.write_text(
        json.dumps(header) + "\n" + json.dumps(body) + "\n", encoding="utf-8"
    )

    assert migrate_session_cwds(tmp_path, "/old/workspace", "/workspace") == 1
    lines = session.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["cwd"] == "/workspace"
    assert json.loads(lines[1]) == body
    backups = list(tmp_path.glob("session.jsonl.*.legacy-cwd.bak"))
    assert len(backups) == 1
    assert (
        json.loads(backups[0].read_text(encoding="utf-8").splitlines()[0])["cwd"]
        == "/old/workspace"
    )

    assert migrate_session_cwds(tmp_path, "/old/workspace", "/workspace") == 0
    assert len(list(tmp_path.glob("session.jsonl.*.legacy-cwd.bak"))) == 1


def test_migrate_session_cwd_ignores_unrelated_and_malformed_files(tmp_path: Path):
    (tmp_path / "unrelated.jsonl").write_text(
        json.dumps({"type": "session", "cwd": "/other"}) + "\n", encoding="utf-8"
    )
    (tmp_path / "broken.jsonl").write_text("not json\n", encoding="utf-8")

    assert migrate_session_cwds(tmp_path, "/old", "/workspace") == 0
    assert not list(tmp_path.glob("*.legacy-cwd.bak"))
