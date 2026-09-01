import asyncio

from app.market import install_skill, parse_skill_search


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
