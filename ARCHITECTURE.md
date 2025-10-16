# Architecture Comparison

## Single-Client Architecture (server.py)

```
┌─────────────────────────────────────────────┐
│         MCP Client (e.g., Claude)          │
└─────────────────┬───────────────────────────┘
                  │
                  │ Tool Calls (no session_id)
                  │
┌─────────────────▼───────────────────────────┐
│         Playwright MCP Server              │
│                                             │
│  ┌────────────────────────────────────┐   │
│  │      Global State                   │   │
│  │                                     │   │
│  │  • browser: Browser                │   │
│  │  • context: BrowserContext         │   │
│  │  • pages: List[Page]               │   │
│  │  • console_messages: List          │   │
│  │  • network_requests: List          │   │
│  └────────────────────────────────────┘   │
│                                             │
│  ┌────────────────────────────────────┐   │
│  │         Tools                       │   │
│  │  • browser_open()                  │   │
│  │  • browser_navigate(url)           │   │
│  │  • browser_snapshot()              │   │
│  │  • browser_close()                 │   │
│  └────────────────────────────────────┘   │
└─────────────────┬───────────────────────────┘
                  │
                  │
┌─────────────────▼───────────────────────────┐
│         Chromium Browser                   │
│         (Single Instance)                  │
└─────────────────────────────────────────────┘

✅ Simple architecture
✅ Easy to understand
✅ Perfect for development
❌ Single client only
❌ No isolation
```

---

## Multi-Client Architecture (session_server.py)

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Client A    │  │  Client B    │  │  Client C    │
│ session_a    │  │ session_b    │  │ session_c    │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       │ Tool Calls      │ Tool Calls      │ Tool Calls
       │ (session_id=a)  │ (session_id=b)  │ (session_id=c)
       │                 │                 │
┌──────▼─────────────────▼─────────────────▼──────┐
│       Playwright MCP Server (Session-Based)     │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │     Session Storage: Dict[str, Session]    │ │
│  │                                            │ │
│  │  session_a: ┌──────────────────────┐     │ │
│  │             │ BrowserSession       │     │ │
│  │             │ • browser            │     │ │
│  │             │ • pages              │     │ │
│  │             │ • console_messages   │     │ │
│  │             └──────────────────────┘     │ │
│  │                                            │ │
│  │  session_b: ┌──────────────────────┐     │ │
│  │             │ BrowserSession       │     │ │
│  │             │ • browser            │     │ │
│  │             │ • pages              │     │ │
│  │             └──────────────────────┘     │ │
│  │                                            │ │
│  │  session_c: ┌──────────────────────┐     │ │
│  │             │ BrowserSession       │     │ │
│  │             │ • browser            │     │ │
│  │             └──────────────────────┘     │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │     Background Cleanup Task                │ │
│  │  • Runs every 5 minutes                   │ │
│  │  • Removes inactive sessions (30 min)     │ │
│  │  • Enforces MAX_SESSIONS limit            │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │         Session-Aware Tools                │ │
│  │  • browser_open(session_id, ...)          │ │
│  │  • browser_navigate(url, session_id)      │ │
│  │  • browser_snapshot(session_id)           │ │
│  │  • browser_close(session_id)              │ │
│  │  • session_list()                         │ │
│  │  • session_create()                       │ │
│  └────────────────────────────────────────────┘ │
└──────┬────────────────┬────────────────┬─────────┘
       │                │                │
       │                │                │
┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
│  Chromium   │  │  Chromium   │  │  Chromium   │
│  Browser A  │  │  Browser B  │  │  Browser C  │
│ (Isolated)  │  │ (Isolated)  │  │ (Isolated)  │
└─────────────┘  └─────────────┘  └─────────────┘

✅ Multiple concurrent clients
✅ Complete isolation
✅ Automatic cleanup
✅ Resource management
✅ Production ready
⚠️  More complex
⚠️  Higher resource usage
```

---

## Request Flow Comparison

### Single-Client (server.py)

```
Client Request: browser_navigate(url="https://example.com")
     │
     ▼
Tool Function: browser_navigate(url)
     │
     ▼
Get Global State: pages[current_page_index]
     │
     ▼
Execute: page.goto(url)
     │
     ▼
Return: "Navigated to https://example.com"
```

### Multi-Client (session_server.py)

```
Client A Request: browser_navigate(url="...", session_id="a")
Client B Request: browser_navigate(url="...", session_id="b")
     │                           │
     ▼                           ▼
Tool Function                Tool Function
     │                           │
     ▼                           ▼
get_session("a")            get_session("b")
     │                           │
     ▼                           ▼
Session A State             Session B State
     │                           │
     ▼                           ▼
session_a.pages[0]          session_b.pages[0]
     │                           │
     ▼                           ▼
Execute on Page A           Execute on Page B
     │                           │
     ▼                           ▼
Return Result               Return Result
     │                           │
     ▼                           ▼
Update session_a            Update session_b
last_activity               last_activity
```

---

## Session Lifecycle

```
┌─────────────────────────────────────────────────┐
│              Session Lifecycle                  │
└─────────────────────────────────────────────────┘

1. CREATE
   session_create() → generates UUID → stores in sessions dict
   Status: Created but no browser yet

2. INITIALIZE
   browser_open(session_id) → launches browser → sets up listeners
   Status: Active with browser running

3. ACTIVE USE
   browser_navigate(), browser_click(), etc.
   Each call updates last_activity timestamp
   Status: Active

4. IDLE
   No activity for some time
   last_activity not updated
   Status: Idle (but still valid)

5. TIMEOUT
   30 minutes of no activity
   Background cleanup task detects idle session
   Status: Marked for cleanup

6. CLEANUP
   cleanup_session(session_id) called
   - Closes browser
   - Closes context
   - Stops playwright
   - Removes from sessions dict
   Status: Deleted

Timeline:
─────────────────────────────────────────────────►
0min        10min       20min       30min       31min
CREATE      ACTIVE      IDLE        TIMEOUT     CLEANUP
  ↓           ↓           ↓           ↓           ↓
  New     Working    No activity  Still idle  Removed
```

---

## Resource Management

### Memory Usage Estimate

```
Single Browser Instance:
┌────────────────────────────────────┐
│ Chromium Process: ~100-300 MB      │
│ Browser Context: ~10-50 MB         │
│ Per Page: ~10-30 MB                │
│ Python Objects: ~1-5 MB            │
└────────────────────────────────────┘
Total per session: ~120-385 MB

With 10 concurrent sessions:
Total: ~1.2-3.8 GB

Add system overhead: ~2-5 GB recommended
```

### Resource Limits

```python
# session_server.py configuration
MAX_SESSIONS = 10           # Max concurrent clients
SESSION_TIMEOUT = 1800      # 30 minutes
MAX_PAGES_PER_SESSION = 5   # Max tabs per client

# Calculated limits
Max memory: ~5 GB
Max browser processes: 10
Max pages total: 50
```

---

## Decision Tree

```
                    Start Here
                        │
                        ▼
        ┌───────────────────────────────┐
        │   How many clients?           │
        └───────────┬───────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
    Single Client          Multiple Clients
        │                       │
        ▼                       ▼
┌──────────────┐        ┌──────────────┐
│  server.py     │        │ main_        │
│              │        │ sessions.py  │
│  ✅ Simple    │        │              │
│  ✅ Fast dev  │        │  ✅ Isolated  │
│  ✅ Easy     │        │  ✅ Scalable │
│  ❌ No scale │        │  ⚠️  Complex  │
└──────────────┘        └──────────────┘
```

---

## Deployment Patterns

### Pattern 1: Local Development
```
Developer Machine
└─ server.py (global state)
   └─ Single Chromium browser
```

### Pattern 2: Personal HTTP Server
```
VPS/Cloud Server
└─ session_server.py
   └─ Multiple browser instances
      ├─ Session 1 (Your laptop)
      ├─ Session 2 (Your phone)
      └─ Session 3 (Your tablet)
```

### Pattern 3: Team Server
```
Team Server
└─ session_server.py
   └─ Multiple browser instances
      ├─ Session 1 (Alice)
      ├─ Session 2 (Bob)
      ├─ Session 3 (Charlie)
      └─ ... (up to MAX_SESSIONS)
```

### Pattern 4: Production with Load Balancer
```
            Load Balancer
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
    Server 1  Server 2  Server 3
    (Redis shared session storage)
```

---

## Quick Comparison Table

| Feature | server.py | session_server.py |
|---------|---------|------------------|
| **Architecture** | Global state | Session dictionary |
| **Clients** | 1 | 10+ (configurable) |
| **Session ID** | Not used | Required |
| **Isolation** | None | Complete |
| **Auto-cleanup** | Manual | Automatic (30 min) |
| **Resource limits** | None | MAX_SESSIONS |
| **Memory/client** | 120-385 MB | 120-385 MB |
| **Total memory** | 120-385 MB | 1.2-3.8 GB (10 clients) |
| **Setup complexity** | Low | Medium |
| **Deployment** | Local | Production |
| **Use case** | Development | Multi-user |
