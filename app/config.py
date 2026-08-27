from dataclasses import dataclass
from pathlib import Path
import os


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


def get_settings() -> Settings:
    data_dir = Path(os.getenv("PI_PLATFORM_DATA_DIR", "data"))
    return Settings(
        data_dir=data_dir,
        pi_cli_path=os.getenv("PI_CLI_PATH", "pi"),
        pi_session_dir=Path(os.getenv("PI_SESSION_DIR", str(data_dir / "pi-sessions"))),
        pi_cwd=Path(os.getenv("PI_CWD", str(Path.cwd()))),
        pi_provider=os.getenv("PI_PROVIDER") or None,
        pi_model=os.getenv("PI_MODEL") or None,
        pi_tools=os.getenv("PI_TOOLS") or None,
        pi_home=Path(os.getenv("PI_HOME", str(Path.home() / ".pi" / "agent"))).expanduser(),
    )
