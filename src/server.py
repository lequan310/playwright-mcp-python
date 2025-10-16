import json
from datetime import datetime
from typing import Any, Literal, Optional
from urllib.parse import quote_plus

from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

mcp = FastMCP("Playwright MCP Server")

# Global state for browser management
headless = True
browser: Optional[Browser] = None
context: Optional[BrowserContext] = None
pages: list[Page] = []
current_page_index: int = 0
playwright_instance = None
console_messages: list[dict[str, Any]] = []
network_requests: list[dict[str, Any]] = []


async def ensure_browser(headless: bool = True) -> list[Page]:
    """Ensure browser is initialized"""
    global browser, context, pages, current_page_index, playwright_instance

    if browser is None:
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        pages = [page]
        current_page_index = 0

        # Set up console message listener
        page.on(
            "console",
            lambda msg: console_messages.append(
                {"type": msg.type, "text": msg.text, "location": msg.location}
            ),
        )

        # Set up network request listener
        page.on(
            "request",
            lambda request: network_requests.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "headers": request.headers,
                    "resourceType": request.resource_type,
                }
            ),
        )

    return pages[current_page_index]


def get_current_page() -> Optional[Page]:
    """Get the current active page"""
    if pages and 0 <= current_page_index < len(pages):
        return pages[current_page_index]
    return None


# Browser Lifecycle Tools


@mcp.tool()
async def browser_open(width: int = 1920, height: int = 1080) -> str:
    """Open a new browser instance

    Args:
        headless: Whether to run browser in headless mode
        width: Initial browser width
        height: Initial browser height
    """
    global browser, context, pages, current_page_index, playwright_instance, console_messages, network_requests, headless

    if browser is not None:
        return "Browser is already open. Close it first with browser_close before opening a new one."

    playwright_instance = await async_playwright().start()
    browser = await playwright_instance.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--disable-info-bars"],
    )
    context = await browser.new_context(
        viewport={"width": width, "height": height},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        locale="en-US",
        timezone_id="America/New_York",
    )
    page = await context.new_page()
    pages = [page]
    current_page_index = 0
    console_messages = []
    network_requests = []

    # Set up console message listener
    page.on(
        "console",
        lambda msg: console_messages.append(
            {"type": msg.type, "text": msg.text, "location": msg.location}
        ),
    )

    # Set up network request listener
    page.on(
        "request",
        lambda request: network_requests.append(
            {
                "url": request.url,
                "method": request.method,
                "headers": request.headers,
                "resourceType": request.resource_type,
            }
        ),
    )

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

    mode = "headless" if headless else "headed"
    return f"Browser opened in {mode} mode with viewport {width}x{height}"


# Core Navigation Tools


@mcp.tool()
async def browser_navigate(url: str) -> str:
    """Navigate to a URL

    Args:
        url: The URL to navigate to
    """
    page = await ensure_browser()
    await page.goto(url)
    return f"Navigated to {url}"


@mcp.tool()
async def browser_navigate_back() -> str:
    """Go back to the previous page"""
    page = get_current_page()
    if not page:
        return "No browser page available"

    await page.go_back()
    return "Navigated back"


# @mcp.tool()
# async def browser_search(query: str) -> str:
#     """Search for a topic using Google search

#     Args:
#         query: The search query or topic to search for
#     """
#     page = await ensure_browser()
#     encoded_query = quote_plus(query)
#     search_url = f"https://www.google.com/search?q={encoded_query}"
#     await page.goto(search_url)
#     return f"Searched for '{query}' on Google: {search_url}"


@mcp.tool()
async def browser_close() -> str:
    """Close the browser and clean up all resources"""
    global browser, context, pages, playwright_instance, console_messages, network_requests, current_page_index

    if browser:
        await context.close()
        await browser.close()
        if playwright_instance:
            await playwright_instance.stop()

        browser = None
        context = None
        pages = []
        playwright_instance = None
        console_messages = []
        network_requests = []
        current_page_index = 0

        return "Browser closed and all resources cleaned up"
    return "Browser was not open"


@mcp.tool()
async def browser_resize(width: int, height: int) -> str:
    """Resize the browser window

    Args:
        width: Width of the browser window
        height: Height of the browser window
    """
    page = get_current_page()
    if not page:
        return "No browser page available"

    await page.set_viewport_size({"width": width, "height": height})
    return f"Browser resized to {width}x{height}"


# Snapshot and Screenshot Tools


@mcp.tool()
async def browser_snapshot() -> str:
    """Capture accessibility snapshot of the current page"""
    page = get_current_page()
    if not page:
        return "No browser page available"

    # Get accessibility tree snapshot
    snapshot = await page.accessibility.snapshot()
    return json.dumps(snapshot, indent=2)


@mcp.tool()
async def browser_take_screenshot(
    type: str = "png",
    element: Optional[str] = None,
    ref: Optional[str] = None,
    fullPage: bool = False,
) -> Image:
    """Take a screenshot of the current page

    Args:
        type: Image format (png or jpeg)
        element: Human-readable element description
        ref: Exact target element reference from the page snapshot
        fullPage: Take screenshot of full scrollable page
    """
    page = get_current_page()
    if not page:
        raise ValueError("No browser page available")

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


# Interaction Tools


@mcp.tool()
async def browser_click(
    element: str,
    ref: str,
    doubleClick: bool = False,
    button: str = "left",
    modifiers: Optional[list[str]] = None,
) -> str:
    """Perform click on a web page

    Args:
        element: Human-readable element description
        ref: Exact target element reference from the page snapshot
        doubleClick: Whether to perform a double click
        button: Button to click (left, right, middle)
        modifiers: Modifier keys to press (Alt, Control, Meta, Shift)
    """
    page = get_current_page()
    if not page:
        return "No browser page available"

    click_options = {"button": button}
    if modifiers:
        click_options["modifiers"] = modifiers

    if doubleClick:
        await page.dblclick(ref, **click_options)
        return f"Double-clicked on {element}"
    else:
        await page.click(ref, **click_options)
        return f"Clicked on {element}"


@mcp.tool()
async def browser_hover(element: str, ref: str) -> str:
    """Hover over element on page

    Args:
        element: Human-readable element description
        ref: Exact target element reference from the page snapshot
    """
    page = get_current_page()
    if not page:
        return "No browser page available"

    await page.hover(ref)
    return f"Hovered over {element}"


@mcp.tool()
async def browser_type(
    element: str, ref: str, text: str, submit: bool = False, slowly: bool = False
) -> str:
    """Type text into editable element

    Args:
        element: Human-readable element description
        ref: Exact target element reference from the page snapshot
        text: Text to type into the element
        submit: Whether to submit (press Enter after)
        slowly: Whether to type one character at a time
    """
    page = get_current_page()
    if not page:
        return "No browser page available"

    if slowly:
        await page.type(ref, text)
    else:
        await page.fill(ref, text)

    if submit:
        await page.press(ref, "Enter")
        return f"Typed '{text}' into {element} and submitted"

    return f"Typed '{text}' into {element}"


@mcp.tool()
async def browser_press_key(key: str) -> str:
    """Press a key on the keyboard

    Args:
        key: Name of the key to press (e.g., ArrowLeft, a, Enter)
    """
    page = get_current_page()
    if not page:
        return "No browser page available"

    await page.keyboard.press(key)
    return f"Pressed key: {key}"


# Form and Selection Tools


@mcp.tool()
async def browser_fill_form(fields: list[dict[str, str]]) -> str:
    """Fill multiple form fields

    Args:
        fields: List of fields to fill, each with 'ref', 'element', and 'value'
    """
    page = get_current_page()
    if not page:
        return "No browser page available"

    filled_fields = []
    for field in fields:
        ref = field.get("ref")
        value = field.get("value")
        element_desc = field.get("element", ref)

        if ref and value:
            await page.fill(ref, value)
            filled_fields.append(element_desc)

    return f"Filled {len(filled_fields)} fields: {', '.join(filled_fields)}"


@mcp.tool()
async def browser_select_option(element: str, ref: str, values: list[str]) -> str:
    """Select an option in a dropdown

    Args:
        element: Human-readable element description
        ref: Exact target element reference from the page snapshot
        values: Array of values to select
    """
    page = get_current_page()
    if not page:
        return "No browser page available"

    await page.select_option(ref, values)
    return f"Selected {values} in {element}"


@mcp.tool()
async def browser_file_upload(paths: Optional[list[str]] = None) -> str:
    """Upload one or multiple files

    Args:
        paths: Absolute paths to files to upload. If omitted, file chooser is cancelled.
    """
    page = get_current_page()
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
    startElement: str, startRef: str, endElement: str, endRef: str
) -> str:
    """Perform drag and drop between two elements

    Args:
        startElement: Human-readable source element description
        startRef: Exact source element reference
        endElement: Human-readable target element description
        endRef: Exact target element reference
    """
    page = get_current_page()
    if not page:
        return "No browser page available"

    await page.drag_and_drop(startRef, endRef)
    return f"Dragged from {startElement} to {endElement}"


@mcp.tool()
async def browser_evaluate(
    function: str, element: Optional[str] = None, ref: Optional[str] = None
) -> str:
    """Evaluate JavaScript expression on page or element

    Args:
        function: JavaScript function as string (e.g., "() => document.title")
        element: Human-readable element description
        ref: Exact target element reference
    """
    page = get_current_page()
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
    time: Optional[float] = None,
    text: Optional[str] = None,
    textGone: Optional[str] = None,
) -> str:
    """Wait for text to appear/disappear or a specified time to pass

    Args:
        time: Time to wait in seconds
        text: Text to wait for to appear
        textGone: Text to wait for to disappear
    """
    page = get_current_page()
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


# @mcp.tool()
# async def browser_handle_dialog(accept: bool, promptText: Optional[str] = None) -> str:
#     """Handle a dialog

#     Args:
#         accept: Whether to accept the dialog
#         promptText: Text to enter in prompt dialog
#     """
#     page = get_current_page()
#     if not page:
#         return "No browser page available"

#     # Set up dialog handler for the next dialog
#     async def handle_dialog(dialog):
#         if accept:
#             if promptText:
#                 await dialog.accept(promptText)
#             else:
#                 await dialog.accept()
#         else:
#             await dialog.dismiss()

#     page.once("dialog", handle_dialog)

#     action = "accept" if accept else "dismiss"
#     return f"Dialog handler set to {action}"


# @mcp.tool()
# async def browser_console_messages(onlyErrors: bool = False) -> str:
#     """Returns all console messages

#     Args:
#         onlyErrors: Only return error messages
#     """
#     global console_messages

#     if onlyErrors:
#         errors = [msg for msg in console_messages if msg["type"] == "error"]
#         return json.dumps(errors, indent=2)

#     return json.dumps(console_messages, indent=2)


# @mcp.tool()
# async def browser_network_requests() -> str:
#     """Returns all network requests since loading the page"""
#     global network_requests
#     return json.dumps(network_requests, indent=2)


# Tab Management Tools


@mcp.tool()
async def browser_tabs(
    action: Literal["list", "create", "close", "select"], index: Optional[int] = None
) -> str:
    """List, create, close, or select a browser tab

    Args:
        action: Operation to perform (list, create, close, select)
        index: Tab index for close/select operations
    """
    global pages, current_page_index, context

    if action == "list":
        tabs_info = []
        for i, page in enumerate(pages):
            title = await page.title()
            url = page.url
            is_current = i == current_page_index
            tabs_info.append(
                {"index": i, "title": title, "url": url, "current": is_current}
            )
        return json.dumps(tabs_info, indent=2)

    elif action == "create":
        await ensure_browser()
        new_page = await context.new_page()

        # Set up listeners for new page
        new_page.on(
            "console",
            lambda msg: console_messages.append(
                {"type": msg.type, "text": msg.text, "location": msg.location}
            ),
        )
        new_page.on(
            "request",
            lambda request: network_requests.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "headers": request.headers,
                    "resourceType": request.resource_type,
                }
            ),
        )

        pages.append(new_page)
        current_page_index = len(pages) - 1
        return f"Created new tab at index {current_page_index}"

    elif action == "close":
        if index is None:
            index = current_page_index

        if 0 <= index < len(pages):
            await pages[index].close()
            pages.pop(index)

            if current_page_index >= len(pages):
                current_page_index = max(0, len(pages) - 1)

            return f"Closed tab at index {index}"
        else:
            return f"Invalid tab index: {index}"

    elif action == "select":
        if index is None:
            return "Index required for select action"

        if 0 <= index < len(pages):
            current_page_index = index
            return f"Selected tab at index {index}"
        else:
            return f"Invalid tab index: {index}"

    else:
        return f"Unknown action: {action}"
