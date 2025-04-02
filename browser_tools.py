from typing import List
from pydantic import BaseModel, Field
from langchain_core.tools import Tool
from browser import Browser, BrowserError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

class ClickByIndexSchema(BaseModel):
    index: int = Field(..., description="The numerical index (#number) of the interactive element to click.")

class TypeByIndexSchema(BaseModel):
    index: int = Field(..., description="The numerical index (#number) of the input element to type into.")
    text: str = Field(..., description="The text to type into the element.")

class NavigateSchema(BaseModel):
    url: str = Field(..., description="The complete URL to navigate to (e.g., 'https://www.google.com').")

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

async def get_current_url(browser: Browser) -> str:
    print("Tool: Getting current URL")
    return await execute_browser_tool(browser, browser.get_current_url())

async def get_page_title(browser: Browser) -> str:
    print("Tool: Getting page title")
    return await execute_browser_tool(browser, browser.get_title())

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
    page = browser.get_page()
    await execute_browser_tool(browser, page.keyboard.press('Enter'))
    await browser.wait_for_page_load()

async def click_element_by_index(browser: Browser, index: int) -> str:
    print(f"Tool: Clicking element by index '{index}'")
    return await execute_browser_tool(browser, browser.click_element_by_index(index))

async def type_into_element_by_index(browser: Browser, index: int, text: str) -> str:
    print(f"Tool: Typing '{text[:30]}...' into element index '{index}'")
    return await execute_browser_tool(browser, browser.type_element_by_index(index, text))


async def ultimate_task_done():
    print("TASK DONE SUCCESSFULLY-----------------------------------------XXX-------------------")
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
            args_schema=ClickByIndexSchema 
        ),
        Tool.from_function(
            func=lambda index, text: type_into_element_by_index(browser, index, text),
            name="type_into_element_by_index",
            description="Type text into an input element identified by its numerical index (e.g., the '[1]' from 'get_interactive_elements').",
            args_schema=TypeByIndexSchema
        ),
        Tool.from_function(
            func=ultimate_task_done,
            name="ultimate_task_done",
            description="Send Final results to user. Use this only when the ultimate task is done and No further actions are needed. "
        )
    ]
    return tools