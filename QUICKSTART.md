# Quick Start Guide

## Local Development (Simple)

### 1. Run the server
```bash
fastmcp dev server.py
```

### 2. Open browser
```python
browser_open(headless=False, width=1920, height=1080)
```

### 3. Navigate and interact
```python
browser_navigate(url="https://example.com")
browser_snapshot()
browser_click(element="Login button", ref="#login-btn")
```

### 4. Close browser
```python
browser_close()
```

---

## Production HTTP Server (Multi-Client)

### 1. Run the server
```bash
python session_server.py
```

### 2. Client creates session
```python
import uuid
session_id = str(uuid.uuid4())

# Open browser for this session
browser_open(session_id=session_id, headless=True)
```

### 3. All operations use session_id
```python
browser_navigate(url="https://example.com", session_id=session_id)
browser_snapshot(session_id=session_id)
browser_click(element="Login", ref="#login", session_id=session_id)
```

### 4. Close when done
```python
browser_close(session_id=session_id)
```

---

## Key Differences

| Feature | server.py | session_server.py |
|---------|---------|------------------|
| Session ID | ❌ Not needed | ✅ Required |
| Multiple clients | ❌ No | ✅ Yes |
| Auto-cleanup | ❌ No | ✅ Yes (30 min) |
| Resource limits | ❌ No | ✅ Yes (10 sessions) |
| Production ready | ⚠️ Single client only | ✅ Yes |

---

## Common Patterns

### Pattern 1: Basic Navigation
```python
await browser_open()
await browser_navigate("https://example.com")
snapshot = await browser_snapshot()
await browser_close()
```

### Pattern 2: Form Filling
```python
await browser_open()
await browser_navigate("https://example.com/login")
await browser_fill_form([
    {"ref": "#username", "value": "user@example.com"},
    {"ref": "#password", "value": "password123"}
])
await browser_click(element="Submit", ref="#submit-btn")
await browser_close()
```

### Pattern 3: Multi-Tab Workflow
```python
await browser_open()
await browser_navigate("https://example.com")
await browser_tabs(action="create")  # New tab
await browser_navigate("https://another-site.com")
tabs = await browser_tabs(action="list")
await browser_tabs(action="select", index=0)  # Back to first tab
await browser_close()
```

### Pattern 4: Session Management (HTTP Server)
```python
# Client A
session_a = str(uuid.uuid4())
await browser_open(session_id=session_a)
await browser_navigate("https://site1.com", session_id=session_a)

# Client B (independent)
session_b = str(uuid.uuid4())
await browser_open(session_id=session_b)
await browser_navigate("https://site2.com", session_id=session_b)

# Both clients work independently
```

---

## Environment Setup

### Install Dependencies
```bash
# Using pip
pip install fastmcp playwright

# Using uv
uv pip install fastmcp playwright

# Install Playwright browsers
playwright install chromium
```

### Run Development Server
```bash
# Option 1: FastMCP dev mode
fastmcp dev server.py

# Option 2: Direct Python
python server.py

# Option 3: With MCP Inspector
npx @modelcontextprotocol/inspector python server.py
```

### Run Production Server
```bash
# Install uvicorn if needed
pip install uvicorn

# Run with uvicorn
uvicorn main_sessions:mcp --host 0.0.0.0 --port 8000
```

---

## Troubleshooting

### Browser doesn't open
```python
# Check if already open
# Error: "Browser is already open"
await browser_close()  # Close first
await browser_open()   # Then open again
```

### Session timeout
```python
# Default timeout: 30 minutes
# Session automatically cleaned up after 30 min of inactivity
# Each tool call resets the timeout
```

### Too many sessions
```python
# Error: "Maximum number of sessions reached"
# Default limit: 10 concurrent sessions
# Oldest inactive session is automatically cleaned up
```

### Memory issues
```python
# Always close browser when done
await browser_close(session_id=session_id)

# Use headless mode in production
await browser_open(session_id=session_id, headless=True)
```

---

## Best Practices

1. **Always close browsers**
   ```python
   try:
       await browser_open()
       # ... do work
   finally:
       await browser_close()
   ```

2. **Use headless in production**
   ```python
   await browser_open(headless=True)  # Saves resources
   ```

3. **Generate unique session IDs**
   ```python
   import uuid
   session_id = str(uuid.uuid4())  # Unique per client
   ```

4. **Handle errors gracefully**
   ```python
   try:
       await browser_navigate(url)
   except Exception as e:
       await browser_close()
       raise
   ```

5. **Monitor active sessions**
   ```python
   # In session_server.py
   sessions_info = await session_list()
   print(sessions_info)
   ```

---

## Integration Examples

### With Claude Desktop
Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "playwright": {
      "command": "python",
      "args": ["d:/path/to/server.py"]
    }
  }
}
```

### With Python Client
```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async with stdio_client(
    StdioServerParameters(
        command="python",
        args=["server.py"]
    )
) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("browser_navigate", {
            "url": "https://example.com"
        })
```

---

## Quick Reference: All Tools

### Lifecycle
- `browser_open` - Start browser
- `browser_close` - Stop browser

### Navigation
- `browser_navigate` - Go to URL
- `browser_navigate_back` - Go back
- `browser_resize` - Change window size

### Inspection
- `browser_snapshot` - Get accessibility tree
- `browser_take_screenshot` - Capture image
- `browser_console_messages` - Get console logs
- `browser_network_requests` - Get network activity

### Interaction
- `browser_click` - Click element
- `browser_hover` - Hover element
- `browser_type` - Type text
- `browser_press_key` - Press key
- `browser_drag` - Drag and drop

### Forms
- `browser_fill_form` - Fill multiple fields
- `browser_select_option` - Select dropdown
- `browser_file_upload` - Upload files

### Advanced
- `browser_evaluate` - Run JavaScript
- `browser_wait_for` - Wait for conditions
- `browser_handle_dialog` - Handle alerts

### Tabs
- `browser_tabs` - Manage tabs

### Session (session_server.py only)
- `session_list` - List active sessions
- `session_create` - Create new session
