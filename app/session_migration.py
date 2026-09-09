"""Safe, one-time normalization of Pi session project paths."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def migrate_session_cwds(
    session_dir: Path, legacy_cwd: str | None, current_cwd: str
) -> int:
    """Rewrite only matching session headers, preserving transcript content.

    Each changed JSONL file gets an adjacent backup and is replaced atomically.
    The migration is idempotent because already-normalized headers no longer
    match ``legacy_cwd``.
    """
    if not legacy_cwd or legacy_cwd == current_cwd or not session_dir.is_dir():
        return 0
    changed = 0
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for path in sorted(session_dir.glob("*.jsonl")):
        try:
            original = path.read_bytes()
            first, separator, remainder = original.partition(b"\n")
            header = json.loads(first.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if header.get("type") != "session" or header.get("cwd") != legacy_cwd:
            continue
        header["cwd"] = current_cwd
        replacement = json.dumps(
            header, ensure_ascii=False, separators=(",", ":")
        ).encode()
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        backup_path = path.with_name(f"{path.name}.{stamp}.legacy-cwd.bak")
        if backup_path.exists():
            backup_path = path.with_name(
                f"{path.name}.{stamp}.{uuid4().hex}.legacy-cwd.bak"
            )
        try:
            temp_path.write_bytes(replacement + (separator or b"\n") + remainder)
            os.replace(path, backup_path)
            os.replace(temp_path, path)
        except OSError:
            temp_path.unlink(missing_ok=True)
            if backup_path.exists() and not path.exists():
                os.replace(backup_path, path)
            raise
        changed += 1
    return changed
