# Friction log and product feedback

Notes written while building Recall (Alexa+ track). Entries use the format the
hackathon asks for: task, steps, expected vs actual, severity, workaround,
suggestion. Keep adding entries as you go, and edit these to match what you
actually saw.

## Tools used so far
- Python MCP SDK (`mcp` package, FastMCP, Streamable HTTP), version 1.x
- MCP Inspector v2.11.0 (testing the server, protocol MCP 2025-11-25)

## 1. Python MCP SDK 2.x breaks the FastMCP import
- **Task:** start an MCP server with `from mcp.server.fastmcp import FastMCP`
- **Steps:** `pip install "mcp[cli]"` (installed 2.x), then `python server.py`
- **Expected:** the server starts, since most examples and tutorials use FastMCP
- **Actual:** `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`.
  The 2.x release renamed FastMCP to MCPServer.
- **Severity:** medium (blocks first run, but easy to resolve)
- **Workaround:** `pip install "mcp[cli]<2"` to stay on 1.x
- **Suggestion:** make the install page and quickstart say which major version
  the examples target. Credit where due: the error message itself named the
  rename and linked the migration guide, which made this quick to fix.

## 2. Inspector shows only "Failed" when the server is not running
- **Task:** connect MCP Inspector to my local server at `http://127.0.0.1:8787/mcp`
- **Steps:** added the server, turned on its toggle
- **Expected:** a plain reason, such as "connection refused: is the server running?"
- **Actual:** the card showed "Failed", and the Network panel listed a POST with
  status ERROR. Nothing on the card explained the cause.
- **Severity:** low to medium (cost me a few minutes; the cause was a stopped server)
- **Workaround:** restarted the server and reconnected
- **Suggestion:** show the underlying reason (refused, timeout, HTTP status)
  right on the server card.

## 3. Adding a custom server in Inspector v2 was not obvious
- **Task:** connect Inspector to my own Streamable HTTP server
- **Steps:** opened Inspector; saw three example servers; cloned the example HTTP
  server and edited its URL (it also asked for a "server id")
- **Expected:** a clear "connect to a URL" option
- **Actual:** it worked after cloning and editing, but it took some guessing
  (I may have missed an easier route)
- **Severity:** low
- **Workaround:** clone and edit the example server
- **Suggestion:** add a "Connect to a local URL" shortcut on the first screen.

## What worked well
- Streamable HTTP server needed only a few lines with FastMCP.
- Inspector's protocol view showed the negotiated version (MCP 2025-11-25),
  which was handy for checking the spec requirement.
- Tool results with a short `speech` field plus structured data were easy to
  inspect and test.

## Feature requests (optional)
- (add yours as you think of them: what you'd want, why it matters, urgency)
