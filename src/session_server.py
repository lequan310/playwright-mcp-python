"""
Playwright MCP Server with Session Management
This version supports multiple concurrent clients with isolated browser sessions.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

mcp = FastMCP("Playwright MCP Server (Session-Based)")


@dataclass
class BrowserSession:
    """Represents an isolated browser session for a single client"""

    session_id: str
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
MAX_SESSIONS = 10
SESSION_TIMEOUT = 1800  # 30 minutes in seconds


def _setup_page_listeners(page: Page, session: BrowserSession) -> None:
    """Set up console and network listeners for a page"""
    # Set up console message listener
    page.on(
        "console",
        lambda msg: session.console_messages.append(
            {"type": msg.type, "text": msg.text, "location": msg.location}
        ),
    )

    # Set up network request listener
    page.on(
        "request",
        lambda request: session.network_requests.append(
            {
                "url": request.url,
                "method": request.method,
                "headers": request.headers,
                "resourceType": request.resource_type,
            }
        ),
    )


async def _initialize_browser(
    session: BrowserSession,
    headless: bool = True,
    width: int = 1920,
    height: int = 1080,
) -> Page:
    """Initialize browser with consistent settings for a session"""

    session.playwright_instance = await async_playwright().start()
    session.browser = await session.playwright_instance.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--disable-info-bars"],
    )

    # Handle browser close event
    def handle_browser_close():
        session.browser = None
        session.context = None
        session.pages = []
        session.playwright_instance = None
        session.console_messages = []
        session.network_requests = []
        session.current_page_index = 0

    session.browser.on("disconnected", handle_browser_close)

    session.context = await session.browser.new_context(
        viewport={"width": width, "height": height},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    page = await session.context.new_page()
    session.pages = [page]
    session.current_page_index = 0
    session.console_messages = []
    session.network_requests = []

    # Set up listeners
    _setup_page_listeners(page, session)

    # Hide webdriver flag
    await page.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    """
    )

    # Spoof plugins & languages
    await page.add_init_script(
        """
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
    """
    )

    return page


def get_session(session_id: str) -> BrowserSession:
    """Get or create a browser session for the given session ID"""
    if session_id not in sessions:
        if len(sessions) >= MAX_SESSIONS:
            # Clean up oldest inactive session
            oldest_session_id = min(
                sessions.keys(), key=lambda sid: sessions[sid].last_activity
            )
            asyncio.create_task(cleanup_session(oldest_session_id))

        sessions[session_id] = BrowserSession(session_id=session_id)

    # Update last activity
    sessions[session_id].last_activity = datetime.now().timestamp()
    return sessions[session_id]


async def cleanup_session(session_id: str):
    """Clean up a browser session and release resources"""
    if session_id in sessions:
        session = sessions[session_id]
        try:
            if session.browser:
                await session.context.close()
                await session.browser.close()
                if session.playwright_instance:
                    await session.playwright_instance.stop()
        except Exception as e:
            print(f"Error cleaning up session {session_id}: {e}")
        finally:
            del sessions[session_id]


async def session_cleanup_task():
    """Background task to cleanup inactive sessions"""
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes

        current_time = datetime.now().timestamp()

        inactive_sessions = [
            session_id
            for session_id, session in sessions.items()
            if current_time - session.last_activity > SESSION_TIMEOUT
        ]

        for session_id in inactive_sessions:
            print(f"Cleaning up inactive session: {session_id}")
            await cleanup_session(session_id)


def get_current_page(session: BrowserSession) -> Optional[Page]:
    """Get the current active page for a session"""
    if session.pages and 0 <= session.current_page_index < len(session.pages):
        return session.pages[session.current_page_index]
    return None


async def _get_snapshot_result(
    page: Optional[Page], action_message: str
) -> Dict[str, Any]:
    """Get browser snapshot with action result message

    Args:
        page: The page to capture snapshot from
        action_message: Message describing the action that was performed

    Returns:
        Dict containing action message, url, title, and snapshot
    """
    if not page:
        return {"error": "No browser page available", "message": action_message}

    try:
        snapshot = await page.locator("body").aria_snapshot()
        page_url = page.url
        page_title = await page.title()

        return {
            "message": action_message,
            "url": page_url,
            "title": page_title,
            "snapshot": snapshot,
        }
    except Exception as e:
        return {
            "error": f"Failed to capture snapshot: {str(e)}",
            "message": action_message,
        }


# Browser Lifecycle Tools


@mcp.tool()
async def browser_open(
    session_id: str = "default",
    headless: bool = True,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """Open a new browser instance for this session

    Args:
        session_id: Unique identifier for this client session
        headless: Whether to run browser in headless mode
        width: Initial browser width
        height: Initial browser height
    """
    session = get_session(session_id)

    if session.browser is not None:
        return f"Browser is already open for session {session_id}"

    await _initialize_browser(session, headless=headless, width=width, height=height)

    mode = "headless" if headless else "headed"
    return f"Browser opened in {mode} mode for session {session_id} with viewport {width}x{height}"


@mcp.tool()
async def browser_close(session_id: str = "default") -> str:
    """Close the browser and clean up all resources for this session

    Args:
        session_id: Unique identifier for this client session
    """
    await cleanup_session(session_id)
    return f"Browser closed and resources cleaned up for session {session_id}"


# Core Navigation Tools


@mcp.tool()
async def browser_navigate(url: str, session_id: str = "default") -> Dict[str, Any]:
    """Navigate to a URL

    Args:
        url: The URL to navigate to
        session_id: Unique identifier for this client session
    """
    session = get_session(session_id)

    if session.browser is None:
        # Auto-open browser if not already open
        await browser_open(session_id=session_id)
        session = get_session(session_id)

    page = get_current_page(session)
    await page.goto(url)
    return await _get_snapshot_result(page, f"Navigated to {url}")


@mcp.tool()
async def browser_navigate_back(session_id: str = "default") -> Dict[str, Any]:
    """Go back to the previous page

    Args:
        session_id: Unique identifier for this client session
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return {"error": "No browser page available"}

    await page.go_back()
    return await _get_snapshot_result(page, "Navigated back")


# @mcp.tool()
# async def browser_search(query: str, session_id: str = "default") -> str:
#     """Search for a topic using Google search

#     Args:
#         query: The search query or topic to search for
#         session_id: Unique identifier for this client session
#     """
#     session = get_session(session_id)

#     if session.browser is None:
#         # Auto-open browser if not already open
#         await browser_open(session_id=session_id)
#         session = get_session(session_id)

#     page = get_current_page(session)
#     encoded_query = quote_plus(query)
#     search_url = f"https://www.google.com/search?q={encoded_query}"
#     await page.goto(search_url)
#     return f"Searched for '{query}' on Google: {search_url}"


@mcp.tool()
async def browser_resize(width: int, height: int, session_id: str = "default") -> str:
    """Resize the browser window

    Args:
        width: Width of the browser window
        height: Height of the browser window
        session_id: Unique identifier for this client session
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return "No browser page available"

    await page.set_viewport_size({"width": width, "height": height})
    return f"Browser resized to {width}x{height}"


# Snapshot and Screenshot Tools


@mcp.tool()
async def browser_snapshot(session_id: str = "default") -> dict[str, Any]:
    """Capture accessibility snapshot of the current page

    Args:
        session_id: Unique identifier for this client session
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return {"error": "No browser page available"}

    snapshot = await page.locator("body").aria_snapshot()

    # Get page metadata
    page_url = page.url
    page_title = await page.title()

    # Combine all information
    result = {"url": page_url, "title": page_title, "snapshot": snapshot}

    return result


@mcp.tool()
async def browser_take_screenshot(
    session_id: str = "default",
    type: str = "png",
    element: Optional[str] = None,
    ref: Optional[str] = None,
    fullPage: bool = False,
) -> str:
    """Take a screenshot of the current page

    Args:
        session_id: Unique identifier for this client session
        type: Image format (png or jpeg)
        element: Human-readable element description
        ref: Exact target element reference from the page snapshot
        fullPage: Take screenshot of full scrollable page
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return "No browser page available"

    screenshot_options = {"type": type}

    if element and ref:
        # Screenshot specific element
        element_handle = await page.query_selector(ref)
        if element_handle:
            screenshot_bytes = await element_handle.screenshot(**screenshot_options)
        else:
            raise ValueError(f"Element not found: {ref}")
    else:
        # Screenshot full page or viewport
        screenshot_options["full_page"] = fullPage
        screenshot_bytes = await page.screenshot(**screenshot_options)

    return Image(data=screenshot_bytes, format=type)


@mcp.tool()
async def browser_get_html(
    session_id: str = "default",
    selector: Optional[str] = None,
    maxLength: int = 50000,
    filter_tags: Optional[list[str]] = None,
) -> str:
    """Get HTML content for debugging when locators fail

    Args:
        session_id: Unique identifier for this client session
        selector: CSS selector to get HTML from (defaults to body)
        maxLength: Maximum characters to return (default 50000)
        filter_tags: List of tag names to remove (e.g., ['script', 'style']). Defaults to ['script']
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return json.dumps({"error": "No browser page available"}, indent=2)

    # Default to filtering script tags
    if filter_tags is None:
        filter_tags = ["script"]

    try:
        if selector:
            element = await page.query_selector(selector)
            if not element:
                return json.dumps({"error": f"Element not found: {selector}"}, indent=2)
            html = await element.inner_html()
        else:
            html = await page.inner_html("body")

        # Filter out unwanted tags
        if filter_tags:
            import re

            for tag in filter_tags:
                # Remove opening and closing tags plus content
                pattern = f"<{tag}\\b[^>]*>.*?</{tag}>"
                html = re.sub(pattern, "", html, flags=re.DOTALL | re.IGNORECASE)

        # Truncate if too long
        original_length = len(html)
        if len(html) > maxLength:
            html = (
                html[:maxLength]
                + f"\n\n... [truncated {len(html) - maxLength} characters]"
            )

        return json.dumps(
            {
                "selector": selector or "body",
                "html": html,
                "length": len(html),
                "original_length": original_length,
                "filtered_tags": filter_tags,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": f"Failed to get HTML: {str(e)}"}, indent=2)


# Session Management Tools


@mcp.tool()
async def session_list() -> str:
    """List all active sessions"""
    if not sessions:
        return "No active sessions"

    session_info = []
    current_time = datetime.now().timestamp()

    for session_id, session in sessions.items():
        inactive_time = current_time - session.last_activity
        session_info.append(
            {
                "session_id": session_id,
                "browser_open": session.browser is not None,
                "num_pages": len(session.pages),
                "created_at": datetime.fromtimestamp(session.created_at).isoformat(),
                "last_activity": datetime.fromtimestamp(
                    session.last_activity
                ).isoformat(),
                "inactive_seconds": int(inactive_time),
            }
        )

    return json.dumps(session_info, indent=2)


@mcp.tool()
async def session_create() -> str:
    """Create a new session and return its ID"""
    session_id = str(uuid.uuid4())
    get_session(session_id)  # Creates the session
    return json.dumps({"session_id": session_id})


# Interaction Tools


@mcp.tool()
async def browser_click(
    element: str,
    role: Optional[str] = None,
    name: Optional[str] = None,
    selector: Optional[str] = None,
    session_id: str = "default",
    doubleClick: bool = False,
    button: str = "left",
    modifiers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Perform click on a web page

    Args:
        element: Human-readable element description
        role: ARIA role of the element (e.g., 'button', 'link', 'textbox')
        name: Accessible name of the element (from snapshot)
        selector: CSS selector (fallback if role/name not available)
        session_id: Unique identifier for this client session
        doubleClick: Whether to perform a double click
        button: Button to click (left, right, middle)
        modifiers: Modifier keys to press (Alt, Control, Meta, Shift)
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return {"error": "No browser page available"}

    click_options = {"button": button}
    if modifiers:
        click_options["modifiers"] = modifiers

    try:
        # Prefer role-based locators (more reliable)
        if role and name:
            locator = page.get_by_role(role, name=name)
            if doubleClick:
                await locator.dblclick(**click_options)
                message = f"Double-clicked on {element} (role={role}, name={name})"
            else:
                await locator.click(**click_options)
                message = f"Clicked on {element} (role={role}, name={name})"
        elif selector:
            if doubleClick:
                await page.dblclick(selector, **click_options)
                message = f"Double-clicked on {element} (selector={selector})"
            else:
                await page.click(selector, **click_options)
                message = f"Clicked on {element} (selector={selector})"
        else:
            return {"error": "Must provide either (role + name) or selector"}

        return await _get_snapshot_result(page, message)
    except Exception as e:
        return {"error": f"Failed to click: {str(e)}", "element": element}


@mcp.tool()
async def browser_hover(
    element: str,
    role: Optional[str] = None,
    name: Optional[str] = None,
    selector: Optional[str] = None,
    session_id: str = "default",
) -> Dict[str, Any]:
    """Hover over element on page

    Args:
        element: Human-readable element description
        role: ARIA role of the element (e.g., 'button', 'link', 'textbox')
        name: Accessible name of the element (from snapshot)
        selector: CSS selector (fallback if role/name not available)
        session_id: Unique identifier for this client session
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return {"error": "No browser page available"}

    try:
        # Prefer role-based locators
        if role and name:
            await page.get_by_role(role, name=name).hover()
            message = f"Hovered over {element} (role={role}, name={name})"
        elif selector:
            await page.hover(selector)
            message = f"Hovered over {element} (selector={selector})"
        else:
            return {"error": "Must provide either (role + name) or selector"}

        return await _get_snapshot_result(page, message)
    except Exception as e:
        return {"error": f"Failed to hover: {str(e)}", "element": element}


@mcp.tool()
async def browser_type(
    element: str,
    text: str,
    role: Optional[str] = None,
    name: Optional[str] = None,
    selector: Optional[str] = None,
    session_id: str = "default",
    submit: bool = False,
    slowly: bool = False,
) -> Dict[str, Any]:
    """Type text into editable element

    Args:
        element: Human-readable element description
        text: Text to type into the element
        role: ARIA role of the element (e.g., 'textbox', 'searchbox', 'combobox')
        name: Accessible name of the element (from snapshot)
        selector: CSS selector (fallback if role/name not available)
        session_id: Unique identifier for this client session
        submit: Whether to submit (press Enter after)
        slowly: Whether to type one character at a time
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return {"error": "No browser page available"}

    try:
        # Prefer role-based locators
        if role and name:
            locator = page.get_by_role(role, name=name)
            if slowly:
                await locator.type(text)
            else:
                await locator.fill(text)

            if submit:
                await locator.press("Enter")
                message = f"Typed '{text}' into {element} and submitted (role={role}, name={name})"
            else:
                message = f"Typed '{text}' into {element} (role={role}, name={name})"
        elif selector:
            if slowly:
                await page.type(selector, text)
            else:
                await page.fill(selector, text)

            if submit:
                await page.press(selector, "Enter")
                message = (
                    f"Typed '{text}' into {element} and submitted (selector={selector})"
                )
            else:
                message = f"Typed '{text}' into {element} (selector={selector})"
        else:
            return {"error": "Must provide either (role + name) or selector"}

        return await _get_snapshot_result(page, message)
    except Exception as e:
        return {"error": f"Failed to type: {str(e)}", "element": element}


@mcp.tool()
async def browser_press_key(key: str, session_id: str = "default") -> Dict[str, Any]:
    """Press a key on the keyboard

    Args:
        key: Name of the key to press (e.g., ArrowLeft, a, Enter)
        session_id: Unique identifier for this client session
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return {"error": "No browser page available"}

    await page.keyboard.press(key)
    return await _get_snapshot_result(page, f"Pressed key: {key}")


# Form and Selection Tools


@mcp.tool()
async def browser_fill_form(
    fields: List[Dict[str, str]], session_id: str = "default"
) -> Dict[str, Any]:
    """Fill multiple form fields

    Args:
        fields: List of fields to fill, each with 'element', 'value', and either ('role' + 'name') or 'selector'
        session_id: Unique identifier for this client session
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return {"error": "No browser page available"}

    filled_fields = []
    errors = []

    for fld in fields:
        role = fld.get("role")
        name = fld.get("name")
        selector = fld.get("selector")
        value = fld.get("value")
        element_desc = fld.get("element", name or selector)

        if not value:
            continue

        try:
            if role and name:
                await page.get_by_role(role, name=name).fill(value)
                filled_fields.append(f"{element_desc} (role={role})")
            elif selector:
                await page.fill(selector, value)
                filled_fields.append(f"{element_desc} (selector)")
            else:
                errors.append(f"{element_desc}: missing role+name or selector")
        except Exception as e:
            errors.append(f"{element_desc}: {str(e)}")

    message = f"Filled {len(filled_fields)} fields: {', '.join(filled_fields)}"
    if errors:
        message += f"\nErrors: {'; '.join(errors)}"

    return await _get_snapshot_result(page, message)


@mcp.tool()
async def browser_select_option(
    element: str,
    values: List[str],
    role: Optional[str] = None,
    name: Optional[str] = None,
    selector: Optional[str] = None,
    session_id: str = "default",
) -> Dict[str, Any]:
    """Select an option in a dropdown

    Args:
        element: Human-readable element description
        values: Array of values to select
        role: ARIA role of the element (typically 'combobox' or 'listbox')
        name: Accessible name of the element (from snapshot)
        selector: CSS selector (fallback if role/name not available)
        session_id: Unique identifier for this client session
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return {"error": "No browser page available"}

    try:
        if role and name:
            await page.get_by_role(role, name=name).select_option(values)
            message = f"Selected {values} in {element} (role={role}, name={name})"
        elif selector:
            await page.select_option(selector, values)
            message = f"Selected {values} in {element} (selector={selector})"
        else:
            return {"error": "Must provide either (role + name) or selector"}

        return await _get_snapshot_result(page, message)
    except Exception as e:
        return {"error": f"Failed to select option: {str(e)}", "element": element}


@mcp.tool()
async def browser_file_upload(
    paths: Optional[List[str]] = None, session_id: str = "default"
) -> str:
    """Upload one or multiple files

    Args:
        paths: Absolute paths to files to upload. If omitted, file chooser is cancelled.
        session_id: Unique identifier for this client session
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return "No browser page available"

    async with page.expect_file_chooser() as fc_info:
        # Wait for file chooser to appear (triggered by previous action)
        file_chooser = await fc_info.value

        if paths:
            await file_chooser.set_files(paths)
            return f"Uploaded {len(paths)} file(s)"
        else:
            await file_chooser.set_files([])
            return "File chooser cancelled"


# Advanced Interaction Tools


@mcp.tool()
async def browser_drag(
    startElement: str,
    endElement: str,
    startRole: Optional[str] = None,
    startName: Optional[str] = None,
    startSelector: Optional[str] = None,
    endRole: Optional[str] = None,
    endName: Optional[str] = None,
    endSelector: Optional[str] = None,
    session_id: str = "default",
) -> Dict[str, Any]:
    """Perform drag and drop between two elements

    Args:
        startElement: Human-readable source element description
        endElement: Human-readable target element description
        startRole: ARIA role of source element
        startName: Accessible name of source element
        startSelector: CSS selector for source (fallback)
        endRole: ARIA role of target element
        endName: Accessible name of target element
        endSelector: CSS selector for target (fallback)
        session_id: Unique identifier for this client session
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return {"error": "No browser page available"}

    try:
        # Determine source locator
        if startRole and startName:
            source = page.get_by_role(startRole, name=startName)
            source_desc = f"{startElement} (role={startRole}, name={startName})"
        elif startSelector:
            source = page.locator(startSelector)
            source_desc = f"{startElement} (selector={startSelector})"
        else:
            return {
                "error": "Must provide either (startRole + startName) or startSelector"
            }

        # Determine target locator
        if endRole and endName:
            target = page.get_by_role(endRole, name=endName)
            target_desc = f"{endElement} (role={endRole}, name={endName})"
        elif endSelector:
            target = page.locator(endSelector)
            target_desc = f"{endElement} (selector={endSelector})"
        else:
            return {"error": "Must provide either (endRole + endName) or endSelector"}

        await source.drag_to(target)
        return await _get_snapshot_result(
            page, f"Dragged from {source_desc} to {target_desc}"
        )
    except Exception as e:
        return {
            "error": f"Failed to drag: {str(e)}",
            "startElement": startElement,
            "endElement": endElement,
        }


@mcp.tool()
async def browser_evaluate(
    function: str,
    session_id: str = "default",
    element: Optional[str] = None,
    ref: Optional[str] = None,
) -> str:
    """Evaluate JavaScript expression on page or element

    Args:
        function: JavaScript function as string (e.g., "() => document.title")
        session_id: Unique identifier for this client session
        element: Human-readable element description
        ref: Exact target element reference
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return "No browser page available"

    if element and ref:
        element_handle = await page.query_selector(ref)
        if element_handle:
            result = await element_handle.evaluate(function)
        else:
            return f"Element not found: {ref}"
    else:
        result = await page.evaluate(function)

    return json.dumps(result, indent=2)


@mcp.tool()
async def browser_wait_for(
    session_id: str = "default",
    time: Optional[float] = None,
    text: Optional[str] = None,
    textGone: Optional[str] = None,
) -> str:
    """Wait for text to appear/disappear or a specified time to pass

    Args:
        session_id: Unique identifier for this client session
        time: Time to wait in seconds
        text: Text to wait for to appear
        textGone: Text to wait for to disappear
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return "No browser page available"

    if time is not None:
        await page.wait_for_timeout(int(time * 1000))
        return f"Waited for {time} seconds"
    elif text:
        await page.wait_for_selector(f"text={text}")
        return f"Waited for text '{text}' to appear"
    elif textGone:
        await page.wait_for_selector(f"text={textGone}", state="hidden")
        return f"Waited for text '{textGone}' to disappear"
    else:
        return "No wait condition specified"


# Dialog and Monitoring Tools


@mcp.tool()
async def browser_handle_dialog(
    accept: bool, session_id: str = "default", promptText: Optional[str] = None
) -> str:
    """Handle a dialog

    Args:
        accept: Whether to accept the dialog
        session_id: Unique identifier for this client session
        promptText: Text to enter in prompt dialog
    """
    session = get_session(session_id)
    page = get_current_page(session)

    if not page:
        return "No browser page available"

    # Set up dialog handler for the next dialog
    async def handle_dialog(dialog):
        if accept:
            if promptText:
                await dialog.accept(promptText)
            else:
                await dialog.accept()
        else:
            await dialog.dismiss()

    page.once("dialog", handle_dialog)

    action = "accept" if accept else "dismiss"
    return f"Dialog handler set to {action}"


@mcp.tool()
async def browser_console_messages(
    session_id: str = "default", onlyErrors: bool = False
) -> str:
    """Returns all console messages

    Args:
        session_id: Unique identifier for this client session
        onlyErrors: Only return error messages
    """
    session = get_session(session_id)

    if onlyErrors:
        errors = [msg for msg in session.console_messages if msg["type"] == "error"]
        return json.dumps(errors, indent=2)

    return json.dumps(session.console_messages, indent=2)


@mcp.tool()
async def browser_network_requests(session_id: str = "default") -> str:
    """Returns all network requests since loading the page

    Args:
        session_id: Unique identifier for this client session
    """
    session = get_session(session_id)
    return json.dumps(session.network_requests, indent=2)


# Tab Management Tools


@mcp.tool()
async def browser_tabs(
    action: Literal["list", "create", "close", "select"],
    session_id: str = "default",
    index: Optional[int] = None,
) -> str:
    """List, create, close, or select a browser tab

    Args:
        action: Operation to perform (list, create, close, select)
        session_id: Unique identifier for this client session
        index: Tab index for close/select operations
    """
    session = get_session(session_id)

    if action == "list":
        tabs_info = []
        for i, page in enumerate(session.pages):
            title = await page.title()
            url = page.url
            is_current = i == session.current_page_index
            tabs_info.append(
                {"index": i, "title": title, "url": url, "current": is_current}
            )
        return json.dumps(tabs_info, indent=2)

    elif action == "create":
        # Ensure browser is open
        if session.browser is None:
            await browser_open(session_id=session_id)
            session = get_session(session_id)

        new_page = await session.context.new_page()

        # Set up listeners for new page
        _setup_page_listeners(new_page, session)

        session.pages.append(new_page)
        session.current_page_index = len(session.pages) - 1
        return f"Created new tab at index {session.current_page_index}"

    elif action == "close":
        if index is None:
            index = session.current_page_index

        if 0 <= index < len(session.pages):
            await session.pages[index].close()
            session.pages.pop(index)

            if session.current_page_index >= len(session.pages):
                session.current_page_index = max(0, len(session.pages) - 1)

            return f"Closed tab at index {index}"
        else:
            return f"Invalid tab index: {index}"

    elif action == "select":
        if index is None:
            return "Index required for select action"

        if 0 <= index < len(session.pages):
            session.current_page_index = index
            return f"Selected tab at index {index}"
        else:
            return f"Invalid tab index: {index}"

    else:
        return f"Unknown action: {action}"


if __name__ == "__main__":
    # Start the server with background cleanup task

    async def main():
        # Start cleanup task
        cleanup_task = asyncio.create_task(session_cleanup_task())

        try:
            # Run the MCP server
            await mcp.run()
        finally:
            cleanup_task.cancel()
            # Cleanup all sessions on shutdown
            for session_id in list(sessions.keys()):
                await cleanup_session(session_id)

    asyncio.run(main())
