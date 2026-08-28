import os
from dataclasses import dataclass
from pathlib import Path


def _env_file_values() -> dict[str, str]:
    """Read simple dotenv values so reload workers pick up local configuration."""
    path = Path.cwd() / ".env"
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("\"'")
    return values


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    pi_cli_path: str
    pi_session_dir: Path
    pi_cwd: Path
    pi_provider: str | None
    pi_model: str | None
    pi_tools: str | None
    pi_home: Path
    pi_default_tools: tuple[str, ...]
    pi_default_extensions: tuple[str, ...]
    pi_default_skills: tuple[str, ...]
    pi_default_mcp_servers: tuple[str, ...]
    mode: str
    pi_thinking_level: str
    jina_api_key: str | None
    baidu_search_api_key: str | None
    baidu_search_base_url: str


def get_settings() -> Settings:
    dotenv = _env_file_values()

    def value(name: str, default: str | None = None) -> str | None:
        return os.environ.get(name, dotenv.get(name, default))

    data_dir = Path(value("PI_PLATFORM_DATA_DIR", "data") or "data")
    mode = (value("PI_MODE", "production") or "production").lower()
    if mode not in {"development", "production"}:
        mode = "production"
    thinking_level = (value("PI_THINKING_LEVEL", "low") or "low").lower()
    if thinking_level not in {
        "off",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    }:
        thinking_level = "low"
    return Settings(
        data_dir=data_dir,
        pi_cli_path=value("PI_CLI_PATH", "pi") or "pi",
        pi_session_dir=Path(
            value("PI_SESSION_DIR", str(data_dir / "pi-sessions"))
            or str(data_dir / "pi-sessions")
        ),
        pi_cwd=Path(value("PI_CWD", str(Path.cwd())) or str(Path.cwd())),
        pi_provider=value("PI_PROVIDER") or None,
        pi_model=value("PI_MODEL") or None,
        pi_tools=value("PI_TOOLS") or None,
        pi_home=Path(
            value("PI_HOME", str(Path.home() / ".pi" / "agent"))
            or str(Path.home() / ".pi" / "agent")
        ).expanduser(),
        pi_default_tools=_csv(value("PI_DEFAULT_TOOLS")),
        pi_default_extensions=_csv(value("PI_DEFAULT_EXTENSIONS")),
        pi_default_skills=_csv(value("PI_DEFAULT_SKILLS")),
        pi_default_mcp_servers=_csv(value("PI_DEFAULT_MCP_SERVERS")),
        mode=mode,
        pi_thinking_level=thinking_level,
        jina_api_key=value("JINA_API_KEY") or None,
        baidu_search_api_key=value("BAIDU_SEARCH_API_KEY") or None,
        baidu_search_base_url=value("BAIDU_SEARCH_BASE_URL", "https://api.qnaigc.com/v1") or "https://api.qnaigc.com/v1",
    )
