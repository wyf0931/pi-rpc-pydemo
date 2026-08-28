from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from tinydb import Query, TinyDB

DEFAULT_TOOLS = ["read", "write", "edit", "bash"]
BUILTIN_TOOLS = DEFAULT_TOOLS + ["grep", "find", "ls"]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = TinyDB(path)
        self.agents = self.db.table("agents")
        self.chats = self.db.table("chats")

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
            "protected": False,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        self.agents.insert(item)
        return item

    def update_agent(self, agent_id: str, values: dict) -> dict | None:
        values = {k: v for k, v in values.items() if v is not None}
        if "tools" in values:
            values["tools_configured"] = True
        values["updated_at"] = now_iso()
        if self.agents.update(values, Query().id == agent_id):
            return self.get_agent(agent_id)
        return None

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
        self, agent_id: str, session_id: str, status: str = "starting"
    ) -> dict:
        timestamp = now_iso()
        item = {
            "id": str(uuid4()),
            "session_id": session_id,
            "agent_id": agent_id,
            "title": "New conversation",
            "status": status,
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_activity_at": timestamp,
        }
        self.chats.insert(item)
        return item

    def update_chat(self, chat_id: str, values: dict) -> dict | None:
        values = {**values, "updated_at": now_iso()}
        if "last_activity_at" not in values:
            values["last_activity_at"] = values["updated_at"]
        if self.chats.update(values, Query().id == chat_id):
            return self.get_chat(chat_id)
        return None

    def delete_chat(self, chat_id: str) -> bool:
        return bool(self.chats.remove(Query().id == chat_id))
