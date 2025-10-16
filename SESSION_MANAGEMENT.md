# Session Management for Streamable HTTP MCP Server

## Overview

When deploying this Playwright MCP server as a streamable HTTP MCP server, session management becomes critical because:
1. Multiple clients may connect simultaneously
2. Each client needs isolated browser sessions
3. Resources must be properly cleaned up when clients disconnect

## Current Implementation (Global State)

The current implementation uses **global state** which is suitable for:
- **Single-user scenarios** (local development)
- **SSE (Server-Sent Events) transport** with one client
- **Testing and prototyping**

```python
# Global state - NOT suitable for multi-client HTTP server
browser: Optional[Browser] = None
context: Optional[BrowserContext] = None
pages: List[Page] = []
```

## Session-Based Architecture (For HTTP MCP Server)

### Option 1: Session ID-Based Storage (Recommended)

Use a dictionary to store browser instances per session:

```python
from fastmcp import FastMCP
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from typing import Optional, List, Dict, Any
import json
from datetime import datetime
from dataclasses import dataclass, field
import asyncio

mcp = FastMCP("Playwright MCP Server")

@dataclass
class BrowserSession:
    """Represents a browser session for a single client"""
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    pages: List[Page] = field(default_factory=list)
    current_page_index: int = 0
    playwright_instance: Any = None
    console_messages: List[Dict[str, Any]] = field(default_factory=list)
    network_requests: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    last_activity: float = field(default_factory=lambda: datetime.now().timestamp())

# Session storage: session_id -> BrowserSession
sessions: Dict[str, BrowserSession] = {}

def get_session(session_id: str) -> BrowserSession:
    """Get or create a browser session for the given session ID"""
    if session_id not in sessions:
        sessions[session_id] = BrowserSession()
    
    # Update last activity
    sessions[session_id].last_activity = datetime.now().timestamp()
    return sessions[session_id]

async def cleanup_session(session_id: str):
    """Clean up a browser session"""
    if session_id in sessions:
        session = sessions[session_id]
        if session.browser:
            await session.context.close()
            await session.browser.close()
            if session.playwright_instance:
                await session.playwright_instance.stop()
        del sessions[session_id]

# Modified tool example
@mcp.tool()
async def browser_open(
    session_id: str,  # Pass session ID from client
    headless: bool = False,
    width: int = 1280,
    height: int = 720
) -> str:
    """Open a new browser instance for this session"""
    session = get_session(session_id)
    
    if session.browser is not None:
        return "Browser is already open for this session"
    
    session.playwright_instance = await async_playwright().start()
    session.browser = await session.playwright_instance.chromium.launch(headless=headless)
    session.context = await session.browser.new_context(
        viewport={"width": width, "height": height}
    )
    page = await session.context.new_page()
    session.pages = [page]
    session.current_page_index = 0
    
    # Set up listeners
    page.on("console", lambda msg: session.console_messages.append({
        "type": msg.type,
        "text": msg.text,
        "location": msg.location
    }))
    
    page.on("request", lambda request: session.network_requests.append({
        "url": request.url,
        "method": request.method,
        "headers": request.headers,
        "resourceType": request.resource_type
    }))
    
    mode = "headless" if headless else "headed"
    return f"Browser opened in {mode} mode for session {session_id}"

@mcp.tool()
async def browser_close(session_id: str) -> str:
    """Close browser for this session"""
    await cleanup_session(session_id)
    return f"Browser closed for session {session_id}"
```

### Option 2: Context-Based (FastMCP Built-in)

FastMCP supports context that can be passed to tools:

```python
from fastmcp import FastMCP, Context

mcp = FastMCP("Playwright MCP Server")

# Store sessions using context
sessions: Dict[str, BrowserSession] = {}

@mcp.tool()
async def browser_open(ctx: Context, headless: bool = False) -> str:
    """Open browser using FastMCP context"""
    # Use context.request_id or custom session identifier
    session_id = ctx.request_id or ctx.meta.get("session_id", "default")
    
    session = get_session(session_id)
    # ... rest of implementation
```

### Option 3: Dependency Injection Pattern

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

class BrowserManager:
    def __init__(self):
        self.sessions: Dict[str, BrowserSession] = {}
    
    async def get_or_create_session(self, session_id: str) -> BrowserSession:
        if session_id not in self.sessions:
            self.sessions[session_id] = BrowserSession()
        return self.sessions[session_id]
    
    async def cleanup_session(self, session_id: str):
        # Cleanup logic
        pass
    
    async def cleanup_all(self):
        """Cleanup all sessions on server shutdown"""
        for session_id in list(self.sessions.keys()):
            await self.cleanup_session(session_id)

# Global manager instance
browser_manager = BrowserManager()

@mcp.tool()
async def browser_open(session_id: str, headless: bool = False) -> str:
    session = await browser_manager.get_or_create_session(session_id)
    # ... implementation
```

## Session Timeout and Cleanup

Add automatic cleanup for inactive sessions:

```python
import asyncio
from datetime import datetime

async def session_cleanup_task():
    """Background task to cleanup inactive sessions"""
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes
        
        current_time = datetime.now().timestamp()
        timeout = 1800  # 30 minutes
        
        inactive_sessions = [
            session_id for session_id, session in sessions.items()
            if current_time - session.last_activity > timeout
        ]
        
        for session_id in inactive_sessions:
            print(f"Cleaning up inactive session: {session_id}")
            await cleanup_session(session_id)

# Start cleanup task when server starts
@mcp.lifespan()
async def lifespan():
    """Manage server lifecycle"""
    # Start background cleanup task
    cleanup_task = asyncio.create_task(session_cleanup_task())
    
    try:
        yield  # Server is running
    finally:
        # Cleanup on shutdown
        cleanup_task.cancel()
        for session_id in list(sessions.keys()):
            await cleanup_session(session_id)
```

## Deployment Considerations

### 1. **HTTP Transport with Session Headers**

```python
# Client sends session ID in headers
headers = {
    "X-Session-ID": "unique-session-id-12345"
}

# Server extracts session ID from request
session_id = request.headers.get("X-Session-ID", "default")
```

### 2. **SSE Transport (Single Client)**

For SSE transport, the current global state approach works fine since there's only one active connection.

### 3. **WebSocket Transport**

```python
# Each WebSocket connection gets its own session
async def handle_websocket(websocket):
    session_id = str(uuid.uuid4())
    try:
        # Handle messages with this session_id
        pass
    finally:
        await cleanup_session(session_id)
```

### 4. **Resource Limits**

```python
MAX_SESSIONS = 10  # Limit concurrent sessions

async def create_session(session_id: str):
    if len(sessions) >= MAX_SESSIONS:
        raise Exception("Maximum number of sessions reached")
    # Create session...
```

### 5. **Browser Resource Management**

```python
# Limit pages per session
MAX_PAGES_PER_SESSION = 5

# Use browser contexts efficiently
# Each context is isolated but shares the browser process
async def ensure_browser_open(session: BrowserSession):
    if session.browser is None:
        session.playwright_instance = await async_playwright().start()
        # Use shared browser instance with separate contexts
        session.browser = await session.playwright_instance.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']  # Docker-friendly
        )
```

## Production Deployment Checklist

- [ ] Implement session-based storage
- [ ] Add session timeout and cleanup
- [ ] Set resource limits (max sessions, max pages)
- [ ] Use headless mode in production
- [ ] Add proper error handling
- [ ] Implement session authentication/authorization
- [ ] Monitor memory usage and browser processes
- [ ] Add logging for debugging
- [ ] Consider using browser pool for efficiency
- [ ] Implement graceful shutdown

## Example: Complete Session-Based Implementation

See `session_server.py` for a complete example with session management.
