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


async def search_skills(query: str, owner: str | None = None) -> list[dict[str, str]]:
    command = ["npx", "-y", "skills", "find", query]
    if owner:
        command.extend(["--owner", owner])
    environment = os.environ.copy()
    environment["DISABLE_TELEMETRY"] = "1"
    process = await asyncio.create_subprocess_exec(
        *command,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError("skills CLI search timed out after 60 seconds") from None

    if process.returncode:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            detail or f"skills CLI exited with code {process.returncode}"
        )
    return parse_skill_search(stdout.decode("utf-8", errors="replace"))
