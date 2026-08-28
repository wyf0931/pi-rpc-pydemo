from pathlib import Path

from app.files import discover_chat_files, resolve_chat_file


def test_discovers_only_workspace_files_written_by_chat(tmp_path: Path):
    report = tmp_path / "research" / "report.md"
    report.parent.mkdir()
    report.write_text("# Report", encoding="utf-8")
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    messages = [{
        "role": "assistant",
        "timestamp": 1700000000000,
        "content": [
            {"type": "toolCall", "name": "write", "arguments": {"path": "research/report.md"}},
            {"type": "toolCall", "name": "write", "arguments": {"path": str(outside)}},
        ],
    }]

    files = discover_chat_files(messages, tmp_path)

    assert [item["path"] for item in files] == ["research/report.md"]
    assert resolve_chat_file(messages, tmp_path, "research/report.md") == report.resolve()
    assert resolve_chat_file(messages, tmp_path, "../outside.md") is None
