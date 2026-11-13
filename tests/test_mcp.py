import importlib

import anyio
import pytest

pytest.importorskip("mcp")
from mcp import Client  # noqa: E402

from tests.test_extract import CONTRACT  # noqa: E402


@pytest.fixture
def mcp_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTICEDAY_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("NOTICEDAY_TODAY", "2026-11-13")
    import noticeday.app as appmod
    importlib.reload(appmod)
    import noticeday.mcp_server as m
    importlib.reload(m)
    appmod.store.add("Supply - A Co", CONTRACT)
    return m


def call(m, name, args):
    async def go():
        async with Client(m.server) as c:
            tools = await c.list_tools()
            r = await c.call_tool(name, args)
            return tools, r
    return anyio.run(go)


def test_tools_are_read_only(mcp_mod):
    tools, _ = call(mcp_mod, "list_deadlines", {})
    names = {t.name for t in tools.tools}
    assert names == {"list_deadlines", "get_contract", "search_contracts"}
    assert all(t.annotations.read_only_hint for t in tools.tools)


def test_list_deadlines_reports_unconfirmed(mcp_mod):
    _, r = call(mcp_mod, "list_deadlines", {"within_days": 60})
    d = r.structured_content
    assert d["today"] == "2026-11-13"
    [item] = d["deadlines"]
    # Same contract as test_app: notice due 2026-12-31, 48 days away, not confirmed.
    assert item["act_by"] == "2026-12-31" and item["days_left"] == 48
    assert item["status_text"] == "Send notice by" and item["confirmed"] is False
    _, r = call(mcp_mod, "list_deadlines", {"within_days": 60, "confirmed_only": True})
    assert r.structured_content["deadlines"] == []


def test_get_contract_quotes_the_clause(mcp_mod):
    _, r = call(mcp_mod, "get_contract", {"contract_id": 1})
    f = r.structured_content["fields"]
    assert f["notice"]["value"] == "60 days" and "sixty (60) days" in f["notice"]["quote"]
    _, r = call(mcp_mod, "get_contract", {"contract_id": 99})
    assert r.is_error


def test_search(mcp_mod):
    _, r = call(mcp_mod, "search_contracts", {"query": "SIXTY"})
    [hit] = r.structured_content["results"]
    assert hit["id"] == 1 and "sixty" in hit["snippet"].lower()
