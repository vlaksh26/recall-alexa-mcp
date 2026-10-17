"""Recall MCP server (Streamable HTTP).

Run:   python server.py            -> http://127.0.0.1:8787/mcp
Debug: RECALL_DEBUG=1 python server.py   (adds the advance_days tool for demos)

NOTE: written against the official `mcp` Python SDK's FastMCP API. If your
installed version complains about a constructor argument, check
`pip show mcp` and the SDK README, then log it in your friction log.
"""
import os

from mcp.server.fastmcp import FastMCP

from core import Store

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8787"))

mcp = FastMCP("recall", host=HOST, port=PORT, stateless_http=True, json_response=True)
store = Store(os.environ.get("RECALL_DB", "recall.db"))


@mcp.tool()
def add_cards(deck: str, cards: list[dict[str, str]]) -> dict:
    """Add flashcards to a deck. Each card is {"front": question, "back": answer}."""
    ids = store.add_cards(deck, cards)
    return {"speech": f"Added {len(ids)} cards to {deck}.", "card_ids": ids}


@mcp.tool()
def next_due(deck: str | None = None) -> dict:
    """Get the next card due for review. Speak ONLY `speech` (the question).
    Keep `card.back` hidden until the user has answered."""
    cards = store.next_due(deck, limit=1)
    if not cards:
        return {"speech": "You're all caught up. Nothing is due today.", "card": None, "remaining": 0}
    card = cards[0]
    return {
        "speech": card["front"],
        "card": {"id": card["id"], "front": card["front"], "back": card["back"]},
        "remaining": store.count_due(deck),
    }


@mcp.tool()
def grade_answer(card_id: int, rating: str) -> dict:
    """Record how well the user recalled a card. rating is one of:
    again (wrong or blank), hard (right but struggled), good, easy."""
    try:
        r = store.grade(card_id, rating)
    except (ValueError, KeyError) as e:
        return {"speech": f"Sorry, I couldn't record that. {e}", "error": str(e)}
    days = r["interval_days"]
    when = "tomorrow" if days == 1 else f"in {days} days"
    return {"speech": f"The answer was: {r['back']}. I'll ask again {when}.", **r}


@mcp.tool()
def progress_summary(deck: str | None = None) -> dict:
    """Summarize progress: cards due, reviewed today, mastered, and streak."""
    s = store.stats(deck)
    speech = (
        f"You have {s['due_today']} cards due, reviewed {s['reviewed_today']} today, "
        f"and a {s['streak_days']} day streak."
    )
    return {"speech": speech, **s}


if os.environ.get("RECALL_DEBUG") == "1":

    @mcp.tool()
    def advance_days(days: int = 1) -> dict:
        """DEMO ONLY: move the clock forward so a week of scheduling fits in seconds."""
        today = store.advance_days(days)
        return {"speech": f"It's now {today}.", "today": today}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
