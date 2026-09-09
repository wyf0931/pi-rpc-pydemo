# pyright: reportIncompatibleVariableOverride=false

"""SQLModel records for OMA Studio's platform metadata.

JSON-valued columns intentionally remain JSON text.  They are configuration
snapshots, not queryable message content, and keeping them encoded preserves
the existing Store dictionary interface without introducing a second schema
for Pi transcripts.
"""

from typing import ClassVar

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__: ClassVar[str] = "users"
    id: str = Field(primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str | None = None
    password_hash: str
    role: str
    status: str
    created_at: str
    last_login_at: str | None = None
    extra_json: str = "{}"


class Session(SQLModel, table=True):
    __tablename__: ClassVar[str] = "sessions"
    id: str = Field(primary_key=True)
    token_hash: str = Field(index=True, unique=True)
    user_id: str = Field(index=True)
    created_at: str
    expires_at: str
    extra_json: str = "{}"


class Agent(SQLModel, table=True):
    __tablename__: ClassVar[str] = "agents"
    id: str = Field(primary_key=True)
    user_id: str | None = Field(default=None, index=True)
    name: str
    instruction: str
    description: str | None = None
    tags_json: str = "[]"
    quickstarts_json: str = "[]"
    provider: str | None = None
    model: str | None = None
    thinking_level: str | None = None
    extensions_json: str = "[]"
    skills_json: str = "[]"
    tools_json: str = "[]"
    tools_configured: bool = True
    mcp_servers_json: str = "[]"
    avatar_path: str | None = None
    content_hash: str | None = None
    source_publication_id: str | None = None
    source_version: str | None = None
    source_hash: str | None = None
    protected: bool = False
    created_at: str
    updated_at: str
    extra_json: str = "{}"


class Chat(SQLModel, table=True):
    __tablename__: ClassVar[str] = "chats"
    id: str = Field(primary_key=True)
    user_id: str | None = Field(default=None, index=True)
    session_id: str
    agent_id: str = Field(index=True)
    title: str
    status: str
    created_at: str
    updated_at: str
    last_activity_at: str
    extra_json: str = "{}"


class Autopilot(SQLModel, table=True):
    __tablename__: ClassVar[str] = "autopilots"
    id: str = Field(primary_key=True)
    user_id: str | None = Field(default=None, index=True)
    name: str
    instruction: str
    agent_id: str = Field(index=True)
    cron: str
    enabled: bool = False
    starts_at: str | None = None
    ends_at: str | None = None
    created_at: str
    updated_at: str
    last_run_at: str | None = None
    extra_json: str = "{}"


class AutopilotRun(SQLModel, table=True):
    __tablename__: ClassVar[str] = "autopilot_runs"
    id: str = Field(primary_key=True)
    user_id: str | None = Field(default=None, index=True)
    autopilot_id: str = Field(index=True)
    chat_id: str = Field(index=True)
    session_id: str
    status: str
    started_at: str
    finished_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None
    extra_json: str = "{}"


class Share(SQLModel, table=True):
    __tablename__: ClassVar[str] = "shares"
    token: str = Field(primary_key=True)
    user_id: str | None = Field(default=None, index=True)
    chat_id: str = Field(index=True, unique=True)
    created_at: str
    extra_json: str = "{}"


class AgentPublication(SQLModel, table=True):
    __tablename__: ClassVar[str] = "agent_publications"
    id: str = Field(primary_key=True)
    source_agent_id: str = Field(index=True)
    owner_user_id: str = Field(index=True)
    name: str
    description: str
    install_count: int = 0
    created_at: str
    updated_at: str
    extra_json: str = "{}"


class AgentPublicationVersion(SQLModel, table=True):
    __tablename__: ClassVar[str] = "agent_publication_versions"
    id: str = Field(primary_key=True)
    publication_id: str = Field(index=True)
    version: str
    version_sort_json: str = "[]"
    content_json: str = "{}"
    content_hash: str
    created_at: str
    extra_json: str = "{}"


class Upload(SQLModel, table=True):
    __tablename__: ClassVar[str] = "uploads"
    id: str = Field(primary_key=True)
    chat_id: str = Field(index=True)
    created_at: str
    extra_json: str = "{}"


class SystemSetting(SQLModel, table=True):
    __tablename__: ClassVar[str] = "system_settings"
    key: str = Field(primary_key=True)
    value: str
    extra_json: str = "{}"


TABLE_MODELS = {
    "users": User,
    "sessions": Session,
    "agents": Agent,
    "chats": Chat,
    "autopilots": Autopilot,
    "autopilot_runs": AutopilotRun,
    "shares": Share,
    "agent_publications": AgentPublication,
    "agent_publication_versions": AgentPublicationVersion,
    "uploads": Upload,
    "system_settings": SystemSetting,
}
