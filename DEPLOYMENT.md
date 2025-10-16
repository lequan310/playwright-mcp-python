# Deployment Examples

## 1. Local Development (Current Implementation)

The `server.py` file uses global state and is suitable for:
- Single-user local development
- Testing with MCP Inspector
- SSE transport with one client

### Running locally:
```bash
# Using FastMCP CLI
fastmcp dev server.py

# Or using Python directly
python server.py
```

### Usage:
```python
# Tools are called without session_id
await browser_open(headless=False)
await browser_navigate(url="https://example.com")
await browser_snapshot()
await browser_close()
```

## 2. HTTP MCP Server (Multi-Client)

Use `session_server.py` for production deployments with multiple clients.

### Running as HTTP server:
```bash
# Install additional dependencies
pip install uvicorn

# Run with uvicorn
uvicorn main_sessions:mcp --host 0.0.0.0 --port 8000
```

### Client Usage:
```python
import requests
import uuid

# Generate unique session ID for this client
session_id = str(uuid.uuid4())

# Call tools with session_id
response = requests.post(
    "http://localhost:8000/tools/browser_open",
    json={
        "session_id": session_id,
        "headless": True,
        "width": 1280,
        "height": 720
    }
)

response = requests.post(
    "http://localhost:8000/tools/browser_navigate",
    json={
        "session_id": session_id,
        "url": "https://example.com"
    }
)

# Get snapshot
response = requests.post(
    "http://localhost:8000/tools/browser_snapshot",
    json={"session_id": session_id}
)
snapshot = response.json()

# Close browser
response = requests.post(
    "http://localhost:8000/tools/browser_close",
    json={"session_id": session_id}
)
```

## 3. Docker Deployment

### Dockerfile:
```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

WORKDIR /app

COPY pyproject.toml .
COPY session_server.py .

RUN pip install uv
RUN uv pip install --system -e .

EXPOSE 8000

CMD ["uvicorn", "main_sessions:mcp", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml:
```yaml
version: '3.8'

services:
  playwright-mcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MAX_SESSIONS=20
      - SESSION_TIMEOUT=1800
    volumes:
      - ./screenshots:/app/screenshots
    restart: unless-stopped
```

### Build and run:
```bash
docker-compose up -d
```

## 4. Using with MCP Client

### Claude Desktop Configuration:
```json
{
  "mcpServers": {
    "playwright": {
      "command": "python",
      "args": [
        "d:/Studying/ML/Others/playwright-mcp/server.py"
      ]
    }
  }
}
```

### Using with @modelcontextprotocol/sdk:
```typescript
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const transport = new StdioClientTransport({
  command: "python",
  args: ["server.py"],
});

const client = new Client({
  name: "playwright-client",
  version: "1.0.0",
}, {
  capabilities: {}
});

await client.connect(transport);

// Call tools
const result = await client.callTool({
  name: "browser_navigate",
  arguments: { url: "https://example.com" }
});
```

## 5. Environment Variables

For `session_server.py`, you can configure via environment variables:

```bash
# .env file
MAX_SESSIONS=20
SESSION_TIMEOUT=1800
HEADLESS_DEFAULT=true
BROWSER_WIDTH=1920
BROWSER_HEIGHT=1080
```

```python
import os

MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "10"))
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "1800"))
```

## 6. Load Balancing (Multiple Instances)

For high-scale deployments, use Redis for session storage:

```python
import redis
import pickle

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def get_session(session_id: str) -> BrowserSession:
    """Get session from Redis"""
    data = redis_client.get(f"session:{session_id}")
    if data:
        return pickle.loads(data)
    
    session = BrowserSession(session_id=session_id)
    save_session(session)
    return session

def save_session(session: BrowserSession):
    """Save session to Redis"""
    redis_client.setex(
        f"session:{session.session_id}",
        SESSION_TIMEOUT,
        pickle.dumps(session)
    )
```

## 7. Monitoring and Logging

Add logging for production:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

@mcp.tool()
async def browser_navigate(url: str, session_id: str = "default") -> str:
    logger.info(f"Session {session_id}: Navigating to {url}")
    # ... implementation
    logger.info(f"Session {session_id}: Successfully navigated to {url}")
```

## Performance Considerations

1. **Browser Pooling**: Reuse browser instances across sessions
2. **Resource Limits**: Set max pages, max tabs per session
3. **Timeout Management**: Auto-close inactive browsers
4. **Memory Monitoring**: Track browser memory usage
5. **Graceful Degradation**: Handle browser crashes gracefully

## Security Considerations

1. **Session Validation**: Validate session IDs
2. **Rate Limiting**: Limit requests per session
3. **URL Filtering**: Block dangerous URLs
4. **Sandboxing**: Run browsers in isolated environments
5. **Authentication**: Add API key authentication for HTTP server
