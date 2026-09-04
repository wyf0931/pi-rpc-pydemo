import json
from pathlib import Path

from app.files import (
    delete_chat_files,
    discover_chat_files,
    discover_session_files,
    read_session_messages,
    resolve_chat_file,
)


def test_discovers_only_workspace_files_written_by_chat(tmp_path: Path):
    report = tmp_path / "research" / "report.md"
    report.parent.mkdir()
    report.write_text("# Report", encoding="utf-8")
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    messages = [
        {
            "role": "assistant",
            "timestamp": 1700000000000,
            "content": [
                {
                    "type": "toolCall",
                    "name": "write",
                    "arguments": {"path": "research/report.md"},
                },
                {
                    "type": "toolCall",
                    "name": "write",
                    "arguments": {"path": str(outside)},
                },
            ],
        }
    ]

    files = discover_chat_files(messages, tmp_path)

    assert [item["path"] for item in files] == ["research/report.md"]
    assert (
        resolve_chat_file(messages, tmp_path, "research/report.md") == report.resolve()
    )
    assert resolve_chat_file(messages, tmp_path, "../outside.md") is None
    assert delete_chat_files(messages, tmp_path, {"research/report.md"}) == []


def test_discovers_files_from_session_jsonl_without_starting_pi(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text("# Report", encoding="utf-8")
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps(
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "timestamp": 1700000000000,
                    "content": [
                        {
                            "type": "toolCall",
                            "name": "write",
                            "arguments": {"path": "report.md"},
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert len(read_session_messages(session)) == 1
    assert discover_session_files(session, tmp_path)[0]["path"] == "report.md"
