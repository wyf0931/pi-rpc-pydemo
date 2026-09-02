import asyncio

import pytest

from app.market import (
    install_extension,
    install_skill,
    normalize_npm_package,
    parse_skill_search,
    uninstall_extension,
    uninstall_skill,
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
