from types import SimpleNamespace

from app.pi_rpc import PiRuntimeManager


def test_agent_provider_and_model_override_global_defaults():
    settings = SimpleNamespace(
        pi_cli_path="pi",
        pi_session_dir="sessions",
        pi_provider="deepseek",
        pi_model="deepseek-v4-pro",
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
