from pathlib import Path


def test_usage_statistics_has_a_single_sidebar_entry_and_dialog():
    html = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/app.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert 'data-lucide="chart-pie"' in html
    assert '@click="openProfileUsage()"' in html
    assert 'class="modal modal-middle usage-dialog"' in html
    assert "usageOpen" in script
    assert "`/api/usage?days=${encodeURIComponent(this.usageRange)}`" in script
    assert "Usage trend" in html
    assert ":points=" in html
    assert "usageData.sessions" in html
    assert "usageData.users" in html
    assert "usageData.agents" in html
    assert "x-show=\"authUser?.role === 'admin'\"" in html
    assert "usageTab === 'users' && authUser?.role === 'admin'" in html
    assert "usageTab === 'agents' && authUser?.role === 'admin'" in html
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


def test_users_are_managed_in_a_dedicated_dialog_not_settings_tab():
    html = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/app.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert "usersOpen" in script
    assert "openProfileUsers()" in script
    assert 'class="modal modal-middle users-dialog"' in html
    assert 'class="modal-box usage-modal-box users-modal-box"' in html
    assert "settingsTab === 'users'" not in html
    assert "openSettingsTab('users')" not in html
    assert ".users-modal-box" in styles
    users_markup = html.split('class="modal modal-middle users-dialog"', 1)[1].split(
        "</dialog>", 1
    )[0]
    assert "usage-count" not in users_markup
    assert 'class="btn btn-soft btn-primary" @click="openAddUser()"' in users_markup
    assert "New" in users_markup
    assert ".user-add-dialog" in styles
    assert "z-index: 60;" in styles
