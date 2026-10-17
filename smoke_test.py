"""Smoke test: talks to the RUNNING Recall server like a real MCP client.

1. Terminal 1:  python server.py   (add RECALL_DEBUG=1 to test advance_days)
2. Terminal 2:  python smoke_test.py

Each step prints what the tool said. Delete recall.db (with the server stopped)
to start from a clean slate.
"""
import asyncio
import json

from mcp import ClientSession

try:  # newer 1.x SDKs rename this helper; support both names
    from mcp.client.streamable_http import streamable_http_client as connect
except ImportError:
    from mcp.client.streamable_http import streamablehttp_client as connect

URL = "http://127.0.0.1:8787/mcp"


async def call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    if result.isError:
        raise RuntimeError(f"{name} returned an error: {result.content}")
    try:
        data = json.loads(result.content[0].text)
    except (IndexError, AttributeError, ValueError):
        data = result.structuredContent or {}
    print(f"- {name}: {data.get('speech', data)}")
    return data


async def main():
    async with connect(URL) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("Tools found:", names)

            await call(session, "add_cards", {
                "deck": "smoke",
                "cards": [{"front": "Capital of France?", "back": "Paris"}],
            })
            due = await call(session, "next_due", {"deck": "smoke"})
            if due.get("card"):
                await call(session, "grade_answer", {
                    "card_id": due["card"]["id"],
                    "rating": "good",
                })
            await call(session, "next_due", {"deck": "smoke"})
            if "advance_days" in names:
                await call(session, "advance_days", {"days": 1})
                await call(session, "next_due", {"deck": "smoke"})
            else:
                print("(advance_days not found: start the server with RECALL_DEBUG=1)")
            concept = await call(session, "add_concept", {
                "deck": "smoke",
                "title": "photosynthesis",
                "key_points": [
                    {"point": "plants use sunlight", "keywords": ["sunlight", "light"]},
                    {"point": "chlorophyll captures light", "keywords": ["chlorophyll"]},
                    {"point": "glucose and oxygen come out", "keywords": ["glucose", "sugar"]},
                ],
            })
            await call(session, "teach_back", {
                "card_id": concept["card_id"],
                "explanation": "Plants use sunlight and chlorophyll to make sugar.",
            })
            await call(session, "progress_summary", {"deck": "smoke"})
    print("\nAll steps finished.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:  # keep the output friendly for debugging
        print(f"\nSmoke test failed: {type(e).__name__}: {e}")
        print("Is server.py still running on http://127.0.0.1:8787 ?")
        raise
