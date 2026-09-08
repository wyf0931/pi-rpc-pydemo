import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from .auth import hash_password, new_session_token, session_digest
from .storage import create_sqlite_engine, from_row, migrate_tinydb, to_row
from .storage_models import TABLE_MODELS

DEFAULT_TOOLS = ["read", "write", "edit", "bash"]
BUILTIN_TOOLS = DEFAULT_TOOLS + ["grep", "find", "ls"]
PLATFORM_TOOLS = ["web_fetch", "web_search", "publish_artifact"]
SUPPORTED_TOOLS = BUILTIN_TOOLS + PLATFORM_TOOLS


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def pi_terminal_failure(messages: list[dict]) -> str | None:
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        reason = message.get("stopReason")
        if reason not in {"aborted", "error"}:
            return None
        return message.get("errorMessage") or (
            "The agent turn was aborted before a final answer was generated."
            if reason == "aborted"
            else "The agent turn failed before a final answer was generated."
        )
    return None


class Store:
    """Dictionary-compatible metadata store backed by SQLModel/SQLite."""

    def __init__(self, path: Path):
        self.legacy_path = (
            path if path.suffix != ".sqlite3" else path.with_name("platform.json")
        )
        self.sqlite_path = (
            path if path.suffix == ".sqlite3" else path.with_name("platform.sqlite3")
        )
        migrate_tinydb(self.legacy_path, self.sqlite_path)
        self.engine = create_sqlite_engine(self.sqlite_path)

    def close(self) -> None:
        self.engine.dispose()

    @staticmethod
    def public_user(user: dict) -> dict:
        return {key: value for key, value in user.items() if key != "password_hash"}

    def _all(self, table: str) -> list[dict]:
        model = TABLE_MODELS[table]
        with Session(self.engine) as session:
            return [from_row(row) for row in session.exec(select(model)).all()]

    def _find(self, table: str, predicate: Callable[[dict], bool]) -> dict | None:
        return next((item for item in self._all(table) if predicate(item)), None)

    def _insert(self, table: str, values: dict[str, Any]) -> dict:
        model = TABLE_MODELS[table]
        with Session(self.engine) as session:
            session.add(model(**to_row(table, values)))
            session.commit()
        return values

    def _update(
        self, table: str, predicate: Callable[[dict], bool], values: dict
    ) -> int:
        model = TABLE_MODELS[table]
        with Session(self.engine) as session:
            changed = 0
            for row in session.exec(select(model)).all():
                item = from_row(row)
                if predicate(item):
                    item.update(values)
                    for key, value in to_row(table, item).items():
                        setattr(row, key, value)
                    session.add(row)
                    changed += 1
            session.commit()
            return changed

    def _remove(self, table: str, predicate: Callable[[dict], bool]) -> int:
        model = TABLE_MODELS[table]
        with Session(self.engine) as session:
            removed = 0
            for row in session.exec(select(model)).all():
                if predicate(from_row(row)):
                    session.delete(row)
                    removed += 1
            session.commit()
            return removed

    def ensure_default_user(self, password: str) -> dict:
        user = self.get_user_by_username("admin")
        if user:
            return user
        user = {
            "id": str(uuid4()),
            "username": "admin",
            "email": None,
            "password_hash": hash_password(password),
            "role": "admin",
            "status": "active",
            "created_at": now_iso(),
            "last_login_at": None,
        }
        self._insert("users", user)
        return user

    def list_users(self) -> list[dict]:
        return [self.public_user(user) for user in self._all("users")]

    def get_system_setting(self, key: str, default: str) -> str:
        record = self._find("system_settings", lambda item: item.get("key") == key)
        return record.get("value", default) if record else default

    def set_system_setting(self, key: str, value: str) -> str:
        if self._update(
            "system_settings", lambda item: item.get("key") == key, {"value": value}
        ):
            return value
        self._insert("system_settings", {"key": key, "value": value})
        return value

    def get_user(self, user_id: str) -> dict | None:
        return self._find("users", lambda item: item.get("id") == user_id)

    def get_user_by_username(self, username: str) -> dict | None:
        return self._find("users", lambda item: item.get("username") == username)

    def create_user(self, username: str, email: str | None, password: str) -> dict:
        user = {
            "id": str(uuid4()),
            "username": username.strip(),
            "email": email.strip() if email else None,
            "password_hash": hash_password(password),
            "role": "normal",
            "status": "active",
            "created_at": now_iso(),
            "last_login_at": None,
        }
        self._insert("users", user)
        return user

    def update_user_status(self, user_id: str, status: str) -> dict | None:
        self._update(
            "users", lambda item: item.get("id") == user_id, {"status": status}
        )
        return self.get_user(user_id)

    def delete_user(self, user_id: str) -> bool:
        self._remove("sessions", lambda item: item.get("user_id") == user_id)
        return bool(self._remove("users", lambda item: item.get("id") == user_id))

    def create_session(self, user_id: str, expires_at: str) -> str:
        token = new_session_token()
        self._insert(
            "sessions",
            {
                "id": str(uuid4()),
                "token_hash": session_digest(token),
                "user_id": user_id,
                "created_at": now_iso(),
                "expires_at": expires_at,
            },
        )
        return token

    def get_session_user(self, token: str) -> dict | None:
        session = self._find(
            "sessions", lambda item: item.get("token_hash") == session_digest(token)
        )
        if not session:
            return None
        if session.get("expires_at", "") <= now_iso():
            self._remove("sessions", lambda item: item.get("id") == session.get("id"))
            return None
        return self.get_user(session["user_id"])

    def delete_session(self, token: str) -> None:
        self._remove(
            "sessions", lambda item: item.get("token_hash") == session_digest(token)
        )

    def mark_user_login(self, user_id: str) -> dict | None:
        self._update(
            "users",
            lambda item: item.get("id") == user_id,
            {"last_login_at": now_iso()},
        )
        return self.get_user(user_id)

    @staticmethod
    def agent_config(agent: dict) -> dict:
        return {
            key: agent.get(key)
            for key in (
                "name",
                "instruction",
                "provider",
                "model",
                "thinking_level",
                "tools",
                "extensions",
                "skills",
                "mcp_servers",
            )
        }

    @classmethod
    def agent_content_hash(cls, agent: dict) -> str:
        payload = json.dumps(
            cls.agent_config(agent),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    def ensure_default_agent(self, default_tools: list[str] | None = None) -> dict:
        agent = self.get_agent("default-assistant")
        if agent:
            values = {}
            if "tools_configured" not in agent or "provider" not in agent:
                values = {
                    "tools": agent.get("tools") or default_tools or [],
                    "tools_configured": True,
                    "provider": agent.get("provider"),
                }
            if values:
                self._update(
                    "agents", lambda item: item.get("id") == agent["id"], values
                )
                agent.update(values)
            agent.setdefault("avatar_path", None)
            return agent
        item = {
            "id": "default-assistant",
            "name": "assistant",
            "instruction": "Be helpful, clear, and concise.",
            "provider": None,
            "model": None,
            "thinking_level": None,
            "extensions": [],
            "skills": [],
            "tools": default_tools or [],
            "tools_configured": True,
            "mcp_servers": [],
            "avatar_path": None,
            "protected": True,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        self._insert("agents", item)
        return item

    def list_agents(self) -> list[dict]:
        return self._all("agents")

    def get_agent(self, agent_id: str) -> dict | None:
        return self._find("agents", lambda item: item.get("id") == agent_id)

    def create_agent(
        self,
        name: str,
        instruction: str,
        provider: str | None = None,
        model: str | None = None,
        tools: list[str] | None = None,
        extensions: list[str] | None = None,
        skills: list[str] | None = None,
        mcp_servers: list[str] | None = None,
        thinking_level: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        item = {
            "id": str(uuid4()),
            "name": name.strip(),
            "instruction": instruction.strip(),
            "provider": provider,
            "model": model,
            "extensions": extensions or [],
            "skills": skills or [],
            "thinking_level": thinking_level,
            "tools": tools or [],
            "tools_configured": True,
            "mcp_servers": mcp_servers or [],
            "avatar_path": None,
            "protected": False,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        if user_id:
            item["user_id"] = user_id
        item["content_hash"] = self.agent_content_hash(item)
        self._insert("agents", item)
        return item

    def update_agent(self, agent_id: str, values: dict) -> dict | None:
        values = {k: v for k, v in values.items() if v is not None}
        if "tools" in values:
            values["tools_configured"] = True
        values["updated_at"] = now_iso()
        if not self._update("agents", lambda item: item.get("id") == agent_id, values):
            return None
        agent = self.get_agent(agent_id)
        if agent:
            content_hash = self.agent_content_hash(agent)
            self._update(
                "agents",
                lambda item: item.get("id") == agent_id,
                {"content_hash": content_hash},
            )
            agent["content_hash"] = content_hash
        return agent

    def list_agent_publications(self) -> list[dict]:
        publications = []
        for publication in self._all("agent_publications"):
            versions = [
                v
                for v in self._all("agent_publication_versions")
                if v.get("publication_id") == publication["id"]
            ]
            if not versions:
                continue
            latest = max(versions, key=lambda item: tuple(item["version_sort"]))
            author = self.get_user(publication["owner_user_id"])
            publications.append(
                {
                    **publication,
                    "latest_version": latest["version"],
                    "latest_hash": latest["content_hash"],
                    "latest": latest,
                    "author_username": author.get("username", "admin")
                    if author
                    else "admin",
                }
            )
        return sorted(
            publications, key=lambda item: item.get("updated_at", ""), reverse=True
        )

    def get_agent_publication(self, publication_id: str) -> dict | None:
        publication = self._find(
            "agent_publications", lambda item: item.get("id") == publication_id
        )
        if not publication:
            return None
        versions = [
            v
            for v in self._all("agent_publication_versions")
            if v.get("publication_id") == publication_id
        ]
        if not versions:
            return None
        latest = max(versions, key=lambda item: tuple(item["version_sort"]))
        author = self.get_user(publication["owner_user_id"])
        return {
            **publication,
            "latest_version": latest["version"],
            "latest_hash": latest["content_hash"],
            "latest": latest,
            "author_username": author.get("username", "admin") if author else "admin",
        }

    def has_agent_publication_version(self, publication_id: str, version: str) -> bool:
        return bool(
            self._find(
                "agent_publication_versions",
                lambda item: (
                    item.get("publication_id") == publication_id
                    and item.get("version") == version
                ),
            )
        )

    def publish_agent(self, agent: dict, owner_user_id: str, version: str) -> dict:
        content, content_hash, timestamp = (
            self.agent_config(agent),
            self.agent_content_hash(agent),
            now_iso(),
        )
        publication = self._find(
            "agent_publications",
            lambda item: (
                item.get("owner_user_id") == owner_user_id
                and item.get("source_agent_id") == agent["id"]
            ),
        )
        if not publication:
            publication = {
                "id": str(uuid4()),
                "source_agent_id": agent["id"],
                "owner_user_id": owner_user_id,
                "name": agent["name"],
                "description": agent["instruction"],
                "install_count": 0,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            self._insert("agent_publications", publication)
        else:
            self._update(
                "agent_publications",
                lambda item: item.get("id") == publication["id"],
                {
                    "name": agent["name"],
                    "description": agent["instruction"],
                    "updated_at": timestamp,
                },
            )
        self._insert(
            "agent_publication_versions",
            {
                "id": str(uuid4()),
                "publication_id": publication["id"],
                "version": version,
                "version_sort": [int(part) for part in version[1:].split(".")],
                "content": content,
                "content_hash": content_hash,
                "created_at": timestamp,
            },
        )
        return self.get_agent_publication(publication["id"]) or publication

    def install_agent_publication(
        self, publication_id: str, owner_user_id: str, version: str | None = None
    ) -> dict | None:
        publication = self.get_agent_publication(publication_id)
        if not publication:
            return None
        target = publication["latest"]
        if version:
            target = self._find(
                "agent_publication_versions",
                lambda item: (
                    item.get("publication_id") == publication_id
                    and item.get("version") == version
                ),
            )
            if not target:
                return None
        timestamp = now_iso()
        agent = {
            "id": str(uuid4()),
            **target["content"],
            "user_id": owner_user_id,
            "tools_configured": True,
            "avatar_path": None,
            "protected": False,
            "created_at": timestamp,
            "updated_at": timestamp,
            "content_hash": target["content_hash"],
            "source_publication_id": publication_id,
            "source_version": target["version"],
            "source_hash": target["content_hash"],
        }
        self._insert("agents", agent)
        self._update(
            "agent_publications",
            lambda item: item.get("id") == publication_id,
            {"install_count": int(publication.get("install_count", 0)) + 1},
        )
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        agent = self.get_agent(agent_id)
        return bool(
            agent
            and not agent.get("protected")
            and self._remove("agents", lambda item: item.get("id") == agent_id)
        )

    def list_chats(self) -> list[dict]:
        return sorted(
            self._all("chats"),
            key=lambda x: x.get("last_activity_at", ""),
            reverse=True,
        )

    def get_chat(self, chat_id: str) -> dict | None:
        return self._find("chats", lambda item: item.get("id") == chat_id)

    def create_chat(
        self,
        agent_id: str,
        session_id: str | None = None,
        status: str = "starting",
        user_id: str | None = None,
    ) -> dict:
        timestamp, chat_id = now_iso(), str(uuid4())
        item = {
            "id": chat_id,
            "session_id": session_id or chat_id,
            "agent_id": agent_id,
            "title": "New conversation",
            "status": status,
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_activity_at": timestamp,
        }
        if user_id:
            item["user_id"] = user_id
        self._insert("chats", item)
        return item

    def create_autopilot_chat(
        self, agent_id: str, title: str, user_id: str | None = None
    ) -> dict:
        chat = self.create_chat(agent_id, status="starting", user_id=user_id)
        return self.update_chat(chat["id"], {"title": title}) or chat

    def update_chat(self, chat_id: str, values: dict) -> dict | None:
        values = {**values, "updated_at": now_iso()}
        return (
            self.get_chat(chat_id)
            if self._update("chats", lambda item: item.get("id") == chat_id, values)
            else None
        )

    def delete_chat(self, chat_id: str) -> bool:
        self._remove("shares", lambda item: item.get("chat_id") == chat_id)
        self._remove("uploads", lambda item: item.get("chat_id") == chat_id)
        return bool(self._remove("chats", lambda item: item.get("id") == chat_id))

    def create_upload(self, values: dict) -> dict:
        item = {**values, "created_at": now_iso()}
        self._insert("uploads", item)
        return item

    def get_upload(self, upload_id: str) -> dict | None:
        return self._find("uploads", lambda item: item.get("id") == upload_id)

    def list_uploads(self, chat_id: str) -> list[dict]:
        return sorted(
            [x for x in self._all("uploads") if x.get("chat_id") == chat_id],
            key=lambda x: x.get("created_at", ""),
        )

    def delete_upload(self, upload_id: str, chat_id: str) -> bool:
        return bool(
            self._remove(
                "uploads",
                lambda x: x.get("id") == upload_id and x.get("chat_id") == chat_id,
            )
        )

    def get_share(self, token: str) -> dict | None:
        return self._find("shares", lambda x: x.get("token") == token)

    def create_share(self, chat_id: str, user_id: str | None = None) -> dict:
        existing = self._find("shares", lambda x: x.get("chat_id") == chat_id)
        if existing:
            return existing
        share = {
            "token": secrets.token_urlsafe(12),
            "chat_id": chat_id,
            "created_at": now_iso(),
        }
        if user_id:
            share["user_id"] = user_id
        self._insert("shares", share)
        return share

    def list_autopilots(self) -> list[dict]:
        return sorted(
            self._all("autopilots"), key=lambda x: x.get("updated_at", ""), reverse=True
        )

    def get_autopilot(self, autopilot_id: str) -> dict | None:
        return self._find("autopilots", lambda x: x.get("id") == autopilot_id)

    def create_autopilot(
        self,
        name: str,
        instruction: str,
        agent_id: str,
        cron: str,
        starts_at: str | None = None,
        ends_at: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        timestamp = now_iso()
        item = {
            "id": str(uuid4()),
            "name": name.strip(),
            "instruction": instruction.strip(),
            "agent_id": agent_id,
            "cron": cron.strip(),
            "enabled": False,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_run_at": None,
        }
        if user_id:
            item["user_id"] = user_id
        self._insert("autopilots", item)
        return item

    def update_autopilot(self, autopilot_id: str, values: dict) -> dict | None:
        values = {**values, "updated_at": now_iso()}
        return (
            self.get_autopilot(autopilot_id)
            if self._update("autopilots", lambda x: x.get("id") == autopilot_id, values)
            else None
        )

    def delete_autopilot(self, autopilot_id: str) -> bool:
        return bool(self._remove("autopilots", lambda x: x.get("id") == autopilot_id))

    def create_autopilot_run(
        self,
        autopilot_id: str,
        chat_id: str,
        session_id: str,
        user_id: str | None = None,
    ) -> dict:
        item = {
            "id": str(uuid4()),
            "autopilot_id": autopilot_id,
            "chat_id": chat_id,
            "session_id": session_id,
            "status": "running",
            "started_at": now_iso(),
            "finished_at": None,
            "duration_ms": None,
            "error": None,
        }
        if user_id:
            item["user_id"] = user_id
        self._insert("autopilot_runs", item)
        return item

    def update_autopilot_run(self, run_id: str, values: dict) -> dict | None:
        if not self._update("autopilot_runs", lambda x: x.get("id") == run_id, values):
            return None
        return self._find("autopilot_runs", lambda x: x.get("id") == run_id)

    def list_autopilot_runs(self, autopilot_id: str) -> list[dict]:
        return sorted(
            [
                x
                for x in self._all("autopilot_runs")
                if x.get("autopilot_id") == autopilot_id
            ],
            key=lambda x: x.get("started_at", ""),
            reverse=True,
        )

    def list_all_autopilot_runs(self) -> list[dict]:
        return self._all("autopilot_runs")
