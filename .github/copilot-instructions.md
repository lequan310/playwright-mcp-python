# Playwright MCP Server - AI Coding Agent Instructions

## Project Overview

This is a **Model Context Protocol (MCP) server** providing browser automation via Playwright. The server exposes structured tools (not traditional API endpoints) that enable LLMs to interact with web pages through **accessibility-first snapshots** and **role-based locators** rather than screenshots or visual models.

**Core Philosophy**: Interact with web pages the way screen readers do - using ARIA roles/names from the accessibility tree instead of brittle CSS selectors.

## Architecture & Key Components

### MCP Server Pattern (`src/server.py`)
- Built with `fastmcp` framework - uses decorator-based tool registration (`@mcp.tool()`)
- Entry point: `if __name__ == "__main__": mcp.run(transport="streamable-http")`
- **Not a REST API**: Tools are RPC-style functions exposed via MCP protocol

### Global Browser State Management
The server maintains **singleton browser state** across tool invocations:
```python
browser: Optional[Browser] = None
context: Optional[BrowserContext] = None
pages: list[Page] = []  # Supports multiple tabs
current_page_index: int = 0
```

**Critical Pattern**: Most tools call `get_current_page()` to access the active tab. Tools like `browser_navigate` use `ensure_browser()` to auto-initialize if needed.

### Element Locator System (`src/schemas/element.py`)
Two mutually exclusive ways to locate elements:

1. **AriaNode** (preferred): `{"role": "button", "name": "Submit"}`
2. **Selector** (fallback): `{"selector": "button.submit-btn"}`

Both implement `ElementLocator` union type. The `_get_locator()` helper converts these to Playwright locators and handles optional `nth` indexing for multiple matches.

### Auto-Snapshot Pattern
**Every mutating tool returns snapshot + metadata**:
```python
return await _get_snapshot_result(page, "Action message")
# Returns: {message, url, title, snapshot}
```

The `snapshot` field contains the accessibility tree from `page.locator("body").aria_snapshot()` - this is the **primary way LLMs understand page state**.

## Development Workflows

### Setup & Running
```bash
# Install dependencies (requires Python 3.13+ and uv)
uv sync

# Install Playwright browsers
playwright install chromium

# Dev mode with FastMCP inspector (recommended for testing)
fastmcp dev src/server.py

# Single-client mode
python src/server.py
```

### Testing
- **Tests are currently disabled** (see `pytest.ini` and commented-out CI workflow)
- When implementing tests, use `pytest-asyncio` with `asyncio_mode = auto`
- Test discovery: `tests/test_*.py` or `tests/*_test.py`

### Linting & Formatting
```bash
# Run ruff (minimal ruleset: E4, E7, E9, F, I)
ruff check src/
ruff format src/
```

CI runs these checks on `src/**` changes via `.github/workflows/ci.yaml`.

## Code Conventions

### Tool Definition Pattern
```python
@mcp.tool(tags={"category"})  # tags optional
async def browser_action(
    param: Annotated[Type, "Human-readable description for LLM"],
    optional_param: Annotated[Optional[Type], "Description"] = None,
) -> dict[str, Any] | str:
    """Docstring becomes tool description in MCP"""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}
    
    # Do work
    return await _get_snapshot_result(page, "Success message")
```

**Key Details**:
- Use `Annotated[Type, "description"]` for all parameters (FastMCP requirement)
- Return types: `dict[str, Any]` for snapshots, `str` for simple messages, `Image` for screenshots
- Always check `get_current_page()` before operations
- Use `_get_locator()` to handle `ElementLocator` union types

### Error Handling
Return errors as dicts, don't raise exceptions in most cases:
```python
return {"error": "Failure reason", "element": element_description}
```

### Page Lifecycle Listeners
New pages automatically get console/network listeners via `_setup_page_listeners()`. These are wired up in:
1. `_initialize_browser()` via `context.on("page", ...)`
2. Manual tab creation in `browser_tabs(action="create")`

## Key Files & Directories

- `src/server.py` - All 20+ MCP tools (navigation, interaction, snapshots, tabs)
- `src/schemas/element.py` - `ElementLocator` union type (`AriaNode | Selector`) and `FormField`
- `pyproject.toml` - Uses `uv` with `link-mode = "copy"`, Python 3.13+, `fastmcp + patchright + trafilatura`
- `ruff.toml` - Minimal linting rules, double quotes for docstrings
- `.github/workflows/ci.yaml` - Only lint job active (test job commented out)

## Important Dependencies

- **patchright**: Playwright fork with stealth features (anti-detection)
- **fastmcp**: MCP server framework with decorator-based tools
- **trafilatura**: Used in `browser_get_text_content()` to extract clean markdown from HTML

## Common Pitfalls

1. **Don't use REST API patterns** - Tools are async functions, not HTTP handlers
2. **Always use absolute paths** - For file uploads, use absolute paths in `browser_file_upload()`
3. **nth indexing is 0-based** - First element is `nth=0`, not `nth=1`
4. **Prefer AriaNode over Selector** - More reliable and aligns with accessibility-first design
5. **Browser state persists** - `browser_close()` must be called to clean up; auto-closes when last page closes
6. **Tools are stateful** - Browser instance and pages live across multiple tool calls

## When Adding New Tools

1. Follow the `@mcp.tool()` decorator pattern with appropriate tags
2. Use `Annotated` for all parameters with LLM-friendly descriptions
3. Call `get_current_page()` and handle None case
4. Return snapshot via `_get_snapshot_result()` for state-changing actions
5. Update README.md tools documentation if adding major features

## Testing Locally

Use `fastmcp dev src/server.py` to launch the inspector UI - it provides:
- Interactive tool testing with parameter forms
- Real-time browser window to see actions
- JSON response inspection

This is the fastest way to validate new tool implementations.
