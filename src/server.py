import json
from typing import Any, Literal, Optional
from urllib.parse import quote_plus

from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

mcp = FastMCP("Playwright MCP Server")

# Global state for browser management
headless = False
browser: Optional[Browser] = None
context: Optional[BrowserContext] = None
pages: list[Page] = []
current_page_index: int = 0
playwright_instance = None
console_messages: list[dict[str, Any]] = []
network_requests: list[dict[str, Any]] = []


def _setup_page_listeners(page: Page) -> None:
    """Set up console and network listeners for a page"""
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


async def _initialize_browser(
    headless: bool = True, width: int = 1920, height: int = 1080
) -> Page:
    """Initialize browser with consistent settings"""
    global browser, context, pages, current_page_index, playwright_instance, console_messages, network_requests

    playwright_instance = await async_playwright().start()
    browser = await playwright_instance.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--disable-info-bars"],
    )

    # Handle browser close event
    def handle_browser_close():
        global browser, context, pages, playwright_instance, console_messages, network_requests, current_page_index
        browser = None
        context = None
        pages = []
        playwright_instance = None
        console_messages = []
        network_requests = []
        current_page_index = 0

    browser.on("disconnected", handle_browser_close)

    context = await browser.new_context(
        viewport={"width": width, "height": height},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    page = await context.new_page()
    pages = [page]
    current_page_index = 0
    console_messages = []
    network_requests = []

    # Set up listeners
    _setup_page_listeners(page)

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


async def ensure_browser(headless: bool = True) -> Page:
    """Ensure browser is initialized"""
    global browser

    if browser is None:
        await _initialize_browser(headless=headless)

    return pages[current_page_index]


def get_current_page() -> Optional[Page]:
    """Get the current active page"""
    if pages and 0 <= current_page_index < len(pages):
        return pages[current_page_index]
    return None


async def _get_snapshot_result(
    page: Optional[Page], action_message: str
) -> dict[str, Any]:
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
async def browser_open(width: int = 1920, height: int = 1080) -> str:
    """Open a new browser instance

    Args:
        width: Initial browser width
        height: Initial browser height
    """
    global browser, headless

    if browser is not None:
        return "Browser is already open. Close it first with browser_close before opening a new one."

    await _initialize_browser(headless=headless, width=width, height=height)

    mode = "headless" if headless else "headed"
    return f"Browser opened in {mode} mode with viewport {width}x{height}"


# Core Navigation Tools


@mcp.tool()
async def browser_navigate(url: str) -> dict[str, Any]:
    """Navigate to a URL

    Args:
        url: The URL to navigate to
    """
    global headless
    page = await ensure_browser(headless=headless)
    await page.goto(url)
    return await _get_snapshot_result(page, f"Navigated to {url}")


@mcp.tool()
async def browser_navigate_back() -> dict[str, Any]:
    """Go back to the previous page"""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    await page.go_back()
    return await _get_snapshot_result(page, "Navigated back")


@mcp.tool()
async def browser_search(query: str) -> dict[str, Any]:
    """Search for a topic using Google search

    Args:
        query: The search query or topic to search for
    """
    global headless
    page = await ensure_browser(headless=headless)
    encoded_query = quote_plus(query)
    search_url = f"https://www.google.com/search?q={encoded_query}"
    await page.goto(search_url)
    return await _get_snapshot_result(
        page, f"Searched for '{query}' on Google: {search_url}"
    )


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
async def browser_snapshot() -> dict[str, Any]:
    """Capture accessibility snapshot of the current page"""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    # Get accessibility tree snapshot
    snapshot = await page.locator("body").aria_snapshot()

    # Get page metadata
    page_url = page.url
    page_title = await page.title()

    # Combine all information
    result = {"url": page_url, "title": page_title, "snapshot": snapshot}

    return result


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


@mcp.tool()
async def browser_get_html(
    selector: Optional[str] = None,
    maxLength: int = 50000,
    filter_tags: Optional[list[str]] = None,
) -> str:
    """Get HTML content for debugging when locators fail

    Args:
        selector: CSS selector to get HTML from (defaults to body)
        maxLength: Maximum characters to return (default 50000)
        filter_tags: List of tag names to remove (e.g., ['script', 'style']). Defaults to ['script']
    """
    page = get_current_page()
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


# Interaction Tools


@mcp.tool()
async def browser_click(
    element: str,
    role: Optional[str] = None,
    name: Optional[str] = None,
    selector: Optional[str] = None,
    nth: Optional[int] = None,
    doubleClick: bool = False,
    button: str = "left",
    modifiers: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Perform click on a web page

    Args:
        element: Human-readable element description
        role: ARIA role of the element (e.g., 'button', 'link', 'textbox')
        name: Accessible name of the element (from snapshot)
        selector: CSS selector (fallback if role/name not available)
        nth: Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)
        doubleClick: Whether to perform a double click
        button: Button to click (left, right, middle)
        modifiers: Modifier keys to press (Alt, Control, Meta, Shift)
    """
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    click_options = {"button": button}
    if modifiers:
        click_options["modifiers"] = modifiers

    try:
        # Prefer role-based locators (more reliable)
        if role and name:
            locator = page.get_by_role(role, name=name)
            if nth is not None:
                locator = locator.nth(nth)
            nth_msg = f", nth={nth}" if nth is not None else ""
            if doubleClick:
                await locator.dblclick(**click_options)
                message = (
                    f"Double-clicked on {element} (role={role}, name={name}{nth_msg})"
                )
            else:
                await locator.click(**click_options)
                message = f"Clicked on {element} (role={role}, name={name}{nth_msg})"
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
    nth: Optional[int] = None,
) -> dict[str, Any]:
    """Hover over element on page

    Args:
        element: Human-readable element description
        role: ARIA role of the element (e.g., 'button', 'link', 'textbox')
        name: Accessible name of the element (from snapshot)
        selector: CSS selector (fallback if role/name not available)
        nth: Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)
    """
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    try:
        # Prefer role-based locators
        if role and name:
            locator = page.get_by_role(role, name=name)
            if nth is not None:
                locator = locator.nth(nth)
            await locator.hover()
            nth_msg = f", nth={nth}" if nth is not None else ""
            message = f"Hovered over {element} (role={role}, name={name}{nth_msg})"
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
    nth: Optional[int] = None,
    submit: bool = False,
    slowly: bool = False,
) -> dict[str, Any]:
    """Type text into editable element

    Args:
        element: Human-readable element description
        text: Text to type into the element
        role: ARIA role of the element (e.g., 'textbox', 'searchbox', 'combobox')
        name: Accessible name of the element (from snapshot)
        selector: CSS selector (fallback if role/name not available)
        nth: Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)
        submit: Whether to submit (press Enter after)
        slowly: Whether to type one character at a time
    """
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    try:
        # Prefer role-based locators
        if role and name:
            locator = page.get_by_role(role, name=name)
            if nth is not None:
                locator = locator.nth(nth)
            if slowly:
                await locator.type(text)
            else:
                await locator.fill(text)

            nth_msg = f", nth={nth}" if nth is not None else ""
            if submit:
                await locator.press("Enter")
                message = f"Typed '{text}' into {element} and submitted (role={role}, name={name}{nth_msg})"
            else:
                message = (
                    f"Typed '{text}' into {element} (role={role}, name={name}{nth_msg})"
                )
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
async def browser_press_key(key: str) -> dict[str, Any]:
    """Press a key on the keyboard

    Args:
        key: Name of the key to press (e.g., ArrowLeft, a, Enter)
    """
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    await page.keyboard.press(key)
    return await _get_snapshot_result(page, f"Pressed key: {key}")


# Form and Selection Tools


@mcp.tool()
async def browser_fill_form(fields: list[dict[str, str]]) -> dict[str, Any]:
    """Fill multiple form fields

    Args:
        fields: List of fields to fill, each with 'element', 'value', and either ('role' + 'name') or 'selector'
    """
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    filled_fields = []
    errors = []

    for field in fields:
        role = field.get("role")
        name = field.get("name")
        selector = field.get("selector")
        value = field.get("value")
        element_desc = field.get("element", name or selector)

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
    values: list[str],
    role: Optional[str] = None,
    name: Optional[str] = None,
    selector: Optional[str] = None,
    nth: Optional[int] = None,
) -> dict[str, Any]:
    """Select an option in a dropdown

    Args:
        element: Human-readable element description
        values: Array of values to select
        role: ARIA role of the element (typically 'combobox' or 'listbox')
        name: Accessible name of the element (from snapshot)
        selector: CSS selector (fallback if role/name not available)
        nth: Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)
    """
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    try:
        if role and name:
            locator = page.get_by_role(role, name=name)
            if nth is not None:
                locator = locator.nth(nth)
            await locator.select_option(values)
            nth_msg = f", nth={nth}" if nth is not None else ""
            message = (
                f"Selected {values} in {element} (role={role}, name={name}{nth_msg})"
            )
        elif selector:
            await page.select_option(selector, values)
            message = f"Selected {values} in {element} (selector={selector})"
        else:
            return {"error": "Must provide either (role + name) or selector"}

        return await _get_snapshot_result(page, message)
    except Exception as e:
        return {"error": f"Failed to select option: {str(e)}", "element": element}


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
    startElement: str,
    endElement: str,
    startRole: Optional[str] = None,
    startName: Optional[str] = None,
    startSelector: Optional[str] = None,
    startNth: Optional[int] = None,
    endRole: Optional[str] = None,
    endName: Optional[str] = None,
    endSelector: Optional[str] = None,
    endNth: Optional[int] = None,
) -> dict[str, Any]:
    """Perform drag and drop between two elements

    Args:
        startElement: Human-readable source element description
        endElement: Human-readable target element description
        startRole: ARIA role of source element
        startName: Accessible name of source element
        startSelector: CSS selector for source (fallback)
        startNth: Zero-based index for source element when multiple match
        endRole: ARIA role of target element
        endName: Accessible name of target element
        endSelector: CSS selector for target (fallback)
        endNth: Zero-based index for target element when multiple match
    """
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    try:
        # Determine source locator
        if startRole and startName:
            source = page.get_by_role(startRole, name=startName)
            if startNth is not None:
                source = source.nth(startNth)
            nth_msg = f", nth={startNth}" if startNth is not None else ""
            source_desc = (
                f"{startElement} (role={startRole}, name={startName}{nth_msg})"
            )
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
            if endNth is not None:
                target = target.nth(endNth)
            nth_msg = f", nth={endNth}" if endNth is not None else ""
            target_desc = f"{endElement} (role={endRole}, name={endName}{nth_msg})"
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
    element: Optional[str] = None,
    selector: Optional[str] = None,
) -> str:
    """Evaluate JavaScript expression on page or element

    Args:
        function: JavaScript function as string (e.g., "() => document.title")
        element: Human-readable element description
        selector: CSS selector for target element (if evaluating on specific element)
    """
    page = get_current_page()
    if not page:
        return "No browser page available"

    try:
        if element and selector:
            element_handle = await page.query_selector(selector)
            if element_handle:
                result = await element_handle.evaluate(function)
            else:
                return json.dumps({"error": f"Element not found: {selector}"}, indent=2)
        else:
            result = await page.evaluate(function)

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to evaluate: {str(e)}"}, indent=2)


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
    global pages, current_page_index, context, headless

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
        await ensure_browser(headless=headless)
        new_page = await context.new_page()

        # Set up listeners for new page
        _setup_page_listeners(new_page)

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
