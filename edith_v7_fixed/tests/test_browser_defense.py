# tests/test_browser_defense.py
import pytest
from plugins.browser_defense import (
    get_defense_status_dict,
    get_browser_defense_summary,
    get_browser_defense_events
)
from brain.router import route
from brain.agent import TOOLS


def test_browser_defense_status_dict_structure():
    """Verify get_defense_status_dict returns expected structure and metrics."""
    data = get_defense_status_dict()
    assert isinstance(data, dict)
    assert data.get("status") == "ok"
    assert "protectionStatus" in data
    assert "stats" in data
    assert "totalScanned" in data["stats"]
    assert "totalBlocked" in data["stats"]
    assert "selfHealing" in data
    assert "status" in data["selfHealing"]
    assert "recentThreats" in data
    assert isinstance(data["recentThreats"], list)


def test_browser_defense_summary_formatting():
    """Verify get_browser_defense_summary produces human-readable briefing."""
    summary = get_browser_defense_summary()
    assert isinstance(summary, str)
    assert "EDITH AI" in summary
    assert "Browser Cyber Defense Summary" in summary
    assert "Protection Engine" in summary
    assert "Intercepted Threats" in summary
    assert "Self-Healing Engine" in summary


def test_browser_defense_events():
    """Verify get_browser_defense_events returns audit trail."""
    events_text = get_browser_defense_events(limit=3)
    assert isinstance(events_text, str)
    assert "Recent Browser Security Events" in events_text


def test_router_fast_paths_extension_summary():
    """Verify router matches various user phrases for extension summary."""
    test_queries = [
        "show summary from that extension in web folder",
        "show summary from the extension",
        "extension summary",
        "what did the extension block",
        "what threats were blocked",
        "cyber defense summary"
    ]
    for q in test_queries:
        resp = route(q)
        assert isinstance(resp, str)
        assert "Browser Cyber Defense Summary" in resp


def test_agent_tools_registered():
    """Verify browser defense tools are registered in ReAct agent."""
    assert "browser_defense_summary" in TOOLS
    assert callable(TOOLS["browser_defense_summary"]["fn"])
    assert "browser_defense_events" in TOOLS
    assert callable(TOOLS["browser_defense_events"]["fn"])


def test_hud_extension_api_endpoints():
    """Verify HUD Flask app exposes /api/extension/summary and /api/extension/sync."""
    from hud.server import app
    client = app.test_client()

    # GET /api/extension/summary
    res = client.get('/api/extension/summary')
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data.get("status") == "ok"
    assert "textSummary" in json_data

    # POST /api/extension/sync
    sync_res = client.post('/api/extension/sync', json={
        "event": {
            "id": "SEC-TEST-999",
            "domain": "malicious-test.site",
            "blocked": True,
            "riskLevel": "HIGH_RISK"
        }
    })
    assert sync_res.status_code == 200
    assert sync_res.get_json().get("ok") is True
