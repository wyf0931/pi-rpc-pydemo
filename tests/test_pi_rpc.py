from types import SimpleNamespace

from app.pi_rpc import PiRuntimeManager


def test_agent_provider_and_model_override_global_defaults():
    settings = SimpleNamespace(
        pi_cli_path="pi",
        pi_session_dir="sessions",
        pi_provider="deepseek",
        pi_model="deepseek-v4-pro",
        pi_thinking_level="low",
    )
    runtime = PiRuntimeManager(settings, store=None)
    command = runtime._command({
        "instruction": "Be focused.",
        "provider": "zhipu",
        "model": "glm-5.3-flash",
        "tools": [],
        "extensions": [],
        "skills": [],
    }, "chat-1", create=True)

    assert command[command.index("--provider") + 1] == "zhipu"
    assert command[command.index("--model") + 1] == "glm-5.3-flash"
    assert command[command.index("--thinking") + 1] == "low"


def test_platform_web_tools_load_the_first_party_extension():
    settings = SimpleNamespace(
        pi_cli_path="pi",
        pi_session_dir="sessions",
        pi_provider="deepseek",
        pi_model="deepseek-v4-pro",
        pi_thinking_level="low",
    )
    runtime = PiRuntimeManager(settings, store=None)
    command = runtime._command({
        "instruction": "Use web tools when needed.",
        "provider": None,
        "model": None,
        "tools": ["read", "web_fetch", "web_search"],
        "extensions": [],
        "skills": [],
    }, "chat-1", create=True)

    assert "--extension" in command
    assert command[command.index("--tools") + 1] == "read,web_fetch,web_search"


def test_container_maps_host_pi_home_resource_paths():
    settings = SimpleNamespace(
        pi_cli_path="pi",
        pi_session_dir="sessions",
        pi_provider=None,
        pi_model=None,
        pi_thinking_level="low",
        pi_home="/home/node/.pi/agent",
    )
    runtime = PiRuntimeManager(settings, store=None)
    command = runtime._command({
        "instruction": "Use the selected extension.",
        "tools": ["read"],
        "extensions": ["/Users/scott/.pi/agent/npm/node_modules/pi-mcp-adapter/index.ts"],
        "skills": ["/Users/scott/.pi/agent/skills/human-writing"],
    }, "chat-1", create=False)

    assert "/home/node/.pi/agent/npm/node_modules/pi-mcp-adapter/index.ts" in command
    assert "/home/node/.pi/agent/skills/human-writing" in command
