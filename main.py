import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import Tool
from pydantic import BaseModel, Field
from typing import List, Dict
from playwright.async_api import async_playwright, Playwright, Browser, Page
from flags import CHROME_ARGS

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY', '')
if not api_key:
    raise ValueError('Provide GEMINI_API_KEY')

class GoogleSearchSchema(BaseModel):
    query: str = Field(..., description="Search query to look up on Google")


async def launch_browser(playwright: Playwright, headless: bool = False) -> Browser:
    """Launch a configured browser instance with anti-detection measures."""
    chrome_args = list(CHROME_ARGS)
    browser = await playwright.chromium.launch(
        headless=headless,
        args=chrome_args,
        handle_sigterm=False,
        handle_sigint=False,
    )
    return browser

async def extract_search_results(page: Page) -> List[Dict[str, str]]:
    results = []
    result_elements = await page.query_selector_all(".g")
    
    for element in result_elements[:3]:
        title_element = await element.query_selector("h3")
        link_element = await element.query_selector("a")
        snippet_element = await element.query_selector(".VwiC3b")
        
        if all([title_element, link_element, snippet_element]):
            results.append({
                "title": await title_element.inner_text(),
                "url": await link_element.get_attribute("href"),
                "snippet": await snippet_element.inner_text()
            })
    
    return results

def format_results(query: str, results: List[Dict[str, str]]) -> str:
    if not results:
        return "No search results found"
    
    formatted = [
        f"Result {i+1}:\nTitle: {r['title']}\nURL: {r['url']}\nSnippet: {r['snippet']}"
        for i, r in enumerate(results)
    ]
    return f"Google search results for '{query}':\n\n" + "\n\n".join(formatted)

async def google_search(query: str) -> str:
    async with async_playwright() as playwright:
        browser = await launch_browser(playwright, headless=False)
        page = await browser.new_page()
        
        try:
            await page.goto(f"https://www.google.com/search?q={query}", timeout=15000)
            await page.wait_for_selector("#search", timeout=10000)
            
            results = await extract_search_results(page)
            return format_results(query, results)
            
        finally:
            await browser.close()

tools = [
    Tool.from_function(
        func=google_search,
        name="google_search",
        description="Perform a Google search and return the top results",
        args_schema=GoogleSearchSchema
    )
]

async def run_agent(task: str):
    llm = ChatGoogleGenerativeAI(model='gemini-2.0-flash-exp', api_key=api_key)
    model_with_tools = llm.bind_tools(tools)
    response = await model_with_tools.ainvoke(task)
    if response.tool_calls:
        results = []
        for tool_call in response.tool_calls:
            tool = next(t for t in tools if t.name == tool_call["name"])
            result = await tool.invoke(tool_call["args"])
            results.append(result)
        return "\n".join(results)
    
    return response.content

async def main():
    task = "I want to know the latest news about AI. Please search for it on Google."
    result = await run_agent(task)
    print(result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())