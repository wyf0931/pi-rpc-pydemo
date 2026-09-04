import asyncio
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
RESULT_RE = re.compile(
    r"^\s*(?P<repo>[^\s@]+)@(?P<skill>[^\s]+)\s+"
    r"(?P<installs>[\d.,]+(?:[KMB])?)\s+installs\s*$",
    re.IGNORECASE,
)
URL_RE = re.compile(r"^\s*[└├╰`\-]*\s*(?P<url>https?://\S+)\s*$")
SOURCE_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_SOURCE_RE = re.compile(
    r"^(?:"
    r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    r"|https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?"
    r"(?:/tree/[^/]+(?:/.*)?)?"
    r"|git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?"
    r"|ssh://git@github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?"
    r")/?$",
    re.IGNORECASE,
)
SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PREVIEW_SKILL_RE = re.compile(
    r"^\s*(?:[│|]\s*)?(?:[-*]\s*)?"
    r"(?P<skill>[A-Za-z0-9][A-Za-z0-9._-]*)\s*$"
)
NPM_PACKAGE_RE = re.compile(
    r"^(?:@[a-z0-9][a-z0-9._~-]*/[a-z0-9][a-z0-9._~-]*|[a-z0-9][a-z0-9._~-]*)"
    r"(?:@(?:[a-z0-9*^~<>=|.+-]+))?$",
    re.IGNORECASE,
)
MCP_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


class McpServerExistsError(ValueError):
    pass


class McpConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SkillSearchResult:
    repo: str
    skill: str
    installs: str
    url: str

    def as_dict(self) -> dict[str, str]:
        return {
            "repo": self.repo,
            "skill": self.skill,
            "installs": self.installs,
            "url": self.url,
        }


def parse_skill_search(output: str) -> list[dict[str, str]]:
    """Parse the human-readable output emitted by the skills CLI.

    The CLI currently has no JSON output. We pair each recognized result line
    with the next URL line and ignore decorative or informational lines so a
    harmless CLI formatting change does not invalidate all results.
    """
    lines = ANSI_RE.sub("", output).splitlines()
    results: list[SkillSearchResult] = []
    pending: dict[str, str] | None = None
    for line in lines:
        match = RESULT_RE.match(line)
        if match:
            pending = match.groupdict()
            continue
        if pending is None:
            continue
        url_match = URL_RE.match(line)
        if not url_match:
            continue
        results.append(
            SkillSearchResult(
                repo=pending["repo"],
                skill=pending["skill"],
                installs=pending["installs"],
                url=url_match["url"],
            )
        )
        pending = None
    return [result.as_dict() for result in results]


def parse_skill_preview(output: str) -> list[dict[str, str]]:
    """Parse skill names from the skills CLI's human-readable --list output."""
    lines = ANSI_RE.sub("", output).splitlines()
    results: list[dict[str, str]] = []
    in_available_section = False
    for line in lines:
        if "Available Skills" in line:
            in_available_section = True
            continue
        if not in_available_section:
            continue
        if "Use --skill" in line:
            break
        match = PREVIEW_SKILL_RE.match(line)
        if match and (
            "│" in line or "|" in line or line.lstrip().startswith(("-", "*"))
        ):
            results.append({"skill": match["skill"]})
    return results


async def _run_skills_cli(command: list[str], timeout: float) -> str:
    environment = os.environ.copy()
    environment["DISABLE_TELEMETRY"] = "1"
    environment.setdefault(
        "NPM_CONFIG_CACHE", str(Path(tempfile.gettempdir()) / "oma-npm-cache")
    )
    process = await asyncio.create_subprocess_exec(
        "npx",
        "-y",
        "skills",
        *command,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError(
            f"skills CLI command timed out after {int(timeout)} seconds"
        ) from None

    if process.returncode:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            detail or f"skills CLI exited with code {process.returncode}"
        )
    return stdout.decode("utf-8", errors="replace")


def validate_skill_source(source: str, skill: str) -> None:
    if not GITHUB_SOURCE_RE.fullmatch(source):
        raise ValueError("Skill source must be a GitHub repository or skill URL")
    if not SKILL_NAME_RE.fullmatch(skill):
        raise ValueError("Skill name contains unsupported characters")


async def search_skills(query: str, owner: str | None = None) -> list[dict[str, str]]:
    command = ["find", query]
    if owner:
        command.extend(["--owner", owner])
    output = await _run_skills_cli(command, timeout=60)
    return parse_skill_search(output)


async def preview_skills(source: str) -> list[dict[str, str]]:
    if not GITHUB_SOURCE_RE.fullmatch(source):
        raise ValueError("Skill source must be a GitHub repository or skill URL")
    output = await _run_skills_cli(["add", source, "--list"], timeout=180)
    return parse_skill_preview(output)


async def install_skill(source: str, skill: str) -> None:
    validate_skill_source(source, skill)
    await _run_skills_cli(
        ["add", source, "--skill", skill, "-g", "-a", "pi", "-y", "--copy"],
        timeout=120,
    )


async def uninstall_skill(source: str | None, skill: str) -> None:
    if source:
        validate_skill_source(source, skill)
    elif not SKILL_NAME_RE.fullmatch(skill):
        raise ValueError("Skill name contains unsupported characters")
    await _run_skills_cli(
        ["remove", skill, "-g", "-a", "pi", "-y"],
        timeout=120,
    )


def normalize_npm_package(value: str) -> str:
    """Normalize a user-entered Pi npm install command to its package source."""
    source = value.strip()
    if source.lower().startswith("pi install "):
        source = source[11:].strip()
    if source.startswith("npm:"):
        source = source[4:].strip()
    if not NPM_PACKAGE_RE.fullmatch(source):
        raise ValueError("Enter a valid npm package id, such as pi-mcp-adapter")
    return f"npm:{source}"


def npm_package_name(source: str) -> str:
    package = source.removeprefix("npm:")
    version_separator = (
        package.find("@", 1) if package.startswith("@") else package.find("@")
    )
    return package if version_separator < 0 else package[:version_separator]


def parse_mcp_config(raw: str) -> dict[str, dict]:
    """Parse and validate a pasted Pi mcpServers configuration."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"MCP configuration is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("mcpServers"), dict):
        raise McpConfigError("MCP configuration must contain an mcpServers object")
    servers = payload["mcpServers"]
    if not servers:
        raise ValueError("MCP configuration must define at least one server")
    for name, definition in servers.items():
        if not isinstance(name, str) or not MCP_SERVER_NAME_RE.fullmatch(name):
            raise ValueError(
                "MCP server names must start with a letter or number and contain only letters, numbers, '.', '_' or '-'"
            )
        if not isinstance(definition, dict):
            raise McpConfigError(f"MCP server {name} must be an object")
        if not any(definition.get(key) for key in ("url", "command", "socket")):
            raise ValueError(f"MCP server {name} must define url, command, or socket")
    return servers


def read_mcp_config(path: Path) -> dict:
    if not path.is_file():
        return {"mcpServers": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Existing MCP configuration is not valid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("mcpServers"), dict):
        raise McpConfigError(
            "Existing MCP configuration must contain an mcpServers object"
        )
    return payload


def write_mcp_config(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_path = tempfile.mkstemp(prefix=".mcp-", suffix=".json", dir=path.parent)
    temporary = Path(raw_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def add_mcp_servers(path: Path, servers: dict[str, dict]) -> list[str]:
    payload = read_mcp_config(path)
    existing = payload["mcpServers"]
    duplicates = sorted(set(existing).intersection(servers))
    if duplicates:
        raise McpServerExistsError(
            f"MCP server already exists: {', '.join(duplicates)}"
        )
    existing.update(servers)
    write_mcp_config(path, payload)
    return sorted(servers)


def remove_mcp_server(path: Path, name: str) -> None:
    if not MCP_SERVER_NAME_RE.fullmatch(name):
        raise ValueError("Invalid MCP server name")
    payload = read_mcp_config(path)
    if name not in payload["mcpServers"]:
        raise ValueError(f"MCP server not found: {name}")
    del payload["mcpServers"][name]
    write_mcp_config(path, payload)


def github_source_owner(source: str) -> str | None:
    normalized = source.strip().removesuffix("/")
    if normalized.startswith("https://github.com/"):
        path = normalized.removeprefix("https://github.com/")
    elif normalized.startswith("git@github.com:"):
        path = normalized.removeprefix("git@github.com:")
    elif normalized.startswith("ssh://git@github.com/"):
        path = normalized.removeprefix("ssh://git@github.com/")
    else:
        path = normalized
    owner = path.split("/", 1)[0]
    return owner or None


async def install_extension(package: str) -> None:
    source = normalize_npm_package(package)
    await _run_pi_cli(["install", source], timeout=180)


async def uninstall_extension(package: str) -> None:
    source = normalize_npm_package(package)
    await _run_pi_cli(["remove", source], timeout=120)


def uninstall_local_extension(path: str, roots: list[Path]) -> None:
    resolved = Path(path).resolve()
    resolved_roots = [root.resolve() for root in roots]
    if not any(resolved.parent == root for root in resolved_roots):
        raise ValueError(
            "Local extension must be directly inside a Pi extensions directory"
        )
    if not resolved.exists():
        raise ValueError("Local extension was not found")
    if resolved.is_dir():
        shutil.rmtree(resolved)
    else:
        resolved.unlink()


async def _run_pi_cli(command: list[str], timeout: float) -> str:
    process = await asyncio.create_subprocess_exec(
        "pi",
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError(
            f"pi command timed out after {int(timeout)} seconds"
        ) from None

    if process.returncode:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"pi exited with code {process.returncode}")
    return stdout.decode("utf-8", errors="replace")
