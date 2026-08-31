from app.market import parse_skill_search


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
