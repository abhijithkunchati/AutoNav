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

class GetContentSchema(BaseModel):
    format: str = Field(default="text", description="Content format: 'text' (cleaned visible text) or 'html' (raw HTML).")
    max_length: int = Field(default=4000, description="Maximum characters to return for 'text' format.")

# --- Browser Interaction Helper ---

async def execute_browser_tool(browser: Browser, coro):
    """Helper to execute browser coroutines with error handling."""
    if not browser or not browser._is_initialized:
        return "Error: Browser is not initialized or available."
    try:
        result = await coro
        if result is None:
             return "Action completed successfully."
        return str(result) # Ensure string output for LLM
    except BrowserError as e:
        print(f"Browser tool error: {e}")
        return f"Browser Error: {e}"
    except PlaywrightTimeoutError as e:
        print(f"Browser tool timeout: {e}")
        return f"Browser Timeout Error: Action could not be completed in time. {e}"
    except Exception as e:
        print(f"Unexpected browser tool error: {e}")
        return f"An unexpected error occurred: {e}"

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

async def read_page_content(browser: Browser, format: str = "text", max_length: int = 4000) -> str:
    print(f"Tool: Reading page content (format: {format}, max_length: {max_length})")
    safe_max_length = max(100, min(max_length, 15000))
    return await execute_browser_tool(browser, browser.get_content(format=format, max_length=safe_max_length))

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
    return result if result else "Enter key pressed successfully."

async def get_interactive_elements(browser: Browser) -> str:
    print("Tool: Getting interactive elements view")
    if not browser or not browser._is_initialized:
        return "Error: Browser is not initialized or available."
    try:
        state: DOMState = await browser.get__dom_state()
        _string = state.get__string()
        if not _string:
             return "No interactive elements found or DOM is empty."
        header = f"Current URL: {state.url}\nPage Title: {state.title}\n\nInteractive Elements:\n"
        return header + _string
    except BrowserError as e:
        print(f"Browser tool error getting interactive elements: {e}")
        return f"Browser Error: {e}"
    except Exception as e:
        print(f"Unexpected browser tool error getting interactive elements: {e}")
        return f"An unexpected error occurred: {e}"


async def click_element_by_index(browser: Browser, index: int) -> str:
    print(f"Tool: Clicking element by index '{index}'")
    return await execute_browser_tool(browser, browser.click_by_index(index))

async def type_into_element_by_index(browser: Browser, index: int, text: str) -> str:
    print(f"Tool: Typing '{text[:30]}...' into element index '{index}'")
    return await execute_browser_tool(browser, browser.type_by_index(index, text))


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
        # Tool.from_function(
        #     func=lambda format="text", max_length=4000: read_page_content(browser, format, max_length),
        #     name="read_page_content",
        #     description="Read the content of the current webpage. Default format is cleaned text. Use format='html' for raw HTML.",
        #     args_schema=GetContentSchema
        # ),
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
            func=lambda: get_interactive_elements(browser),
            name="get_interactive_elements",
            description="Get a  view of the current page, focusing on interactive elements (links, buttons, inputs) marked with numerical indices like [1], [2]. Use this to identify elements for clicking or typing.",
            args_schema=GetInteractiveElementsSchema # Use the new schema
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
    ]
    return tools