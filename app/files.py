import json
from datetime import UTC, datetime
from pathlib import Path

MAX_VIEW_BYTES = 5 * 1024 * 1024


def _tool_arguments(part: dict) -> dict:
    arguments = part.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    return {}


def _timestamp(value: object, fallback: float) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
    return datetime.fromtimestamp(fallback, tz=UTC).isoformat()


def discover_chat_files(messages: list[dict], workspace: Path) -> list[dict]:
    root = workspace.expanduser().resolve()
    files: dict[str, dict] = {}
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for part in message.get("content") or []:
            if part.get("type") != "toolCall" or part.get("name") not in {
                "write",
                "edit",
            }:
                continue
            arguments = _tool_arguments(part)
            raw_path = arguments.get("path") or arguments.get("file_path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            candidate = Path(raw_path).expanduser()
            resolved = (
                candidate if candidate.is_absolute() else root / candidate
            ).resolve()
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                continue
            if not resolved.is_file():
                continue
            stat = resolved.stat()
            files[str(resolved)] = {
                "id": str(relative),
                "name": resolved.name,
                "path": str(relative),
                "generated_at": _timestamp(message.get("timestamp"), stat.st_mtime),
                "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                "size": stat.st_size,
                "extension": resolved.suffix.lower().lstrip("."),
            }
    return sorted(files.values(), key=lambda item: item["generated_at"], reverse=True)


def read_session_messages(session_path: Path) -> list[dict]:
    """Read message records directly from a Pi JSONL session transcript."""
    messages: list[dict] = []
    try:
        lines = session_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return messages
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = record.get("message")
        if isinstance(message, dict):
            messages.append(message)
    return messages


def discover_session_files(session_path: Path, workspace: Path) -> list[dict]:
    """Discover generated files without starting Pi or invoking RPC."""
    return discover_chat_files(read_session_messages(session_path), workspace)


def resolve_chat_file(
    messages: list[dict], workspace: Path, relative_path: str
) -> Path | None:
    match = next(
        (
            item
            for item in discover_chat_files(messages, workspace)
            if item["path"] == relative_path
        ),
        None,
    )
    if not match:
        return None
    resolved = (workspace.expanduser().resolve() / match["path"]).resolve()
    try:
        resolved.relative_to(workspace.expanduser().resolve())
    except ValueError:
        return None
    if not resolved.is_file() or resolved.stat().st_size > MAX_VIEW_BYTES:
        return None
    return resolved


def delete_chat_files(
    messages: list[dict], workspace: Path, protected_paths: set[str] | None = None
) -> list[str]:
    deleted: list[str] = []
    protected_paths = protected_paths or set()
    for item in discover_chat_files(messages, workspace):
        if item["path"] in protected_paths:
            continue
        file_path = (workspace.expanduser().resolve() / item["path"]).resolve()
        try:
            file_path.relative_to(workspace.expanduser().resolve())
        except ValueError:
            continue
        try:
            file_path.unlink()
            deleted.append(item["path"])
        except OSError:
            continue
    return deleted
