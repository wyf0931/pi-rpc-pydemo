import asyncio
from pathlib import Path

import pytest

from app.market import (
    github_source_owner,
    install_extension,
    install_skill,
    normalize_npm_package,
    npm_package_name,
    parse_skill_preview,
    parse_skill_search,
    uninstall_extension,
    uninstall_local_extension,
    uninstall_skill,
    validate_skill_source,
)


def test_parse_skill_search_pairs_results_with_urls():
    output = """
\x1b[32mwshobson/agents@typescript-advanced-types  69K installs\x1b[0m
└ https://skills.sh/wshobson/agents/typescript-advanced-types
informational line
owner/collection@small-skill 1,234 installs
└ https://skills.sh/owner/collection/small-skill
"""
    assert parse_skill_search(output) == [
        {
            "repo": "wshobson/agents",
            "skill": "typescript-advanced-types",
            "installs": "69K",
            "url": "https://skills.sh/wshobson/agents/typescript-advanced-types",
        },
        {
            "repo": "owner/collection",
            "skill": "small-skill",
            "installs": "1,234",
            "url": "https://skills.sh/owner/collection/small-skill",
        },
    ]


def test_parse_skill_search_ignores_unpaired_result():
    assert parse_skill_search("owner/repo@skill 10K installs\n") == []


def test_parse_skill_preview_reads_available_skills():
    output = """
◇  Available Skills
│
│    mono-color
│
└  Use --skill <name> to install specific skills
"""
    assert parse_skill_preview(output) == [{"skill": "mono-color"}]


def test_validate_skill_source_accepts_github_references():
    for source in (
        "owner/repo",
        "https://github.com/owner/repo",
        "https://github.com/owner/repo/tree/main/skills/example",
        "git@github.com:owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
    ):
        validate_skill_source(source, "example")


def test_github_source_owner_extracts_user_or_org():
    assert github_source_owner("https://github.com/tt-a1i/archify") == "tt-a1i"
    assert (
        github_source_owner("https://github.com/tt-a1i/archify/tree/main") == "tt-a1i"
    )
    assert github_source_owner("git@github.com:tt-a1i/archify.git") == "tt-a1i"


def test_install_skill_uses_copy_and_pi_target(monkeypatch):
    calls = []

    async def fake_run(command, timeout):
        calls.append((command, timeout))
        return ""

    monkeypatch.setattr("app.market._run_skills_cli", fake_run)
    asyncio.run(install_skill("owner/repo", "skill-name"))
    assert calls == [
        (
            [
                "add",
                "owner/repo",
                "--skill",
                "skill-name",
                "-g",
                "-a",
                "pi",
                "-y",
                "--copy",
            ],
            120,
        )
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("pi install npm:pi-mcp-adapter", "npm:pi-mcp-adapter"),
        (
            "npm:@juicesharp/rpiv-ask-user-question",
            "npm:@juicesharp/rpiv-ask-user-question",
        ),
        ("@scope/package@1.2.3", "npm:@scope/package@1.2.3"),
    ],
)
def test_normalize_npm_package(value, expected):
    assert normalize_npm_package(value) == expected


@pytest.mark.parametrize(
    "value", ["", "npm:", "pi install npm:x;rm", "git+https://example.com/x"]
)
def test_normalize_npm_package_rejects_commands(value):
    with pytest.raises(ValueError):
        normalize_npm_package(value)


def test_npm_package_name_strips_optional_version():
    assert npm_package_name("npm:pi-mcp-adapter@1.2.3") == "pi-mcp-adapter"
    assert npm_package_name("npm:@scope/package@^1.0.0") == "@scope/package"


def test_pi_install_and_remove_use_argument_lists(monkeypatch):
    calls = []

    async def fake_run(command, timeout):
        calls.append((command, timeout))
        return ""

    monkeypatch.setattr("app.market._run_pi_cli", fake_run)
    asyncio.run(install_extension("pi-mcp-adapter"))
    asyncio.run(uninstall_extension("npm:pi-mcp-adapter"))
    assert calls == [
        (["install", "npm:pi-mcp-adapter"], 180),
        (["remove", "npm:pi-mcp-adapter"], 120),
    ]


def test_uninstall_skill_uses_global_pi_target(monkeypatch):
    calls = []

    async def fake_run(command, timeout):
        calls.append((command, timeout))
        return ""

    monkeypatch.setattr("app.market._run_skills_cli", fake_run)
    asyncio.run(uninstall_skill("owner/repo", "skill-name"))
    assert calls == [(["remove", "skill-name", "-g", "-a", "pi", "-y"], 120)]


def test_uninstall_skill_without_source_uses_skill_name(monkeypatch):
    calls = []

    async def fake_run(command, timeout):
        calls.append((command, timeout))
        return ""

    monkeypatch.setattr("app.market._run_skills_cli", fake_run)
    asyncio.run(uninstall_skill(None, "local-skill"))
    assert calls == [(["remove", "local-skill", "-g", "-a", "pi", "-y"], 120)]


def test_uninstall_local_extension_only_removes_direct_child(tmp_path):
    root = tmp_path / "extensions"
    extension = root / "local-extension"
    extension.mkdir(parents=True)
    (extension / "index.ts").write_text("export default {}", encoding="utf-8")
    uninstall_local_extension(str(extension), [Path(root)])
    assert not extension.exists()


def test_uninstall_local_extension_rejects_nested_path(tmp_path):
    root = tmp_path / "extensions"
    nested = root / "package" / "local-extension"
    nested.mkdir(parents=True)
    with pytest.raises(ValueError):
        uninstall_local_extension(str(nested), [root])
