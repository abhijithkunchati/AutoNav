import asyncio
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import Tool
from browser import Browser, BrowserError # Assuming 'browser.py' contains your Browser class
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

# --- Tool Schemas ---
class GetInteractiveElementsSchema(BaseModel):
    pass # No arguments needed

class ClickByIndexSchema(BaseModel):
    index: int = Field(..., description="The numerical index (#number) of the interactive element to click.")

class TypeByIndexSchema(BaseModel):
    index: int = Field(..., description="The numerical index (#number) of the input element to type into.")
    text: str = Field(..., description="The text to type into the element.")

class NavigateSchema(BaseModel):
    url: str = Field(..., description="The complete URL to navigate to (e.g., 'https://www.google.com').")

class ClickSchema(BaseModel):
    selector: str = Field(..., description="CSS selector for the element to click (e.g., 'button#submit', 'a.results-link').")

class TypeSchema(BaseModel):
    selector: str = Field(..., description="CSS selector for the input element to type into (e.g., 'input[name=\"q\"]').")
    text: str = Field(..., description="The text to type into the element.")

class ClickElementByTextSchema(BaseModel):
    text: str = Field(..., description="The exact visible text content of the element to click.")
    nth: int = Field(default=0, description="The 0-based index if multiple elements match the text (0 for the first).")
    element_type: Optional[str] = Field(default=None, description="Optional element type filter (e.g., 'button', 'a', 'span'). If None, searches all elements.")


# --- Browser Interaction Helper ---

async def execute_browser_tool(browser: Browser, coro):
    """Helper to execute browser coroutines with error handling."""
    if not browser or not browser._is_initialized:
        return "Error: Browser is not initialized or available."
    try:
        result = await coro
        if result is None:
             return "Success: Action completed successfully."
        return str(result) # Ensure string output for LLM
    except BrowserError as e:
        print(f"Browser tool error: {e}")
        return f"Error: Browser Error: {e}"
    except PlaywrightTimeoutError as e:
        print(f"Browser tool timeout: {e}")
        return f"Error: Browser Timeout Error: Action could not be completed in time. {e}"
    except Exception as e:
        print(f"Unexpected browser tool error: {e}")
        return f"Error: An unexpected error occurred: {e}"

# --- Core Tool Functions (Accept Browser instance) ---

async def navigate_to_url(browser: Browser, url: str) -> str:
    print(f"Tool: Navigating to {url}")
    return await execute_browser_tool(browser, browser.navigate_to_url(url))

async def click_element(browser: Browser, selector: str) -> str:
    print(f"Tool: Clicking element '{selector}'")
    return await execute_browser_tool(browser, browser.click(selector))

async def type_into_element(browser: Browser, selector: str, text: str) -> str:
    print(f"Tool: Typing '{text[:30]}...' into '{selector}'")
    return await execute_browser_tool(browser, browser.type(selector, text))

async def get_current_url(browser: Browser) -> str:
    print("Tool: Getting current URL")
    return await execute_browser_tool(browser, browser.get_current_url())

async def get_page_title(browser: Browser) -> str:
    print("Tool: Getting page title")
    return await execute_browser_tool(browser, browser.get_title())

async def read_page_content(browser: Browser, format: str = "html") -> str:
    print(f"Tool: Reading page content (format: {format})")
    return await execute_browser_tool(browser, browser.get_content(format=format))

async def navigate_back(browser: Browser) -> str:
    print("Tool: Navigating back")
    return await execute_browser_tool(browser, browser.navigate_back())

async def navigate_forward(browser: Browser) -> str:
    print("Tool: Navigating forward")
    return await execute_browser_tool(browser, browser.navigate_forward())

async def refresh_page(browser: Browser) -> str:
    print("Tool: Refreshing page")
    return await execute_browser_tool(browser, browser.refresh())

async def press_enter_key(browser: Browser) -> str:
    print("Tool: Pressing Enter key")
    page = browser._ensure_page()
    result = await execute_browser_tool(browser, page.keyboard.press('Enter'))
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)  # Wait for network to be idle
    except PlaywrightTimeoutError:
        print("Warning: Page load state wait timed out after pressing Enter.")
    except Exception as e:
        print(f"Warning: Error waiting for load state after Enter: {e}")
    return result if result else "Success: Enter key pressed successfully."


async def click_element_by_index(browser: Browser, index: int) -> str:
    print(f"Tool: Clicking element by index '{index}'")
    return await execute_browser_tool(browser, browser.click_by_index(index))

async def type_into_element_by_index(browser: Browser, index: int, text: str) -> str:
    print(f"Tool: Typing '{text[:30]}...' into element index '{index}'")
    return await execute_browser_tool(browser, browser.type_by_index(index, text))


async def click_element_with_text(browser: Browser, params: ClickElementByTextSchema) -> str:
    try:
        element_node = await browser.get_locate_element_by_text(
            text=params.text,
            nth=params.nth,
            element_type=params.element_type
        )

        if element_node:
            try:
                await element_node.scroll_into_view_if_needed()
                await element_node.click(timeout=5500, force=True)
            except Exception:
                try:
                    await element_node.evaluate('el => el.click()')
                except Exception as e:
                    return f"Error: Element not clickable with text '{params.text}' - {e}"
        else:
            return f"Error: No element found '{params.text}' - {e}"
    except Exception as e:
        return f"Error: Element not clickable with text '{params.text}' - {e}"


# --- Function to Create LangChain Tools ---

def create_browser_tools(browser: Browser) -> List[Tool]:
    """Creates LangChain Tool objects, binding them to the provided Browser instance."""
    tools = [
        Tool.from_function(
            func=lambda url: navigate_to_url(browser, url),
            name="navigate_to_url",
            description="Navigate the browser to a specified URL. Use full URLs (e.g., https://example.com).",
            args_schema=NavigateSchema
        ),
        Tool.from_function(
            func=lambda selector: click_element(browser, selector),
            name="click_element",
            description="Click on an HTML element specified by a CSS selector (e.g., 'button#submit', 'a.some-class[href=\"/login\"]').",
            args_schema=ClickSchema
        ),
        Tool.from_function(
            func=lambda selector, text: type_into_element(browser, selector, text),
            name="type_into_element",
            description="Type text into an input field or textarea specified by a CSS selector.",
            args_schema=TypeSchema
        ),
        Tool.from_function(
            func=lambda: read_page_content(browser),
            name="read_page_content",
            description="Read the content of the current webpage. Default format is cleaned text. Use format='html' for raw HTML.",
        ),
        Tool.from_function(
            func=lambda: get_current_url(browser),
            name="get_current_url",
            description="Get the current URL of the webpage the browser is on.",
        ),
        Tool.from_function(
            func=lambda: get_page_title(browser),
            name="get_page_title",
            description="Get the title of the current webpage.",
        ),
        Tool.from_function(
            func=lambda: navigate_back(browser),
            name="navigate_back",
            description="Go back to the previous page in the browser history.",
        ),
        Tool.from_function(
            func=lambda: navigate_forward(browser),
            name="navigate_forward",
            description="Go forward to the next page in the browser history.",
        ),
        Tool.from_function(
            func=lambda: refresh_page(browser),
            name="refresh_page",
            description="Reload the current page in the browser.",
        ),
        Tool.from_function(
            func=lambda: press_enter_key(browser),
            name="press_enter_key",
            description="Simulates pressing the Enter key on the keyboard. Use this after typing text into a search bar or form field to submit it.",
        ),
         Tool.from_function(
            func=lambda index: click_element_by_index(browser, index),
            name="click_element_by_index",
            description="Click on an interactive element identified by its numerical index (e.g., the '[1]' from 'get_interactive_elements').",
            args_schema=ClickByIndexSchema # Use the new schema
        ),
        Tool.from_function(
            func=lambda index, text: type_into_element_by_index(browser, index, text),
            name="type_into_element_by_index",
            description="Type text into an input element identified by its numerical index (e.g., the '[1]' from 'get_interactive_elements').",
            args_schema=TypeByIndexSchema # Use the new schema
        ),
        Tool.from_function(
            func=lambda text, nth=0, element_type=None: click_element_with_text(browser, ClickElementByTextSchema(text=text, nth=nth)),
            name="click_element_by_text",
            description="Click on an element identified by its exact visible text content. Use 'nth' (default 0) to specify which element if multiple match. Optionally filter by 'element_type' (e.g., 'button', 'a'). Prefer this over other tools for clicking elements.",
            args_schema=ClickElementByTextSchema
        )
    ]
    return tools