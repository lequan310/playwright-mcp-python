<!-- GitHub Copilot instructions for contributors and automated coding agents -->
# Playwright MCP — Agent instructions

These notes give focused, actionable guidance for AI coding agents working on this repository.
Keep edits small, preserve style, and reference the concrete files listed below.

Key files to read first
- `README.md` — high-level project goals, install/run commands, and tool descriptions (dev: `fastmcp dev src/server.py`; prod: `python src/session_server.py`).
- `src/server.py` — single-client MCP server implementation; shows role-based locator patterns, snapshot flow, and global browser lifecycle.
- `src/session_server.py` — multi-client/session variant; session lifecycle, cleanup task, and per-session state are implemented here.
- `pyproject.toml` — Python requirements (requires Python >= 3.13, dependencies: fastmcp, playwright).

Big-picture architecture (short)
- The project exposes an MCP server (FastMCP) that wraps Playwright browser automation as tools. Tools are declared with `@mcp.tool()` (see `server.py` and `session_server.py`).
- Two entry modes:
  - `server.py`: single shared browser state (global variables). Simpler, useful for quick testing and inspector (`fastmcp dev`).
  - `session_server.py`: per-client isolated sessions stored in `sessions` dict with `BrowserSession` dataclass. Use this for concurrent clients and real deployments.
- Tool outputs prefer structured accessibility snapshots via Playwright's `aria_snapshot()` for action verification rather than raw screenshots.

Project-specific patterns and conventions
- Prefer role-based locators when interacting with elements: code uses `page.get_by_role(role, name=name)` before falling back to CSS `selector` (see `browser_click`, `browser_type`, `browser_select_option`). Mimic these in new tools.
- All tools return structured dictionaries with either `error` keys or `{message, url, title, snapshot}` shapes. Follow this response contract in new tools.
- Global vs session APIs: `server.py` functions do not accept session IDs and operate on module-level browser state; `session_server.py` functions take a `session_id: str` argument. Keep implementations consistent with the chosen entrypoint.
- When capturing DOM state, prefer `page.locator("body").aria_snapshot()`; use `browser_get_html` for debug HTML with `filter_tags` (defaults to `['script']`).

Developer workflows and commands (concrete)
- Create venv with uv (`uv venv --python 3.13`) and install dependencies (`uv sync`) as documented in `README.md`.
- Install Playwright browser binaries: `playwright install chromium`.
- Run in development with inspector: `fastmcp dev src/server.py` (opens inspector and allows interactive testing).
- Run session server (production-like): `python src/session_server.py`.
- Tests: `pytest` (see `pytest.ini`). Tests expect `pytest-asyncio` and cover async tools; run `uv sync` first to install dev deps.

Integration points and external dependencies
- Playwright: the code uses `playwright.async_api` extensively; prefer async implementations and use `async_playwright().start()` and `playwright_instance.stop()` lifecycle calls as shown.
- fastmcp: `FastMCP` registers tools via `@mcp.tool()` decorators. Tool signatures are how the MCP server exposes functions to LLMs — changing signatures affects the external API.

Edge cases and error handling to follow
- Always check `get_current_page()` or session page presence and return `{"error": "No browser page available"}` when absent (this pattern is used repeatedly).
- Resource cleanup: closing contexts and stopping `playwright_instance` is required to avoid orphaned browser processes (see `browser_close` and `cleanup_session`).
- Session limits: `session_server.py` enforces `MAX_SESSIONS` and background session cleanup (`session_cleanup_task`) — avoid creating unbounded sessions in tests.

Examples to copy/paste when adding tools
- Role-first click pattern (from `server.py:browser_click`):
  - If `role` and `name` provided: `locator = page.get_by_role(role, name=name)` then `await locator.click()`.
  - Else if `selector` provided: `await page.click(selector)`.
- Snapshot-return contract (from `_get_snapshot_result`):
  - Return `{"message": <str>, "url": page.url, "title": await page.title(), "snapshot": snapshot}` on success.

What not to change
- Do not change the public tool names or their parameter names (the MCP surface). If you must change them, update `README.md` and note breaking changes.

Where to add tests
- `tests/` — add async tests using `pytest-asyncio`. Mirror the tool contracts: call tool functions and assert snapshot structure or `error` keys.

If parts are unclear
- Ask for clarification and point to the specific file/line (e.g., "In `src/session_server.py`, lines ~1-120 define BrowserSession: should new tools accept session_id?").

Feedback request
- Review these instructions and tell me any missing file references or workflow steps to include. I can iterate quickly.
