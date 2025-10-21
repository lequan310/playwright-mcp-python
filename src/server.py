import json
from typing import Annotated, Any, Literal, Optional
from urllib.parse import quote_plus

from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from patchright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from schemas.element import AriaNode, ElementLocator, FormField, Selector

mcp = FastMCP("Playwright MCP Server")

# Global state for browser management
headless = False
browser: Optional[Browser] = None
context: Optional[BrowserContext] = None
pages: list[Page] = []
current_page_index: int = 0
playwright_instance: Optional[Playwright] = None
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

    # Set up page close listener
    page.on("close", _on_page_close)


async def _on_page_close(page: Page) -> None:
    """Handle page close event to update global state"""
    global pages, current_page_index

    if page in pages:
        index = pages.index(page)
        pages.pop(index)

        if current_page_index >= len(pages):
            current_page_index = max(0, len(pages) - 1)

    if len(pages) == 0:
        await close_browser()


async def close_browser() -> bool:
    global browser, context, pages, playwright_instance, console_messages, network_requests, current_page_index

    if browser and browser.is_connected():
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

        return True
    return False


async def _initialize_browser(headless: bool = True) -> Page:
    """Initialize browser with consistent settings"""
    global browser, context, pages, current_page_index, playwright_instance, console_messages, network_requests

    playwright_instance = await async_playwright().start()
    browser = await playwright_instance.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-info-bars",
            "--start-maximized",
        ],
        channel="chrome",
    )

    context = await browser.new_context(no_viewport=True)
    context.on("page", lambda page: _setup_page_listeners(page))
    context.on("page", lambda page: pages.append(page))
    page = await context.new_page()
    current_page_index = 0
    console_messages = []
    network_requests = []

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


def _get_locator(page: Page, locator: ElementLocator, nth: Optional[int] = None):
    """Create a Playwright locator from ElementLocator union type

    Args:
        page: The page to create the locator on
        locator: ElementLocator (AriaNode or Selector)
        nth: Optional zero-based index when multiple elements match

    Returns:
        tuple: (playwright_locator, description_string)
    """
    if isinstance(locator, AriaNode):
        playwright_locator = page.get_by_role(locator.role, name=locator.name)
        if nth is not None:
            playwright_locator = playwright_locator.nth(nth)
        nth_msg = f", nth={nth}" if nth is not None else ""
        desc = f"role={locator.role}, name={locator.name}{nth_msg}"
    elif isinstance(locator, Selector):
        playwright_locator = page.locator(locator.selector)
        if nth is not None:
            playwright_locator = playwright_locator.nth(nth)
        nth_msg = f", nth={nth}" if nth is not None else ""
        desc = f"selector={locator.selector}{nth_msg}"
    else:
        raise ValueError(f"Invalid locator type: {type(locator)}")

    return playwright_locator, desc


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
        await page.wait_for_load_state("load")
        await page.wait_for_timeout(1000)  # Wait a bit for dynamic content
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
async def browser_open() -> str:
    """Open a new browser instance"""
    global browser, headless

    if browser is not None:
        return "Browser is already open. Close it first with browser_close before opening a new one."

    await _initialize_browser(headless=headless)

    mode = "headless" if headless else "headed"
    return f"Browser opened in {mode} mode"


# Core Navigation Tools


@mcp.tool(tags={"navigation"})
async def browser_navigate(
    url: Annotated[str, "The URL to navigate to"],
) -> dict[str, Any]:
    """Navigate to a URL"""
    global headless
    page = await ensure_browser(headless=headless)
    await page.goto(url, wait_until="load")
    return await _get_snapshot_result(page, f"Navigated to {url}")


@mcp.tool(tags={"navigation"})
async def browser_navigate_back() -> dict[str, Any]:
    """Go back to the previous page"""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    await page.go_back()
    return await _get_snapshot_result(page, "Navigated back")


@mcp.tool(tags={"navigation"})
async def browser_search(
    query: Annotated[str, "The search query or topic to search for"],
) -> dict[str, Any]:
    """Search for a topic using Google search"""
    global headless
    page = await ensure_browser(headless=headless)
    encoded_query = quote_plus(query)
    search_url = f"https://www.google.com/search?q={encoded_query}"
    await page.goto(search_url, wait_until="load")
    return await _get_snapshot_result(
        page, f"Searched for '{query}' on Google: {search_url}"
    )


@mcp.tool(tags={"navigation"})
async def browser_close() -> str:
    """Close the browser and clean up all resources"""
    result = await close_browser()
    if result:
        return "Browser closed and all resources cleaned up"
    return "Browser was not open"


@mcp.tool(tags={"navigation"})
async def browser_resize(
    width: Annotated[int, "Width of the browser window"],
    height: Annotated[int, "Height of the browser window"],
) -> str:
    """Resize the browser window"""
    page = get_current_page()
    if not page:
        return "No browser page available"

    await page.set_viewport_size({"width": width, "height": height})
    return f"Browser resized to {width}x{height}"


# Snapshot and Screenshot Tools


@mcp.tool(tags={"screenshot", "snapshot"})
async def browser_snapshot() -> dict[str, Any]:
    """Capture accessibility snapshot of the current page. Use this tool in case the you think the web did not fully load previously."""
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


@mcp.tool(tags={"screenshot", "snapshot"})
async def browser_take_screenshot(
    type: Annotated[str, "Image format (png or jpeg)"] = "png",
    element: Annotated[Optional[str], "Human-readable element description"] = None,
    locator: Annotated[
        Optional[ElementLocator],
        "Element locator (AriaNode with ARIA role/name or Selector with CSS/XPath selector). Leave empty to screenshot full page or viewport",
    ] = None,
    nth: Annotated[
        Optional[int],
        "Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)",
    ] = None,
    full_page: Annotated[bool, "Take screenshot of full scrollable page"] = False,
) -> Image:
    """Take a screenshot of the current page"""
    page = get_current_page()
    if not page:
        raise ValueError("No browser page available")

    screenshot_options = {"type": type}

    if element and locator:
        # Screenshot specific element
        playwright_locator, desc = _get_locator(page, locator, nth)
        screenshot_bytes = await playwright_locator.screenshot(**screenshot_options)
    else:
        # Screenshot full page or viewport
        screenshot_options["full_page"] = full_page
        screenshot_bytes = await page.screenshot(**screenshot_options)

    return Image(data=screenshot_bytes, format=type)


@mcp.tool(tags={"screenshot", "snapshot"})
async def browser_get_html(
    selector: Annotated[
        Optional[str], "CSS selector to get HTML from (defaults to body)"
    ] = None,
    max_length: Annotated[int, "Maximum characters to return"] = 50000,
    filter_tags: Annotated[
        Optional[list[str]],
        "List of tag names to remove (e.g., ['script', 'style']). Defaults to ['script']",
    ] = None,
) -> str:
    """Get HTML content for debugging when locators fail"""
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
        if len(html) > max_length:
            html = (
                html[:max_length]
                + f"\n\n... [truncated {len(html) - max_length} characters]"
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


@mcp.tool(tags={"screenshot", "snapshot"})
async def browser_get_text_content() -> str:
    """Get all text content from the current page. Useful for extracting clean article text."""
    from trafilatura import extract

    page = get_current_page()
    if not page:
        return json.dumps({"error": "No browser page available"}, indent=2)

    try:
        content = await page.content()
        text = extract(
            content, output_format="markdown", include_links=True, include_tables=True
        )
        return text
    except Exception as e:
        return json.dumps({"error": f"Failed to get text content: {str(e)}"}, indent=2)


# Interaction Tools


@mcp.tool(tags={"interaction"})
async def browser_click(
    element: Annotated[str, "Human-readable element description"],
    locator: Annotated[
        ElementLocator,
        "Element locator (AriaNode with ARIA role & name or Selector with CSS/XPath selector)",
    ],
    nth: Annotated[
        Optional[int],
        "Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)",
    ] = None,
    double_click: Annotated[bool, "Whether to perform a double click"] = False,
    button: Annotated[str, "Button to click (left, right, middle)"] = "left",
    modifiers: Annotated[
        Optional[list[str]], "Modifier keys to press (Alt, Control, Meta, Shift)"
    ] = None,
) -> dict[str, Any]:
    """Perform click on a web page"""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    click_options = {"button": button}
    if modifiers:
        click_options["modifiers"] = modifiers

    try:
        playwright_locator, desc = _get_locator(page, locator, nth)

        if double_click:
            await playwright_locator.dblclick(**click_options)
            message = f"Double-clicked on {element} ({desc})"
        else:
            await playwright_locator.click(**click_options)
            message = f"Clicked on {element} ({desc})"

        return await _get_snapshot_result(page, message)
    except Exception as e:
        return {"error": f"Failed to click: {str(e)}", "element": element}


@mcp.tool(tags={"interaction"})
async def browser_hover(
    element: Annotated[str, "Human-readable element description"],
    locator: Annotated[
        ElementLocator,
        "Element locator (AriaNode with ARIA role/name or Selector with CSS/XPath selector)",
    ],
    nth: Annotated[
        Optional[int],
        "Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)",
    ] = None,
) -> dict[str, Any]:
    """Hover over element on page"""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    try:
        playwright_locator, desc = _get_locator(page, locator, nth)
        await playwright_locator.hover()
        message = f"Hovered over {element} ({desc})"

        return await _get_snapshot_result(page, message)
    except Exception as e:
        return {"error": f"Failed to hover: {str(e)}", "element": element}


@mcp.tool(tags={"interaction"})
async def browser_type(
    element: Annotated[str, "Human-readable element description"],
    text: Annotated[str, "Text to type into the element"],
    locator: Annotated[
        ElementLocator,
        "Element locator (AriaNode with ARIA role/name or Selector with CSS/XPath selector)",
    ],
    nth: Annotated[
        Optional[int],
        "Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)",
    ] = None,
    submit: Annotated[bool, "Whether to submit (press Enter after)"] = False,
    slowly: Annotated[bool, "Whether to type one character at a time"] = False,
) -> dict[str, Any]:
    """Type text into editable element"""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    try:
        playwright_locator, desc = _get_locator(page, locator, nth)

        if slowly:
            await playwright_locator.type(text)
        else:
            await playwright_locator.fill(text)

        if submit:
            await playwright_locator.press("Enter")
            message = f"Typed '{text}' into {element} and submitted ({desc})"
        else:
            message = f"Typed '{text}' into {element} ({desc})"

        return await _get_snapshot_result(page, message)
    except Exception as e:
        return {"error": f"Failed to type: {str(e)}", "element": element}


@mcp.tool(tags={"interaction"})
async def browser_press_key(
    key: Annotated[str, "Name of the key to press (e.g., ArrowLeft, a, Enter)"],
) -> dict[str, Any]:
    """Press a key on the keyboard"""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    await page.keyboard.press(key)
    return await _get_snapshot_result(page, f"Pressed key: {key}")


# Form and Selection Tools


@mcp.tool(tags={"interaction"})
async def browser_fill_form(
    fields: Annotated[
        list[FormField],
        "List of FormField objects, each with element description, value, locator, and optional nth index",
    ],
) -> dict[str, Any]:
    """Fill multiple form fields"""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    filled_fields = []
    errors = []

    for field in fields:
        try:
            playwright_locator, desc = _get_locator(page, field.locator, field.nth)
            await playwright_locator.fill(field.value)
            filled_fields.append(f"{field.element} ({desc})")
        except Exception as e:
            errors.append(f"{field.element}: {str(e)}")

    message = f"Filled {len(filled_fields)} fields: {', '.join(filled_fields)}"
    if errors:
        message += f"\nErrors: {'; '.join(errors)}"

    return await _get_snapshot_result(page, message)


@mcp.tool(tags={"interaction"})
async def browser_select_option(
    element: Annotated[str, "Human-readable element description"],
    values: Annotated[list[str], "Array of values to select"],
    locator: Annotated[
        ElementLocator,
        "Element locator (AriaNode with ARIA role/name or Selector with CSS/XPath selector)",
    ],
    nth: Annotated[
        Optional[int],
        "Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)",
    ] = None,
) -> dict[str, Any]:
    """Select an option in a dropdown"""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    try:
        playwright_locator, desc = _get_locator(page, locator, nth)
        await playwright_locator.select_option(values)
        message = f"Selected {values} in {element} ({desc})"

        return await _get_snapshot_result(page, message)
    except Exception as e:
        return {"error": f"Failed to select option: {str(e)}", "element": element}


@mcp.tool(tags={"interaction"})
async def browser_file_upload(
    paths: Annotated[
        Optional[list[str]],
        "Absolute paths to files to upload. If omitted, file chooser is cancelled.",
    ] = None,
) -> str:
    """Upload one or multiple files"""
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


@mcp.tool(tags={"interaction"})
async def browser_drag(
    start_element: Annotated[str, "Human-readable source element description"],
    end_element: Annotated[str, "Human-readable target element description"],
    start_locator: Annotated[
        ElementLocator,
        "Source element locator (AriaNode with ARIA role/name or Selector with CSS/XPath selector)",
    ],
    end_locator: Annotated[
        ElementLocator,
        "Target element locator (AriaNode with ARIA role/name or Selector with CSS/XPath selector)",
    ],
    start_nth: Annotated[
        Optional[int], "Zero-based index for source element when multiple match"
    ] = None,
    end_nth: Annotated[
        Optional[int], "Zero-based index for target element when multiple match"
    ] = None,
) -> dict[str, Any]:
    """Perform drag and drop between two elements"""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    try:
        source, source_desc = _get_locator(page, start_locator, start_nth)
        target, target_desc = _get_locator(page, end_locator, end_nth)

        await source.drag_to(target)
        return await _get_snapshot_result(
            page,
            f"Dragged from {start_element} ({source_desc}) to {end_element} ({target_desc})",
        )
    except Exception as e:
        return {
            "error": f"Failed to drag: {str(e)}",
            "start_element": start_element,
            "end_element": end_element,
        }


# @mcp.tool()
# async def browser_evaluate(
#     function: str,
#     element: Optional[str] = None,
#     selector: Optional[str] = None,
# ) -> str:
#     """Evaluate JavaScript expression on page or element

#     Args:
#         function: JavaScript function as string (e.g., "() => document.title")
#         element: Human-readable element description
#         selector: CSS selector for target element (if evaluating on specific element)
#     """
#     page = get_current_page()
#     if not page:
#         return "No browser page available"

#     try:
#         if element and selector:
#             element_handle = await page.query_selector(selector)
#             if element_handle:
#                 result = await element_handle.evaluate(function)
#             else:
#                 return json.dumps({"error": f"Element not found: {selector}"}, indent=2)
#         else:
#             result = await page.evaluate(function)

#         return json.dumps(result, indent=2)
#     except Exception as e:
#         return json.dumps({"error": f"Failed to evaluate: {str(e)}"}, indent=2)


@mcp.tool()
async def browser_wait_for(
    time: Annotated[int, "Time to wait in seconds"] = 5,
) -> dict[str, Any]:
    """Wait for a specified time to pass. Useful for waiting on animations or dynamic content."""
    page = get_current_page()
    if not page:
        return {"error": "No browser page available"}

    await page.wait_for_timeout(time * 1000)
    return await _get_snapshot_result(page, f"Waited for {time} seconds")


# Dialog and Monitoring Tools


# @mcp.tool()
# async def browser_handle_dialog(accept: bool, prompt_text: Optional[str] = None) -> str:
#     """Handle a dialog

#     Args:
#         accept: Whether to accept the dialog
#         prompt_text: Text to enter in prompt dialog
#     """
#     page = get_current_page()
#     if not page:
#         return "No browser page available"

#     # Set up dialog handler for the next dialog
#     async def handle_dialog(dialog):
#         if accept:
#             if prompt_text:
#                 await dialog.accept(prompt_text)
#             else:
#                 await dialog.accept()
#         else:
#             await dialog.dismiss()

#     page.once("dialog", handle_dialog)

#     action = "accept" if accept else "dismiss"
#     return f"Dialog handler set to {action}"


# @mcp.tool()
# async def browser_console_messages(only_errors: bool = False) -> str:
#     """Returns all console messages

#     Args:
#         only_errors: Only return error messages
#     """
#     global console_messages

#     if only_errors:
#         errors = [msg for msg in console_messages if msg["type"] == "error"]
#         return json.dumps(errors, indent=2)

#     return json.dumps(console_messages, indent=2)


# @mcp.tool()
# async def browser_network_requests() -> str:
#     """Returns all network requests since loading the page"""
#     global network_requests
#     return json.dumps(network_requests, indent=2)


# Tab Management Tools


@mcp.tool(tags={"tabs"})
async def browser_tabs(
    action: Annotated[
        Literal["list", "create", "close", "select"],
        "Operation to perform (list, create, close, select)",
    ],
    index: Annotated[Optional[int], "Tab index for close/select operations"] = None,
) -> str:
    """List, create, close, or select a browser tab"""
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


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
