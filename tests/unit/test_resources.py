import json
from pathlib import Path

from app.config import get_settings
from app.resources import discover_models, discover_resources


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


def test_skill_discovery_includes_skills_cli_source(tmp_path: Path):
    pi_home = tmp_path / ".pi" / "agent"
    skill_dir = pi_home / "skills" / "human-writing"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: human-writing\ndescription: Writing helper\n---\n",
        encoding="utf-8",
    )
    lock_path = tmp_path / ".agents" / ".skill-lock.json"
    lock_path.parent.mkdir()
    lock_path.write_text(
        json.dumps(
            {
                "skills": {
                    "human-writing": {
                        "source": "owner/writing-skills",
                        "skillPath": "skills/human-writing/SKILL.md",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    skills = discover_resources(pi_home, tmp_path / "workspace")["skills"]
    assert skills[0]["source"] == "owner/writing-skills"
    assert skills[0]["author"] == "owner"


def test_resource_metadata_includes_package_author(tmp_path: Path):
    pi_home = tmp_path / ".pi" / "agent"
    package_dir = pi_home / "npm" / "node_modules" / "example-extension"
    package_dir.mkdir(parents=True)
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "example-extension",
                "author": {"name": "Example Author"},
                "pi": {"extensions": ["./index.ts"]},
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "index.ts").write_text("export default {}", encoding="utf-8")

    extensions = discover_resources(pi_home, tmp_path / "workspace")["extensions"]
    assert extensions[0]["author"] == "Example Author"
