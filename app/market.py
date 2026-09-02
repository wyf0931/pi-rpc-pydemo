import asyncio
import os
import re
from dataclasses import dataclass

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
RESULT_RE = re.compile(
    r"^\s*(?P<repo>[^\s@]+)@(?P<skill>[^\s]+)\s+"
    r"(?P<installs>[\d.,]+(?:[KMB])?)\s+installs\s*$",
    re.IGNORECASE,
)
URL_RE = re.compile(r"^\s*[└├╰`\-]*\s*(?P<url>https?://\S+)\s*$")
SOURCE_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
NPM_PACKAGE_RE = re.compile(
    r"^(?:@[a-z0-9][a-z0-9._~-]*/[a-z0-9][a-z0-9._~-]*|[a-z0-9][a-z0-9._~-]*)"
    r"(?:@(?:[a-z0-9*^~<>=|.+-]+))?$",
    re.IGNORECASE,
)


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


async def _run_skills_cli(command: list[str], timeout: float) -> str:
    environment = os.environ.copy()
    environment["DISABLE_TELEMETRY"] = "1"
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
    if not SOURCE_RE.fullmatch(source):
        raise ValueError("Skill source must use the owner/repository format")
    if not SKILL_NAME_RE.fullmatch(skill):
        raise ValueError("Skill name contains unsupported characters")


async def search_skills(query: str, owner: str | None = None) -> list[dict[str, str]]:
    command = ["find", query]
    if owner:
        command.extend(["--owner", owner])
    output = await _run_skills_cli(command, timeout=60)
    return parse_skill_search(output)


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


async def install_extension(package: str) -> None:
    source = normalize_npm_package(package)
    await _run_pi_cli(["install", source], timeout=180)


async def uninstall_extension(package: str) -> None:
    source = normalize_npm_package(package)
    await _run_pi_cli(["remove", source], timeout=120)


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
