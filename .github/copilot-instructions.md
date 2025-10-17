# Playwright MCP Server - Developer Guide

## Architecture Overview

This is a **Model Context Protocol (MCP) server** that exposes browser automation via Playwright. Two implementations exist:

- **`src/server.py`**: Single-client with global state (for local development)
- **`src/session_server.py`**: Multi-client with session isolation (for production HTTP deployments)

**Critical distinction**: All tools in `session_server.py` require a `session_id` parameter; `server.py` tools do not.

## Key Patterns

### 1. Browser State Management

Global state in `server.py`:
```python
browser: Optional[Browser] = None
context: Optional[BrowserContext] = None
pages: list[Page] = []
current_page_index: int = 0
console_messages: list[dict[str, Any]] = []
network_requests: list[dict[str, Any]] = []
```

Session-isolated state in `session_server.py`:
```python
@dataclass
class BrowserSession:
    session_id: str
    browser: Optional[Browser] = None
    # ... same fields as global state
```

### 2. Auto-initialization Pattern

Browser is lazy-initialized in `session_server.py` to simplify client usage:
```python
async def browser_navigate(url: str, session_id: str = "default") -> str:
    session = get_session(session_id)
    if session.browser is None:
        await browser_open(session_id=session_id)  # Auto-open
    # ... proceed with navigation
```

### 3. Page Listeners Setup

Every new page/tab must have listeners attached in `_setup_page_listeners()`:
- Console message capture
- Network request logging

**Always call this when creating new pages** (see `browser_tabs` create action).

### 4. Anti-Detection Configuration

Standard anti-bot configuration applied in `_initialize_browser()`:
- Custom user agent
- Disable automation flags via `add_init_script()`
- Spoof navigator properties (`webdriver`, `plugins`, `languages`)

## Development Workflow

### Running Locally
```bash
fastmcp dev server.py  # Single-client mode
```

### Testing Multi-Client Features
```bash
python session_server.py  # Runs with session cleanup task
```

### Installing Dependencies
```bash
uv sync  # Uses pyproject.toml
playwright install chromium  # Install browser binaries
```

### Code Formatting
```bash
ruff check .  # Linting only (no formatter configured)
```

## Tool Implementation Guidelines

### Adding New Tools to Both Servers

1. **In `server.py`**: No `session_id` parameter
```python
@mcp.tool()
async def browser_new_feature() -> str:
    page = get_current_page()
    if not page:
        return "No browser page available"
    # ... implementation
```

2. **In `session_server.py`**: Add `session_id` parameter
```python
@mcp.tool()
async def browser_new_feature(session_id: str = "default") -> str:
    session = get_session(session_id)
    page = get_current_page(session)
    if not page:
        return "No browser page available"
    # ... implementation
```

### Element Interaction Pattern

All interaction tools use dual parameters:
- `element`: Human-readable description for permission/logging
- `ref`: CSS selector or accessibility reference from `browser_snapshot()`

Example: `browser_click(element="Login button", ref="#login-btn")`

## Session Lifecycle (session_server.py)

- **Auto-creation**: First tool call creates session
- **Timeout**: 30 minutes of inactivity (`SESSION_TIMEOUT`)
- **Max concurrent**: 10 sessions (`MAX_SESSIONS`)
- **Cleanup**: Background task runs every 5 minutes (`session_cleanup_task()`)
- **LRU eviction**: Oldest inactive session removed when limit reached

## Testing Notes

- `tests/` directory exists but is currently empty
- Dependencies include pytest suite (pytest-asyncio, pytest-cov, pytest-mock)
- No CI/CD configuration found

## Common Pitfalls

1. **Forgetting session_id**: When porting code between servers, remember to add/remove `session_id` parameter
2. **Missing page listeners**: New pages need `_setup_page_listeners(page, session)` call
3. **Browser not closed**: `session_server.py` has auto-cleanup, but explicit `browser_close()` is cleaner
4. **Screenshot return type**: Returns `Image` object from `fastmcp.utilities.types`, not base64 string
