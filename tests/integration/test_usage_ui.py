from pathlib import Path


def test_usage_statistics_has_a_single_sidebar_entry_and_dialog():
    html = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/app.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert 'data-lucide="chart-pie"' in html
    assert '@click="openUsage()"' in html
    assert 'class="modal modal-middle usage-dialog"' in html
    assert "usageOpen" in script
    assert "`/api/usage?days=${encodeURIComponent(this.usageRange)}`" in script
    assert "Usage trend" in html
    assert ":points=" in html
    assert "usageData.sessions" in html
    assert "usageData.users" in html
    assert "usageData.agents" in html
    usage_markup = html.split('class="modal modal-middle usage-dialog"', 1)[1].split(
        "</dialog>", 1
    )[0]
    assert "Team" not in usage_markup
    assert ".usage-modal-box" in styles


def test_usage_statistics_normalizes_pi_usage_field_variants():
    script = Path("static/app.js").read_text(encoding="utf-8")

    assert '"input_tokens", "inputTokens"' in script
    assert '"cache_read", "cache_read_tokens", "cached_tokens"' in script
    assert '"total_cost", "totalCost"' in script
    assert '"tool_calls", "toolCalls", "tools"' in script
