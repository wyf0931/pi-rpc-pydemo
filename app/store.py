import hashlib
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from tinydb import Query, TinyDB  # pyright: ignore[reportMissingImports]

from .auth import hash_password, new_session_token, session_digest

DEFAULT_TOOLS = ["read", "write", "edit", "bash"]
BUILTIN_TOOLS = DEFAULT_TOOLS + ["grep", "find", "ls"]
PLATFORM_TOOLS = ["web_fetch", "web_search", "publish_artifact"]
SUPPORTED_TOOLS = BUILTIN_TOOLS + PLATFORM_TOOLS


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def pi_terminal_failure(messages: list[dict]) -> str | None:
    """Return a user-facing error when Pi ends a turn without an answer."""
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
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = TinyDB(path)
        self.agents = self.db.table("agents")
        self.chats = self.db.table("chats")
        self.autopilots = self.db.table("autopilots")
        self.autopilot_runs = self.db.table("autopilot_runs")
        self.shares = self.db.table("shares")
        self.users = self.db.table("users")
        self.sessions = self.db.table("sessions")
        self.agent_publications = self.db.table("agent_publications")
        self.agent_publication_versions = self.db.table("agent_publication_versions")

    @staticmethod
    def public_user(user: dict) -> dict:
        return {key: value for key, value in user.items() if key != "password_hash"}

    def ensure_default_user(self, password: str) -> dict:
        user = self.get_user_by_username("admin")
        if user:
            return user
        timestamp = now_iso()
        user = {
            "id": str(uuid4()),
            "username": "admin",
            "email": None,
            "password_hash": hash_password(password),
            "role": "admin",
            "status": "active",
            "created_at": timestamp,
            "last_login_at": None,
        }
        self.users.insert(user)
        return user

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
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def list_users(self) -> list[dict]:
        return [self.public_user(user) for user in self.users.all()]

    def get_user(self, user_id: str) -> dict | None:
        return self.users.get(Query().id == user_id)

    def get_user_by_username(self, username: str) -> dict | None:
        return self.users.get(Query().username == username)

    def create_user(self, username: str, email: str | None, password: str) -> dict:
        timestamp = now_iso()
        user = {
            "id": str(uuid4()),
            "username": username.strip(),
            "email": email.strip() if email else None,
            "password_hash": hash_password(password),
            "role": "normal",
            "status": "active",
            "created_at": timestamp,
            "last_login_at": None,
        }
        self.users.insert(user)
        return user

    def update_user_status(self, user_id: str, status: str) -> dict | None:
        self.users.update({"status": status}, Query().id == user_id)
        return self.get_user(user_id)

    def delete_user(self, user_id: str) -> bool:
        self.sessions.remove(Query().user_id == user_id)
        return bool(self.users.remove(Query().id == user_id))

    def create_session(self, user_id: str, expires_at: str) -> str:
        token = new_session_token()
        self.sessions.insert(
            {
                "id": str(uuid4()),
                "token_hash": session_digest(token),
                "user_id": user_id,
                "created_at": now_iso(),
                "expires_at": expires_at,
            }
        )
        return token

    def get_session_user(self, token: str) -> dict | None:
        session = self.sessions.get(Query().token_hash == session_digest(token))
        if not session:
            return None
        if session.get("expires_at", "") <= now_iso():
            self.sessions.remove(doc_ids=[session.doc_id])
            return None
        return self.get_user(session["user_id"])

    def delete_session(self, token: str) -> None:
        self.sessions.remove(Query().token_hash == session_digest(token))

    def mark_user_login(self, user_id: str) -> dict | None:
        self.users.update({"last_login_at": now_iso()}, Query().id == user_id)
        return self.get_user(user_id)

    def ensure_default_agent(self, default_tools: list[str] | None = None) -> dict:
        agent = self.agents.get(Query().id == "default-assistant")
        if agent:
            if "tools_configured" not in agent or "provider" not in agent:
                values = {
                    "tools": agent.get("tools") or default_tools or [],
                    "tools_configured": True,
                    "provider": agent.get("provider"),
                }
                self.agents.update(values, Query().id == agent["id"])
                agent.update(values)
            if "avatar_path" not in agent:
                agent["avatar_path"] = None
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
        self.agents.insert(item)
        return item

    def list_agents(self) -> list[dict]:
        return list(self.agents.all())

    def get_agent(self, agent_id: str) -> dict | None:
        return self.agents.get(Query().id == agent_id)

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
        self.agents.insert(item)
        return item

    def update_agent(self, agent_id: str, values: dict) -> dict | None:
        values = {k: v for k, v in values.items() if v is not None}
        if "tools" in values:
            values["tools_configured"] = True
        values["updated_at"] = now_iso()
        if self.agents.update(values, Query().id == agent_id):
            agent = self.get_agent(agent_id)
            if agent:
                self.agents.update(
                    {"content_hash": self.agent_content_hash(agent)},
                    Query().id == agent_id,
                )
                agent["content_hash"] = self.agent_content_hash(agent)
            return agent
        return None

    def list_agent_publications(self) -> list[dict]:
        publications = []
        for publication in self.agent_publications.all():
            versions = self.agent_publication_versions.search(
                Query().publication_id == publication["id"]
            )
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
        publication = self.agent_publications.get(Query().id == publication_id)
        if not publication:
            return None
        versions = self.agent_publication_versions.search(
            Query().publication_id == publication_id
        )
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
            self.agent_publication_versions.get(
                (Query().publication_id == publication_id)
                & (Query().version == version)
            )
        )

    def publish_agent(self, agent: dict, owner_user_id: str, version: str) -> dict:
        content = self.agent_config(agent)
        content_hash = self.agent_content_hash(agent)
        publication = self.agent_publications.get(
            (Query().owner_user_id == owner_user_id)
            & (Query().source_agent_id == agent["id"])
        )
        timestamp = now_iso()
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
            self.agent_publications.insert(publication)
        else:
            self.agent_publications.update(
                {
                    "name": agent["name"],
                    "description": agent["instruction"],
                    "updated_at": timestamp,
                },
                Query().id == publication["id"],
            )
        version_record = {
            "id": str(uuid4()),
            "publication_id": publication["id"],
            "version": version,
            "version_sort": [int(part) for part in version[1:].split(".")],
            "content": content,
            "content_hash": content_hash,
            "created_at": timestamp,
        }
        self.agent_publication_versions.insert(version_record)
        return self.get_agent_publication(publication["id"]) or publication

    def install_agent_publication(
        self, publication_id: str, owner_user_id: str, version: str | None = None
    ) -> dict | None:
        publication = self.get_agent_publication(publication_id)
        if not publication:
            return None
        target_version = publication["latest"]
        if version:
            target_version = self.agent_publication_versions.get(
                (Query().publication_id == publication_id)
                & (Query().version == version)
            )
            if not target_version:
                return None
        content = target_version["content"]
        timestamp = now_iso()
        agent = {
            "id": str(uuid4()),
            **content,
            "user_id": owner_user_id,
            "tools_configured": True,
            "avatar_path": None,
            "protected": False,
            "created_at": timestamp,
            "updated_at": timestamp,
            "content_hash": target_version["content_hash"],
            "source_publication_id": publication_id,
            "source_version": target_version["version"],
            "source_hash": target_version["content_hash"],
        }
        self.agents.insert(agent)
        self.agent_publications.update(
            {"install_count": int(publication.get("install_count", 0)) + 1},
            Query().id == publication_id,
        )
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        agent = self.get_agent(agent_id)
        if not agent or agent.get("protected"):
            return False
        return bool(self.agents.remove(Query().id == agent_id))

    def list_chats(self) -> list[dict]:
        return sorted(
            self.chats.all(), key=lambda x: x.get("last_activity_at", ""), reverse=True
        )

    def get_chat(self, chat_id: str) -> dict | None:
        return self.chats.get(Query().id == chat_id)

    def create_chat(
        self,
        agent_id: str,
        session_id: str | None = None,
        status: str = "starting",
        user_id: str | None = None,
    ) -> dict:
        timestamp = now_iso()
        chat_id = str(uuid4())
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
        self.chats.insert(item)
        return item

    def create_autopilot_chat(
        self, agent_id: str, title: str, user_id: str | None = None
    ) -> dict:
        """Create a fresh chat whose Pi session ID is unique to this run."""
        chat = self.create_chat(agent_id, status="starting", user_id=user_id)
        return self.update_chat(chat["id"], {"title": title}) or chat

    def update_chat(self, chat_id: str, values: dict) -> dict | None:
        # updated_at tracks any metadata touch; last_activity_at is the sidebar
        # ordering key and is only bumped when a caller passes it explicitly
        # (real user/autopilot activity), so reading history never reorders.
        values = {**values, "updated_at": now_iso()}
        if self.chats.update(values, Query().id == chat_id):
            return self.get_chat(chat_id)
        return None

    def delete_chat(self, chat_id: str) -> bool:
        self.shares.remove(Query().chat_id == chat_id)
        return bool(self.chats.remove(Query().id == chat_id))

    def get_share(self, token: str) -> dict | None:
        matches = self.shares.search(Query().token == token)
        return matches[0] if matches else None

    def create_share(self, chat_id: str, user_id: str | None = None) -> dict:
        """Create (or reuse) the unguessable public share token for a chat."""
        existing = self.shares.search(Query().chat_id == chat_id)
        if existing:
            return existing[0]
        share = {
            "token": secrets.token_urlsafe(12),
            "chat_id": chat_id,
            "created_at": now_iso(),
        }
        if user_id:
            share["user_id"] = user_id
        self.shares.insert(share)
        return share

    def list_autopilots(self) -> list[dict]:
        return sorted(
            self.autopilots.all(),
            key=lambda item: item.get("updated_at", ""),
            reverse=True,
        )

    def get_autopilot(self, autopilot_id: str) -> dict | None:
        return self.autopilots.get(Query().id == autopilot_id)

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
        self.autopilots.insert(item)
        return item

    def update_autopilot(self, autopilot_id: str, values: dict) -> dict | None:
        values = {**values, "updated_at": now_iso()}
        if self.autopilots.update(values, Query().id == autopilot_id):
            return self.get_autopilot(autopilot_id)
        return None

    def delete_autopilot(self, autopilot_id: str) -> bool:
        return bool(self.autopilots.remove(Query().id == autopilot_id))

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
        self.autopilot_runs.insert(item)
        return item

    def update_autopilot_run(self, run_id: str, values: dict) -> dict | None:
        if self.autopilot_runs.update(values, Query().id == run_id):
            return self.autopilot_runs.get(Query().id == run_id)
        return None

    def list_autopilot_runs(self, autopilot_id: str) -> list[dict]:
        return sorted(
            (
                item
                for item in self.autopilot_runs.all()
                if item.get("autopilot_id") == autopilot_id
            ),
            key=lambda item: item.get("started_at", ""),
            reverse=True,
        )
