import json
import re
from pathlib import Path


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = {}
    if text.startswith("---"):
        lines = text.split("---", 2)[1].splitlines()
        index = 0
        while index < len(lines):
            match = re.match(
                r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$", lines[index].strip()
            )
            if not match:
                index += 1
                continue
            key, value = match.group(1), match.group(2).strip()
            if value in {">", ">-", "|", "|-", ">+", "|+"}:
                values = []
                index += 1
                while index < len(lines) and (
                    not lines[index].strip() or lines[index].startswith((" ", "\t"))
                ):
                    if lines[index].strip():
                        values.append(lines[index].strip())
                    index += 1
                separator = "\n" if value.startswith("|") else " "
                joined = separator.join(values).strip()
                frontmatter[key] = joined if value.endswith("+") else joined.rstrip()
                continue
            frontmatter[key] = value.strip("\"'")
            index += 1
    return frontmatter


def _skill_metadata(path: Path, source: str | None = None) -> dict:
    frontmatter = _frontmatter(path)
    directory = path.parent
    return {
        "id": str(directory),
        "name": frontmatter.get("name", directory.name),
        "description": frontmatter.get("description", ""),
        "path": str(directory),
        "type": "skill",
        "source": source,
    }


def _skill_sources(pi_home: Path) -> dict[str, str]:
    lock_path = pi_home.parents[1] / ".agents" / ".skill-lock.json"
    if not lock_path.is_file():
        return {}
    try:
        raw = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    sources: dict[str, str] = {}
    for name, entry in (raw.get("skills") or {}).items():
        if not isinstance(entry, dict) or not isinstance(entry.get("source"), str):
            continue
        sources[name] = entry["source"]
        skill_path = entry.get("skillPath")
        if isinstance(skill_path, str):
            sources[Path(skill_path).parent.name] = entry["source"]
    return sources


def _extension_metadata(resource_path: Path, package: dict | None = None) -> dict:
    package = package or {}
    resolved = str(resource_path.resolve())
    return {
        "id": resolved,
        "name": package.get("name") or resource_path.stem,
        "description": package.get("description", ""),
        "path": resolved,
        "type": "extension",
    }


def discover_models(pi_home: Path) -> list[dict]:
    """Read Pi's user model catalog without starting Pi or resolving credentials."""
    path = pi_home / "models.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    providers: list[dict] = []
    for provider_id, provider in (raw.get("providers") or {}).items():
        if not isinstance(provider, dict):
            continue
        models = []
        for model in provider.get("models") or []:
            if not isinstance(model, dict) or not model.get("id"):
                continue
            default_levels = ["off", "minimal", "low", "medium", "high", "xhigh", "max"]
            level_map = model.get("thinkingLevelMap")
            levels = (
                [level for level in default_levels if level_map.get(level) is not None]
                if isinstance(level_map, dict)
                else (default_levels[1:] if model.get("reasoning") else ["off"])
            )
            models.append(
                {
                    "id": model["id"],
                    "name": model.get("name") or model["id"],
                    "thinking_levels": levels,
                }
            )
        if models:
            providers.append(
                {
                    "id": provider_id,
                    "name": provider.get("name") or provider_id,
                    "models": models,
                }
            )
    return providers


def discover_resources(pi_home: Path, cwd: Path) -> dict:
    extension_roots = [pi_home / "extensions", cwd / ".pi" / "extensions"]
    skill_roots = [pi_home / "skills", cwd / ".pi" / "skills"]
    extensions: list[dict] = []
    skills: list[dict] = []
    mcp_servers: list[dict] = []
    seen_extensions: set[str] = set()
    seen_skills: set[str] = set()
    skill_sources = _skill_sources(pi_home)

    for root in extension_roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            resource_path: Path | None = None
            metadata: dict = {}
            if (
                entry.is_file()
                and entry.suffix in {".ts", ".js"}
                or entry.is_dir()
                and (entry / "index.ts").exists()
                or entry.is_dir()
                and (entry / "index.js").exists()
            ):
                resource_path = entry
            if resource_path is None:
                continue
            resolved = str(resource_path.resolve())
            if resolved in seen_extensions:
                continue
            seen_extensions.add(resolved)
            package_file = (
                resource_path / "package.json"
                if resource_path.is_dir()
                else resource_path.parent / "package.json"
            )
            if package_file.exists():
                try:
                    package = json.loads(package_file.read_text(encoding="utf-8"))
                    metadata = {
                        "name": package.get("name"),
                        "description": package.get("description", ""),
                    }
                except (OSError, json.JSONDecodeError):
                    metadata = {}
            extensions.append(_extension_metadata(resource_path, metadata))

    # Pi packages can contribute extensions from the managed npm directory.
    npm_root = pi_home / "npm" / "node_modules"
    package_files = list(npm_root.glob("*/package.json")) + list(
        npm_root.glob("@*/*/package.json")
    )
    for package_file in sorted(package_files):
        try:
            package = json.loads(package_file.read_text(encoding="utf-8"))
            pi_manifest = package.get("pi") or {}
            for relative_path in pi_manifest.get("extensions", []):
                extension_path = (package_file.parent / relative_path).resolve()
                if not extension_path.exists():
                    continue
                if str(extension_path) not in seen_extensions:
                    seen_extensions.add(str(extension_path))
                    extensions.append(_extension_metadata(extension_path, package))
        except (OSError, json.JSONDecodeError, TypeError):
            continue

    for root in skill_roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("SKILL.md")):
            resolved = str(path.parent.resolve())
            if resolved in seen_skills:
                continue
            seen_skills.add(resolved)
            try:
                metadata = _skill_metadata(path, skill_sources.get(path.parent.name))
                skills.append(metadata)
            except OSError:
                continue
    config_paths = [
        pi_home / "mcp.json",
        Path.home() / ".config" / "mcp" / "mcp.json",
        Path.home() / ".agents" / "mcp.json",
        Path.home() / ".agents" / "mcp" / "mcp.json",
        cwd / ".mcp.json",
        cwd / ".pi" / "mcp.json",
    ]
    seen_servers: set[str] = set()
    for config_path in config_paths:
        if not config_path.is_file():
            continue
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            for name, definition in (raw.get("mcpServers") or {}).items():
                if name in seen_servers or not isinstance(definition, dict):
                    continue
                seen_servers.add(name)
                mcp_servers.append(
                    {
                        "id": name,
                        "name": name,
                        "description": definition.get("description", ""),
                        "path": str(config_path.resolve()),
                        "type": "mcp_server",
                    }
                )
        except (OSError, json.JSONDecodeError):
            continue
    return {
        "extensions": extensions,
        "skills": skills,
        "mcp_servers": mcp_servers,
        "providers": discover_models(pi_home),
    }
