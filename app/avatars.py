from pathlib import Path
from shutil import copyfile

from fastapi import HTTPException

AVATAR_DIRNAME = "avatars"
MAX_AVATAR_BYTES = 5 * 1024 * 1024
_AVATAR_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
    "image/png": (b"\x89PNG\r\n\x1a\n", ".png"),
    "image/webp": (b"RIFF", ".webp"),
    "image/gif": (b"GIF8", ".gif"),
}


def avatar_dir(data_dir: Path) -> Path:
    return data_dir / AVATAR_DIRNAME


def seed_default_avatar(data_dir: Path, agent: dict) -> dict:
    if agent.get("avatar_path"):
        return agent
    source = (
        Path(__file__).parent.parent / "static" / "assets" / "default-assistant.jpg"
    )
    if not source.is_file():
        return agent
    target_dir = avatar_dir(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "default-assistant.jpg"
    if not target.exists():
        target.write_bytes(source.read_bytes())
    agent["avatar_path"] = f"{AVATAR_DIRNAME}/default-assistant.jpg"
    return agent


def avatar_file(data_dir: Path, agent: dict) -> Path | None:
    relative = agent.get("avatar_path")
    relative_path = Path(relative or "")
    if len(relative_path.parts) != 2 or relative_path.parts[0] != AVATAR_DIRNAME:
        return None
    path = avatar_dir(data_dir) / relative_path.name
    return path if path.is_file() else None


def save_avatar(data_dir: Path, agent_id: str, content_type: str, body: bytes) -> str:
    media_type = content_type.split(";", 1)[0].strip().lower()
    signature = _AVATAR_SIGNATURES.get(media_type)
    if not signature or not body.startswith(signature[0]):
        raise HTTPException(415, "Avatar must be a JPEG, PNG, WebP, or GIF image")
    if len(body) > MAX_AVATAR_BYTES:
        raise HTTPException(413, "Avatar must be 5 MB or smaller")
    directory = avatar_dir(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob(f"{agent_id}.*"):
        old.unlink(missing_ok=True)
    filename = f"{agent_id}{signature[1]}"
    (directory / filename).write_bytes(body)
    return f"{AVATAR_DIRNAME}/{filename}"


def remove_avatar(data_dir: Path, agent: dict) -> None:
    path = avatar_file(data_dir, agent)
    if path:
        path.unlink(missing_ok=True)


def copy_avatar(data_dir: Path, source_agent: dict, target_agent_id: str) -> str | None:
    source = avatar_file(data_dir, source_agent)
    if not source:
        return None
    target = avatar_dir(data_dir) / f"{target_agent_id}{source.suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    copyfile(source, target)
    return f"{AVATAR_DIRNAME}/{target.name}"
