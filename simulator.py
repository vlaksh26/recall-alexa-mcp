"""Simulated Alexa+ for Recall: a web page + a small MCP client + a rule-based agent.

1. Terminal 1: python server.py  (start with RECALL_DEBUG=1 for the skip-a-day demo)
2. Terminal 2: python simulator.py  -> open http://127.0.0.1:8000 in Chrome
"""
import json
import os
import re
import time
from pathlib import Path

import uvicorn
from mcp import ClientSession
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

try:
    from mcp.client.streamable_http import streamable_http_client as connect
except ImportError:
    from mcp.client.streamable_http import streamablehttp_client as connect

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8787/mcp")
HERE = Path(__file__).parent
state = {"card": None}  # the card Alexa just asked about
STOP = {"the", "a", "an", "of", "is", "it", "and", "to", "in"}
DEMO_CARDS = [
    {"front": "What is the capital of France?", "back": "Paris"},
    {"front": "What gas do plants take in for photosynthesis?", "back": "carbon dioxide"},
    {"front": "Which organelle makes ATP?", "back": "the mitochondria"},
]
DEMO_CONCEPT = {"deck": "demo", "title": "photosynthesis", "key_points": [
    {"point": "plants use sunlight", "keywords": ["sunlight", "light"]},
    {"point": "chlorophyll captures light", "keywords": ["chlorophyll"]},
    {"point": "carbon dioxide and water go in", "keywords": ["carbon dioxide", "co2"]},
    {"point": "glucose and oxygen come out", "keywords": ["glucose", "sugar"]},
]}


def keywords(s):
    return set(re.findall(r"[a-z0-9]+", s.lower())) - STOP


async def call(session, trace, name, args=None):
    start = time.perf_counter()
    res = await session.call_tool(name, args or {})
    raw = res.content[0].text if res.content else "{}"
    try:
        data = json.loads(raw)
    except ValueError:
        data = {"speech": raw}
    trace.append({"tool": name, "args": args or {}, "speech": data.get("speech"),
                  "ms": round((time.perf_counter() - start) * 1000)})
    return data


async def ask_next(session, trace):
    data = await call(session, trace, "next_due")
    state["card"] = data.get("card")
    return data["speech"]


async def handle(session, text, trace):
    t = text.lower()
    card = state["card"]
    if re.search(r"\b(stop|cancel)\b", t):
        state["card"] = None
        return "Okay, I'll stop here."
    if "demo" in t and "load" in t:
        await call(session, trace, "add_cards", {"deck": "demo", "cards": DEMO_CARDS})
        await call(session, trace, "add_concept", DEMO_CONCEPT)
        return "Demo deck loaded. Say quiz me to start."
    m = re.search(r"(skip|advance|fast forward)\D*(\d+)?\s*days?", t)
    if m:
        data = await call(session, trace, "advance_days", {"days": int(m.group(2) or 1)})
        return data["speech"]
    if re.search(r"progress|streak|how am i", t):
        return (await call(session, trace, "progress_summary"))["speech"]
    if re.search(r"\b(quiz|test me|ask me)\b", t):
        return await ask_next(session, trace)
    if card:
        state["card"] = None
        if card["kind"] == "concept":
            data = await call(session, trace, "teach_back",
                              {"card_id": card["id"], "explanation": text})
        else:
            back, said = keywords(card["back"]), keywords(t)
            score = len(back & said) / len(back) if back else 0
            rating = "again" if re.search(r"don'?t know|no idea", t) else (
                "good" if score >= 0.8 else "hard" if score >= 0.4 else "again")
            data = await call(session, trace, "grade_answer",
                              {"card_id": card["id"], "rating": rating})
        return data["speech"] + " Next: " + await ask_next(session, trace)
    return "Try: load the demo deck, quiz me, how am I doing, or skip a day."


async def say(request):
    text = (await request.json())["text"]
    trace = []
    try:
        async with connect(MCP_URL) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                reply = await handle(session, text, trace)
    except Exception as e:
        return JSONResponse({"reply": "I can't reach the Recall server. Is server.py running?",
                             "trace": trace, "error": str(e)})
    return JSONResponse({"reply": reply, "trace": trace})


async def index(request):
    return FileResponse(HERE / "index.html")


app = Starlette(routes=[Route("/", index), Route("/api/say", say, methods=["POST"])])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
