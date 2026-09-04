from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
EXTENSION = REPOSITORY_ROOT / "extensions" / "oma-web-tools.ts"


def test_web_search_targets_baidu_qianfan_and_uses_search_v2_payload():
    source = EXTENSION.read_text(encoding="utf-8")

    assert "https://qianfan.baidubce.com" in source
    assert "/v2/ai_search/web_search" in source
    assert 'messages: [{ role: "user", content: query }]' in source
    assert 'search_source: "baidu_search_v2"' in source
    assert 'resource_type_filter: [{ type: "web", top_k:' in source
