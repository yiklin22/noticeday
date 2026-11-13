"""MCP server: lets an AI assistant (Claude Desktop, Claude Code) ask about
contract deadlines in the noticeday database.

Read-only on purpose. An assistant can list deadlines, read a contract's
values with the clause each came from, and search contracts. It cannot edit
or confirm values: confirming stays a person's job in the web app, and the
answers say which values nobody has confirmed yet.

Run: NOTICEDAY_DB=demo.db python -m noticeday.mcp_server   (stdio)
"""

import datetime as dt
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .app import STATUS_TEXT, plan, store, today
from .extract import FIELDS
from .store import to_json
from .text import Duration

server = MCPServer(
    name="noticeday",
    instructions=(
        "Contract renewal deadlines. 'act_by' is the last day to send notice of "
        "non-renewal. Values with confirmed=false were read by software and not yet "
        "checked by a person: say so when you report them."),
)
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


def _iso(d):
    return d.isoformat() if isinstance(d, dt.date) else d


def _summary(c) -> dict[str, Any]:
    s = plan(c)
    key = s.act_by or s.term_end
    return {
        "id": c["id"], "name": c["name"],
        "status": s.status, "status_text": STATUS_TEXT[s.status],
        "act_by": _iso(s.act_by), "term_end": _iso(s.term_end),
        "days_left": (key - today()).days if isinstance(key, dt.date) else None,
        "reason": s.reason,
        "confirmed": bool(c["confirmed_by"]), "confirmed_by": c["confirmed_by"],
    }


@server.tool(annotations=READ_ONLY, structured_output=True)
def list_deadlines(within_days: int = 90, confirmed_only: bool = False) -> dict[str, Any]:
    """Contracts with a deadline (send notice by, option, or expiry) within the next
    `within_days` days, soonest first. Each item says whether a person confirmed it."""
    items = []
    for c in store.all():
        if confirmed_only and not c["confirmed_by"]:
            continue
        s = _summary(c)
        if s["days_left"] is not None and 0 <= s["days_left"] <= within_days:
            items.append(s)
    items.sort(key=lambda s: s["days_left"])
    return {"today": today().isoformat(), "within_days": within_days, "deadlines": items}


@server.tool(annotations=READ_ONLY, structured_output=True)
def get_contract(contract_id: int) -> dict[str, Any]:
    """One contract: its schedule, each term value, and the contract words each value
    was read from. Values a person edited have no quote."""
    c = store.get(contract_id)
    if c is None:
        raise ValueError(f"no contract with id {contract_id}")
    fields = {}
    for k in FIELDS:
        ex = c["extracted"].get(k) or {}
        value = to_json(k, c["values"][k])
        quote = None
        if ex.get("start") is not None and to_json(k, ex.get("value")) == value:
            quote = c["text"][max(0, ex["start"] - 80):ex["end"] + 80]
        shown = str(c["values"][k]) if isinstance(c["values"][k], Duration) else value
        fields[k] = {"value": shown, "quote": quote}
    return {**_summary(c), "fields": fields}


@server.tool(annotations=READ_ONLY, structured_output=True)
def search_contracts(query: str, limit: int = 10) -> dict[str, Any]:
    """Contracts whose name or text contains `query` (case-insensitive), with a
    short snippet around the first match."""
    q = query.strip().lower()
    if not q:
        raise ValueError("query is empty")
    hits = []
    for c in store.all():
        text = c["text"]
        i = text.lower().find(q)
        if q in c["name"].lower() or i >= 0:
            snippet = text[max(0, i - 100):i + len(q) + 100] if i >= 0 else None
            hits.append({"id": c["id"], "name": c["name"], "snippet": snippet})
        if len(hits) >= limit:
            break
    return {"query": query, "results": hits}


if __name__ == "__main__":
    server.run()
