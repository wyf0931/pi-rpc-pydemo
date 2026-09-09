"""SQLite engine configuration and one-time TinyDB JSON migration."""

import json
import os
import shutil
import sqlite3
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from .storage_models import TABLE_MODELS

SCHEMA_VERSION = 2
SCHEMA_ALTERS = {
    "agents": {
        "description": "TEXT",
        "tags_json": "TEXT NOT NULL DEFAULT '[]'",
        "quickstarts_json": "TEXT NOT NULL DEFAULT '[]'",
    }
}
T = TypeVar("T", bound=SQLModel)
JSON_FIELDS = {
    "extensions": "extensions_json",
    "skills": "skills_json",
    "tools": "tools_json",
    "mcp_servers": "mcp_servers_json",
    "tags": "tags_json",
    "quickstarts": "quickstarts_json",
    "version_sort": "version_sort_json",
    "content": "content_json",
}
MODEL_FIELDS = {name: set(model.model_fields) for name, model in TABLE_MODELS.items()}


def _schema_needs_upgrade(path: Path) -> bool:
    if not path.exists():
        return False
    connection = sqlite3.connect(path)
    try:
        try:
            version = int(
                connection.execute(
                    "SELECT value FROM schema_meta WHERE key='version'"
                ).fetchone()[0]
            )
        except (TypeError, ValueError, sqlite3.OperationalError):
            version = 0
        existing = {row[1] for row in connection.execute("PRAGMA table_info(agents)")}
        return version < SCHEMA_VERSION or any(
            column not in existing for column in SCHEMA_ALTERS["agents"]
        )
    finally:
        connection.close()


def _backup_before_schema_upgrade(path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.schema-v{SCHEMA_VERSION}.{stamp}.bak")
    if backup.exists():
        backup = path.with_name(
            f"{path.name}.schema-v{SCHEMA_VERSION}.{stamp}.{uuid4().hex}.bak"
        )
    temporary = path.with_name(f".{backup.name}.{uuid4().hex}.tmp")
    source = sqlite3.connect(path)
    destination = sqlite3.connect(temporary)
    try:
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()
    os.replace(temporary, backup)
    return backup


def create_sqlite_engine(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if _schema_needs_upgrade(path):
        _backup_before_schema_upgrade(path)
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection: sqlite3.Connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_meta "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        for table, columns in SCHEMA_ALTERS.items():
            existing = {
                row[1]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            for column, definition in columns.items():
                if column not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                    )
        connection.exec_driver_sql(
            "INSERT INTO schema_meta(key, value) VALUES ('version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
    return engine


def _json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def to_row(table: str, record: dict[str, Any]) -> dict[str, Any]:
    fields = MODEL_FIELDS[table]
    values: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    for key, value in record.items():
        column = JSON_FIELDS.get(key, key)
        if column in fields:
            values[column] = _json_value(value) if key in JSON_FIELDS else value
        else:
            extras[key] = value
    values["extra_json"] = _json_value(extras)
    return values


def from_row(row: SQLModel) -> dict[str, Any]:
    values = row.model_dump()
    extras = json.loads(values.pop("extra_json", "{}") or "{}")
    for key, column in JSON_FIELDS.items():
        if column in values:
            raw = values.pop(column)
            values[key] = json.loads(raw or ("[]" if key != "content" else "{}"))
    values.update(extras)
    return values


def _legacy_records(path: Path) -> dict[str, list[dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, list[dict[str, Any]]] = {}
    for table in TABLE_MODELS:
        table_data = raw.get(table, {})
        result[table] = (
            list(table_data.values()) if isinstance(table_data, dict) else []
        )
    return result


def validate_tinydb_source(path: Path, *, strict: bool = False) -> dict[str, int]:
    """Validate a legacy file without creating or modifying any database."""
    records = _legacy_records(path)
    _validate_records(records, strict=strict)
    return {table: len(items) for table, items in records.items()}


def _validate_records(
    records: dict[str, list[dict[str, Any]]], *, strict: bool = False
) -> None:
    seen: dict[str, set[str]] = {}
    for table, items in records.items():
        model = TABLE_MODELS[table]
        keys = set()
        for item in items:
            prepared = to_row(table, item)
            key = prepared.get(
                "token"
                if table == "shares"
                else "key"
                if table == "system_settings"
                else "id"
            )
            if key in keys:
                raise ValueError(f"duplicate primary key in {table}: {key}")
            keys.add(key)
            model(**prepared)
        seen[table] = keys

    relations = (
        ("agents", "user_id", "users"),
        ("chats", "user_id", "users"),
        ("chats", "agent_id", "agents"),
        ("autopilots", "user_id", "users"),
        ("autopilots", "agent_id", "agents"),
        ("autopilot_runs", "user_id", "users"),
        ("autopilot_runs", "autopilot_id", "autopilots"),
        ("autopilot_runs", "chat_id", "chats"),
        ("shares", "user_id", "users"),
        ("shares", "chat_id", "chats"),
        ("sessions", "user_id", "users"),
        ("agent_publications", "source_agent_id", "agents"),
        ("agent_publications", "owner_user_id", "users"),
        ("agent_publication_versions", "publication_id", "agent_publications"),
    )
    for table, field, target in relations:
        for item in records[table]:
            value = item.get(field)
            if value is not None and value not in seen[target]:
                message = f"invalid relation {table}.{field}={value}"
                if strict:
                    raise ValueError(message)
                warnings.warn(
                    message + "; preserving legacy record", RuntimeWarning, stacklevel=2
                )


def migrate_tinydb(
    tinydb_path: Path,
    sqlite_path: Path,
    *,
    backup_dir: Path | None = None,
    strict: bool = False,
) -> Path | None:
    """Migrate once, atomically. Returns backup path when migration occurred."""
    if sqlite_path.exists():
        return None
    if not tinydb_path.exists():
        create_sqlite_engine(sqlite_path).dispose()
        return None

    records = _legacy_records(tinydb_path)
    _validate_records(records, strict=strict)
    temp_path = sqlite_path.with_name(f".{sqlite_path.name}.{uuid4().hex}.tmp")
    backup_root = backup_dir or tinydb_path.parent
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_root / f"{tinydb_path.name}.{stamp}.bak"
    engine = None
    try:
        engine = create_sqlite_engine(temp_path)
        with Session(engine) as session:
            for table, items in records.items():
                model = TABLE_MODELS[table]
                for item in items:
                    session.add(model(**to_row(table, item)))
            session.commit()
            for table, model in TABLE_MODELS.items():
                actual = len(session.exec(select(model)).all())
                if actual != len(records[table]):
                    raise ValueError(f"migration count mismatch for {table}")
        engine.dispose()
        shutil.copy2(tinydb_path, backup_path)
        temp_path.replace(sqlite_path)
        return backup_path
    except Exception:
        if engine is not None:
            engine.dispose()
        temp_path.unlink(missing_ok=True)
        backup_path.unlink(missing_ok=True)
        raise
