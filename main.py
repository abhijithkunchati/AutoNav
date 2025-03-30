import os
import asyncio
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import Tool
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Type
from browser import Browser, BrowserError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY', '')
if not api_key:
    raise ValueError('Provide GEMINI_API_KEY')

shared_browser: Optional[Browser] = None

async def execute_browser_tool(coro):
    global shared_browser
    if not shared_browser or not shared_browser._is_initialized:
        return "Error: Browser is not initialized or available."
    try:
        result = await coro
        if result is None:
             return "Action completed successfully."
        return result
    except BrowserError as e:
        print(f"Browser tool error: {e}")
        return f"Browser Error: {e}"
    except PlaywrightTimeoutError as e:
        print(f"Browser tool timeout: {e}")
        return f"Browser Timeout Error: Action could not be completed in time. {e}"
    except Exception as e:
        print(f"Unexpected browser tool error: {e}")
        return f"An unexpected error occurred: {e}"

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

async def navigate_to_url_tool(url: str) -> str:
    print(f"Tool: Navigating to {url}")
    return await execute_browser_tool(shared_browser.navigate_to_url(url))

async def click_element_tool(selector: str) -> str:
    print(f"Tool: Clicking element '{selector}'")
    return await execute_browser_tool(shared_browser.click(selector))

async def type_into_element_tool(selector: str, text: str) -> str:
    print(f"Tool: Typing '{text[:30]}...' into '{selector}'")
    return await execute_browser_tool(shared_browser.type(selector, text))

async def get_current_url_tool() -> str:
    print("Tool: Getting current URL")
    return await execute_browser_tool(shared_browser.get_current_url())

async def get_page_title_tool() -> str:
    print("Tool: Getting page title")
    return await execute_browser_tool(shared_browser.get_title())

async def read_page_content_tool(format: str = "text", max_length: int = 4000) -> str:
    print(f"Tool: Reading page content (format: {format}, max_length: {max_length})")
    safe_max_length = max(100, min(max_length, 15000))
    return await execute_browser_tool(shared_browser.get_content(format=format, max_length=safe_max_length))

async def navigate_back_tool() -> str:
    print("Tool: Navigating back")
    return await execute_browser_tool(shared_browser.navigate_back())

async def navigate_forward_tool() -> str:
    print("Tool: Navigating forward")
    return await execute_browser_tool(shared_browser.navigate_forward())

async def refresh_page_tool() -> str:
    print("Tool: Refreshing page")
    return await execute_browser_tool(shared_browser.refresh())

async def press_enter_key_tool() -> str:
    print("Tool: Pressing Enter key")
    page = shared_browser._ensure_page() 
    return await execute_browser_tool(page.keyboard.press('Enter')) 

tools = [
    Tool.from_function(
        func=navigate_to_url_tool,
        name="navigate_to_url",
        description="Navigate the browser to a specified URL. Use full URLs (e.g., https://example.com).",
        args_schema=NavigateSchema
    ),
    Tool.from_function(
        func=click_element_tool,
        name="click_element",
        description="Click on an HTML element specified by a CSS selector (e.g., 'button#submit', 'a.some-class[href=\"/login\"]').",
        args_schema=ClickSchema
    ),
    Tool.from_function(
        func=type_into_element_tool,
        name="type_into_element",
        description="Type text into an input field or textarea specified by a CSS selector.",
        args_schema=TypeSchema
    ),
    Tool.from_function(
        func=read_page_content_tool,
        name="read_page_content",
        description="Read the content of the current webpage. Default format is cleaned text. Use format='html' for raw HTML.",
        args_schema=GetContentSchema
    ),
     Tool.from_function(
        func=get_current_url_tool,
        name="get_current_url",
        description="Get the current URL of the webpage the browser is on.",
    ),
     Tool.from_function(
        func=get_page_title_tool,
        name="get_page_title",
        description="Get the title of the current webpage.",
    ),
     Tool.from_function(
        func=navigate_back_tool,
        name="navigate_back",
        description="Go back to the previous page in the browser history.",
    ),
    Tool.from_function(
        func=navigate_forward_tool,
        name="navigate_forward",
        description="Go forward to the next page in the browser history.",
    ),
     Tool.from_function(
        func=refresh_page_tool,
        name="refresh_page",
        description="Reload the current page in the browser.",
    ),
    Tool.from_function(
        func=press_enter_key_tool,
        name="press_enter_key",
        description="Simulates pressing the Enter key on the keyboard. Use this after typing text into a search bar or form field to submit it.",
        # No args_schema needed as it takes no arguments
    ),
]

async def run_agent(task: str, llm, model_with_tools):
    print(f"\n--- Running Agent for Task: {task} ---")
    response = await model_with_tools.ainvoke(task)
    print(f"\nInitial LLM Response Type: {type(response)}")
    max_iterations = 5
    current_iteration = 0
    message_history = [response]

    while response.tool_calls and current_iteration < max_iterations:
        print(f"\nIteration {current_iteration + 1}: LLM requested {len(response.tool_calls)} tool call(s)...")
        tool_messages = []

        for tool_call in response.tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id")

            if not tool_name or not tool_id:
                print(f"Skipping invalid tool call (missing name or id): {tool_call}")
                tool_messages.append(ToolMessage(content=f"Error: Invalid tool call structure received: {tool_call}", tool_call_id=tool_id or "unknown"))
                continue

            print(f"  Invoking tool '{tool_name}' with args: {tool_args} (Call ID: {tool_id})")
            tool = next((t for t in tools if t.name == tool_name), None)

            if tool:
                try:
                    tool_func = tool.func
                    if tool.args_schema:
                         result = await tool_func(**tool_args)
                    else:
                         result = await tool_func()

                    print(f"  Tool '{tool_name}' result type: {type(result)}")
                    content_result = str(result) if result is not None else "Action completed successfully."
                    tool_messages.append(ToolMessage(content=content_result, tool_call_id=tool_id))
                    print(f"  Tool '{tool_name}' completed.")

                except Exception as e:
                    print(f"  Error invoking tool {tool_name}: {e}")
                    tool_messages.append(ToolMessage(content=f"Error executing tool '{tool_name}': {e}", tool_call_id=tool_id))
            else:
                print(f"  Tool '{tool_name}' not found.")
                tool_messages.append(ToolMessage(content=f"Error: Tool '{tool_name}' is not available.", tool_call_id=tool_id))

        print(f"\nSending {len(tool_messages)} tool results back to LLM...")
        message_history.extend(tool_messages)
        response = await model_with_tools.ainvoke(message_history)
        message_history.append(response)
        current_iteration += 1

    print("\n--- Agent Finished ---")
    if response.tool_calls and current_iteration >= max_iterations:
        print("Reached max iterations, stopping.")
        return "Agent reached maximum iterations without completing the task."
    elif response.content:
        print("LLM provided final content response.")
        return response.content
    else:
        print("LLM did not provide a final content response after last action.")
        return f"Agent finished without a final text response. Last response object: {response}"

async def main():
    global shared_browser

    print("Initializing shared browser...")
    shared_browser = Browser()
    try:
        await shared_browser.start() 
        llm = ChatGoogleGenerativeAI(model='gemini-1.5-flash-latest', api_key=api_key)
        model_with_tools = llm.bind_tools(tools)

        task = (
            "Please navigate to duckduckgo.com, search for 'latest AI news Gemini model', "
            "click the search button (if necessary, often typing Enter is enough), "
            "and then read the main content of the results page and summarize the first few results."
        )

        final_result = await run_agent(task, llm, model_with_tools)

        print("\n--- Final Agent Output ---")
        print(final_result)

    except BrowserError as e:
         print(f"Failed to initialize or run browser: {e}")
    except Exception as e:
        print(f"An unexpected error occurred in main: {e}")
    finally:
        print("\nClosing shared browser...")
        if shared_browser:
            await shared_browser.close()
        print("Browser closed.")

if __name__ == "__main__":
    asyncio.run(main())
