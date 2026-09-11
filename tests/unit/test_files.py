import json
from pathlib import Path

from app.files import (
    delete_chat_files,
    discover_chat_files,
    discover_session_files,
    native_browser_headers,
    native_browser_media_type,
    read_session_messages,
    resolve_chat_file,
)


def test_native_svg_view_falls_back_to_plain_text_when_xml_is_malformed(tmp_path: Path):
    valid = tmp_path / "valid.svg"
    valid.write_text('<svg xmlns="http://www.w3.org/2000/svg"><desc>ok</desc></svg>')
    malformed = tmp_path / "malformed.svg"
    malformed.write_text("<svg><desc>broken</svg></desc>")

    assert native_browser_media_type(valid) == "image/svg+xml"
    assert (
        native_browser_headers("image/svg+xml")["Content-Security-Policy"] == "sandbox"
    )
    assert native_browser_media_type(malformed) == "text/plain"
    assert "Content-Security-Policy" not in native_browser_headers("text/plain")


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


def test_discovers_files_explicitly_published_by_chat(tmp_path: Path):
    report = tmp_path / "anthropic_news.csv"
    report.write_text("title,link\n", encoding="utf-8")
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "toolCall",
                    "name": "publish_artifact",
                    "arguments": {"path": "anthropic_news.csv"},
                }
            ],
        }
    ]

    assert discover_chat_files(messages, tmp_path)[0]["path"] == "anthropic_news.csv"


def test_discovers_images_created_by_image_tools(tmp_path: Path):
    image = tmp_path / "generated" / "chat-1" / "image.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"png")
    messages = [
        {
            "role": "toolResult",
            "toolName": "generate_image",
            "timestamp": 1700000000000,
            "details": {"path": "generated/chat-1/image.png"},
        }
    ]

    assert (
        discover_chat_files(messages, tmp_path)[0]["path"]
        == "generated/chat-1/image.png"
    )
    assert (
        resolve_chat_file(messages, tmp_path, "generated/chat-1/image.png")
        == image.resolve()
    )


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
