from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# pi-lens-ignore: reportMissingImports
from tinydb import Query, TinyDB

DEFAULT_TOOLS = ["read", "write", "edit", "bash"]
BUILTIN_TOOLS = DEFAULT_TOOLS + ["grep", "find", "ls"]
PLATFORM_TOOLS = ["web_fetch", "web_search"]
SUPPORTED_TOOLS = BUILTIN_TOOLS + PLATFORM_TOOLS


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = TinyDB(path)
        self.agents = self.db.table("agents")
        self.chats = self.db.table("chats")
        self.autopilots = self.db.table("autopilots")
        self.autopilot_runs = self.db.table("autopilot_runs")

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

    def create_autopilot_chat(self, agent_id: str, title: str) -> dict:
        """Create a fresh chat whose Pi session ID is unique to this run."""
        chat = self.create_chat(agent_id, "", status="starting")
        return self.update_chat(chat["id"], {
            "session_id": chat["id"],
            "title": title,
        }) or chat

    def update_chat(self, chat_id: str, values: dict) -> dict | None:
        values = {**values, "updated_at": now_iso()}
        if "last_activity_at" not in values:
            values["last_activity_at"] = values["updated_at"]
        if self.chats.update(values, Query().id == chat_id):
            return self.get_chat(chat_id)
        return None

    def delete_chat(self, chat_id: str) -> bool:
        return bool(self.chats.remove(Query().id == chat_id))

    def list_autopilots(self) -> list[dict]:
        return sorted(self.autopilots.all(), key=lambda item: item.get("updated_at", ""), reverse=True)

    def get_autopilot(self, autopilot_id: str) -> dict | None:
        return self.autopilots.get(Query().id == autopilot_id)

    def create_autopilot(self, name: str, instruction: str, agent_id: str, cron: str,
                         starts_at: str | None = None, ends_at: str | None = None) -> dict:
        timestamp = now_iso()
        item = {
            "id": str(uuid4()), "name": name.strip(), "instruction": instruction.strip(),
            "agent_id": agent_id, "cron": cron.strip(), "enabled": False,
            "starts_at": starts_at, "ends_at": ends_at,
            "created_at": timestamp, "updated_at": timestamp, "last_run_at": None,
        }
        self.autopilots.insert(item)
        return item

    def update_autopilot(self, autopilot_id: str, values: dict) -> dict | None:
        values = {**values, "updated_at": now_iso()}
        if self.autopilots.update(values, Query().id == autopilot_id):
            return self.get_autopilot(autopilot_id)
        return None

    def delete_autopilot(self, autopilot_id: str) -> bool:
        return bool(self.autopilots.remove(Query().id == autopilot_id))

    def create_autopilot_run(self, autopilot_id: str, chat_id: str, session_id: str) -> dict:
        item = {"id": str(uuid4()), "autopilot_id": autopilot_id, "chat_id": chat_id,
                "session_id": session_id, "status": "running", "started_at": now_iso(),
                "finished_at": None, "duration_ms": None, "error": None}
        self.autopilot_runs.insert(item)
        return item

    def update_autopilot_run(self, run_id: str, values: dict) -> dict | None:
        if self.autopilot_runs.update(values, Query().id == run_id):
            return self.autopilot_runs.get(Query().id == run_id)
        return None

    def list_autopilot_runs(self, autopilot_id: str) -> list[dict]:
        return sorted((item for item in self.autopilot_runs.all()
                       if item.get("autopilot_id") == autopilot_id),
                      key=lambda item: item.get("started_at", ""), reverse=True)
