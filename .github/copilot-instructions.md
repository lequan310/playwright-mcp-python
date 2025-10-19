## Playwright MCP Server — AI Coding Assistant Notes

Quick, targeted guidance to help an AI agent be productive in this repository.

### Big picture
- This project implements a Model Context Protocol (MCP) server that exposes Playwright-driven browser automation as LLM-callable tools.
- Two entrypoints:
  - `src/server.py` — single-client, inspector-friendly development server (used with `fastmcp dev`).
  - `src/session_server.py` — multi-client sessioned server; uses `session_id` to isolate browser state.
- Accessibility-first approach: every action returns an accessibility snapshot (`page.locator("body").aria_snapshot()`) rather than relying on visual selectors.

### Key files to read first
- `README.md` — install & run notes, tool summaries.
- `pyproject.toml` — dependencies (fastmcp, patchright, playwright). Python >= 3.13 required.
- `src/server.py` — example of core tools for single-client usage.
- `src/session_server.py` — session lifecycle, cleanup, and how tools accept `session_id`.
- `src/schemas/element.py` — Pydantic models for locators and form fields (AriaLabel, Selector, FormField).

### How to run (developer flow)
- Create venv and install deps (project uses `uv` in README):
  - `uv venv --python 3.13`
  - `uv sync`
  - `playwright install chromium`
- Dev with inspector (fast feedback):
  - `fastmcp dev src/server.py`
- Production / multi-client mode:
  - `python src/session_server.py`
- Tests: run `pytest -v` (tests live in `tests/`, `pytest.ini` configures markers and coverage).

### Project-specific patterns & conventions
- Tools are FastMCP tools decorated with `@mcp.tool()` and exposed to the MCP runtime. Follow existing return shapes (JSON-serializable dicts or `Image` from `fastmcp.utilities.types`).
- Locator strategy: prefer `AriaLabel` (role + name) where possible. `ElementLocator = Union[AriaLabel, Selector]` in `src/schemas/element.py`.
  - Example: `page.get_by_role(locator.role, name=locator.name)` used across code.
- Snapshot-first: after most interactions the code calls `_get_snapshot_result(page, message)` which waits for load state, grabs `aria_snapshot`, and returns `{message, url, title, snapshot}`. New tools should reuse this helper when appropriate.
- Session semantics: `src/session_server.py` stores sessions in `sessions: Dict[str, BrowserSession]`. Tools in the session server accept a `session_id: str = "default"` parameter. Clean-up runs in the background (`session_cleanup_task`).
- Browser initialization: both servers call `async_playwright().start()` and create contexts with consistent `user_agent`, `locale`, and `viewport`. They also call `page.add_init_script` to hide `navigator.webdriver` and spoof plugins/languages — preserve this when adding features that rely on UA/feature flags.

### Adding or changing a tool (concrete steps)
1. Add function in `src/server.py` (single-client) or `src/session_server.py` (sessioned). Decorate with `@mcp.tool()`.
2. Keep signatures JSON-serializable. If returning an image, return `Image(data=bytes, format='png')`.
3. Use `_get_locator(page, locator, nth)` to convert `ElementLocator` to a Playwright locator and build consistent debug descriptions.
4. After performing the action, return `_get_snapshot_result(page, "Your message")` where appropriate.
5. Update `README.md` tools summary if you add a top-level, user-facing tool.

### Testing and linting notes
- Tests are discovered under `tests/` according to `pytest.ini`. Use `pytest -k <name> -v` to run subsets.
- Linting uses ruff (configured in `ruff.toml`). The project lists `ruff` in `dev` dependencies.

### Integration & external dependencies
- Playwright is required and must have browser binaries installed via `playwright install`.
- The server depends on `fastmcp` (runtime for exposing tools to LLMs) and `patchright` wrapper for playwright async APIs.

### Examples (call-signature reminders)
- Click (sessioned):
  - `browser_click(element: str, locator: ElementLocator, nth: Optional[int]=None, session_id: str='default', ...)`
- Snapshot helper returns:
  - `{ "message": str, "url": str, "title": str, "snapshot": <accessibility snapshot dict> }`

If anything here is unclear or you'd like more examples (tool wiring, test examples, or a checklist for PRs), tell me what to expand and I'll iterate.
