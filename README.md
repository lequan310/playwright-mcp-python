# Playwright MCP Server

A Model Context Protocol (MCP) server that provides browser automation capabilities using [Playwright](https://playwright.dev). This server enables LLMs to interact with web pages through **structured accessibility snapshots** and **role-based locators**, bypassing the need for screenshots or visually-tuned models.

## ✨ Key Features

- 🎯 **Role-Based Locators**: Use semantic roles and names from accessibility tree instead of brittle CSS selectors
- 📸 **Automatic Snapshots**: Every action returns the updated page state automatically
- 🔒 **Session Management**: Supports multiple concurrent clients with isolated browser sessions
- ♿ **Accessibility-First**: Interacts with pages the same way screen readers do
- 🚀 **Playwright-Powered**: Leverages Playwright's robust browser automation

## 🚀 Setup

### Prerequisites

- Python 3.13 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

1. Create a virtual environment with Python 3.13:
```bash
uv venv --python 3.13
```

2. Install dependencies:
```bash
uv sync
```

3. Install Playwright browser binaries:
```bash
playwright install chromium
```

## 🏃 Running the Server

### Development Mode (with Inspector)

For local development and testing with the FastMCP inspector:

```bash
fastmcp dev src/server.py
```

This launches an interactive inspector where you can test tools and see real-time browser interactions.

### Production Mode

For production deployment with session management:

```bash
python src/session_server.py
```

Or for single-client mode:

```bash
python src/server.py
```

**Note**: `session_server.py` supports multiple concurrent clients with isolated browser sessions, while `server.py` is designed for single-client usage.

## Tools

<details>
<summary><b>Core automation</b></summary>


- **browser_click**
  - Title: Click
  - Description: Perform click on a web page
  - Parameters:
    - `element` (string): Human-readable element description
    - `locator` (ElementLocator): Element locator - either AriaNode with ARIA `role` and `name` fields, or Selector with `selector` field
    - `nth` (number, optional): Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)
    - `double_click` (boolean, optional): Whether to perform a double click instead of a single click
    - `button` (string, optional): Button to click (left, right, middle), defaults to left
    - `modifiers` (array, optional): Modifier keys to press (Alt, Control, Meta, Shift)
  - Read-only: **false**

- **browser_close**
  - Title: Close browser
  - Description: Close the browser and clean up all resources
  - Parameters: None
  - Read-only: **false**

- **browser_drag**
  - Title: Drag mouse
  - Description: Perform drag and drop between two elements
  - Parameters:
    - `start_element` (string): Human-readable source element description
    - `start_locator` (ElementLocator): Source element locator - either AriaNode with ARIA `role` and `name` fields, or Selector with `selector` field
    - `start_nth` (number, optional): Zero-based index for source element when multiple match
    - `end_element` (string): Human-readable target element description
    - `end_locator` (ElementLocator): Target element locator - either AriaNode with ARIA `role` and `name` fields, or Selector with `selector` field
    - `end_nth` (number, optional): Zero-based index for target element when multiple match
  - Read-only: **false**

- **browser_file_upload**
  - Title: Upload files
  - Description: Upload one or multiple files
  - Parameters:
    - `paths` (array, optional): Absolute paths to files to upload. If omitted, file chooser is cancelled.
  - Read-only: **false**

- **browser_fill_form**
  - Title: Fill form
  - Description: Fill multiple form fields
  - Parameters:
    - `fields` (array): List of FormField objects, each with `element` (string), `value` (string), `locator` (ElementLocator), and optional `nth` (number)
  - Read-only: **false**

- **browser_get_html**
  - Title: Get HTML content
  - Description: Get HTML content for debugging when locators fail
  - Parameters:
    - `selector` (string, optional): CSS selector to get HTML from (defaults to body)
    - `max_length` (number, optional): Maximum characters to return (default 50000)
    - `filter_tags` (array, optional): List of tag names to remove (e.g., ['script', 'style']). Defaults to ['script']
  - Read-only: **true**

- **browser_get_text_content**
  - Title: Get page's text content
  - Description: Get page's text content in markdown format. Useful when extracting clean article text.
  - Parameters: None
  - Read-only: **true**

- **browser_hover**
  - Title: Hover mouse
  - Description: Hover over element on page
  - Parameters:
    - `element` (string): Human-readable element description
    - `locator` (ElementLocator): Element locator - either AriaNode with ARIA `role` and `name` fields, or Selector with `selector` field
    - `nth` (number, optional): Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)
  - Read-only: **false**

- **browser_navigate**
  - Title: Navigate to a URL
  - Description: Navigate to a URL
  - Parameters:
    - `url` (string): The URL to navigate to
  - Read-only: **false**

- **browser_navigate_back**
  - Title: Go back
  - Description: Go back to the previous page
  - Parameters: None
  - Read-only: **false**

- **browser_open**
  - Title: Open browser
  - Description: Open a new browser instance
  - Parameters: None
  - Read-only: **false**

- **browser_press_key**
  - Title: Press a key
  - Description: Press a key on the keyboard
  - Parameters:
    - `key` (string): Name of the key to press or a character to generate, such as `ArrowLeft` or `a`
  - Read-only: **false**

- **browser_resize**
  - Title: Resize browser window
  - Description: Resize the browser window
  - Parameters:
    - `width` (number): Width of the browser window
    - `height` (number): Height of the browser window
  - Read-only: **false**

- **browser_search**
  - Title: Search on Google
  - Description: Search for a topic using Google search
  - Parameters:
    - `query` (string): The search query or topic to search for
  - Read-only: **false**

- **browser_select_option**
  - Title: Select option
  - Description: Select an option in a dropdown
  - Parameters:
    - `element` (string): Human-readable element description
    - `values` (array): Array of values to select in the dropdown
    - `locator` (ElementLocator): Element locator - either AriaNode with ARIA ARIA `role` and `name` fields, or Selector with `selector` field
    - `nth` (number, optional): Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)
  - Read-only: **false**

- **browser_snapshot**
  - Title: Page snapshot
  - Description: Capture accessibility snapshot of the current page
  - Parameters: None
  - Read-only: **true**

- **browser_take_screenshot**
  - Title: Take a screenshot
  - Description: Take a screenshot of the current page
  - Parameters:
    - `type` (string, optional): Image format (png or jpeg). Default is png.
    - `element` (string, optional): Human-readable element description
    - `locator` (ElementLocator, optional): Element locator - either AriaNode with ARIA `role` and `name` fields, or Selector with `selector` field
    - `nth` (number, optional): Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)
    - `full_page` (boolean, optional): Take screenshot of full scrollable page
  - Read-only: **true**

- **browser_type**
  - Title: Type text
  - Description: Type text into editable element
  - Parameters:
    - `element` (string): Human-readable element description
    - `text` (string): Text to type into the element
    - `locator` (ElementLocator): Element locator - either AriaNode with ARIA `role` and `name` fields, or Selector with `selector` field
    - `nth` (number, optional): Zero-based index when multiple elements match (e.g., nth=0 for first, nth=1 for second)
    - `submit` (boolean, optional): Whether to submit (press Enter after)
    - `slowly` (boolean, optional): Whether to type one character at a time
  - Read-only: **false**

</details>

<details>
<summary><b>Tab management</b></summary>

- **browser_tabs**
  - Title: Manage tabs
  - Description: List, create, close, or select a browser tab
  - Parameters:
    - `action` (string): Operation to perform (list, create, close, select)
    - `index` (number, optional): Tab index for close/select operations. If omitted for close, current tab is closed.
  - Read-only: **false**

</details>
