import json
from pathlib import Path

from app.config import get_settings
from app.resources import discover_models


def test_discovers_pi_model_catalog(tmp_path: Path):
    (tmp_path / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "example": {
                        "name": "Example Provider",
                        "models": [
                            {
                                "id": "example-fast",
                                "name": "Example Fast",
                                "reasoning": True,
                            },
                            {"id": "example-id-only"},
                        ],
                    },
                    "empty": {"models": []},
                }
            }
        ),
        encoding="utf-8",
    )

    assert discover_models(tmp_path) == [
        {
            "id": "example",
            "name": "Example Provider",
            "models": [
                {
                    "id": "example-fast",
                    "name": "Example Fast",
                    "thinking_levels": [
                        "minimal",
                        "low",
                        "medium",
                        "high",
                        "xhigh",
                        "max",
                    ],
                },
                {
                    "id": "example-id-only",
                    "name": "example-id-only",
                    "thinking_levels": ["off"],
                },
            ],
        }
    ]


def test_reads_agent_defaults_from_dotenv(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(
        "PI_DEFAULT_TOOLS=read,write\nPI_DEFAULT_EXTENSIONS=pi-mcp-adapter\n"
        "PI_DEFAULT_SKILLS=human-writing\nPI_DEFAULT_MCP_SERVERS=browser\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for name in (
        "PI_DEFAULT_TOOLS",
        "PI_DEFAULT_EXTENSIONS",
        "PI_DEFAULT_SKILLS",
        "PI_DEFAULT_MCP_SERVERS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = get_settings()

    assert settings.pi_default_tools == ("read", "write")
    assert settings.pi_default_extensions == ("pi-mcp-adapter",)
    assert settings.pi_default_skills == ("human-writing",)
    assert settings.pi_default_mcp_servers == ("browser",)


def test_storage_paths_expand_home(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(
        "PI_PLATFORM_DATA_DIR=~/.oma-studio/data\n"
        "PI_SESSION_DIR=~/.oma-studio/data/pi-sessions\n"
        "PI_CWD=~/.oma-studio/workspace\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for name in ("PI_PLATFORM_DATA_DIR", "PI_SESSION_DIR", "PI_CWD"):
        monkeypatch.delenv(name, raising=False)

    settings = get_settings()

    home = Path.home()
    assert settings.data_dir == home / ".oma-studio" / "data"
    assert settings.pi_session_dir == home / ".oma-studio" / "data" / "pi-sessions"
    assert settings.pi_cwd == home / ".oma-studio" / "workspace"
