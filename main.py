import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import Tool
from pydantic import BaseModel, Field
from typing import Optional, Type
from playwright.async_api import async_playwright

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY', '')
if not api_key:
    raise ValueError('Provide GEMINI_API_KEY')

class GoogleSearchSchema(BaseModel):
    query: str = Field(..., description="Search query to look up on Google")

async def google_search(query: str) -> str:
    """Perform a Google search and return the top results"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        await page.goto(f"https://www.google.com/search?q={query}")
        await page.wait_for_selector("#search")
        results = []
        result_elements = await page.query_selector_all(".g")
        
        for i, element in enumerate(result_elements[:3]):
            title = await element.query_selector("h3")
            link = await element.query_selector("a")
            snippet = await element.query_selector(".VwiC3b")
            
            if title and link and snippet:
                results.append({
                    "title": await title.inner_text(),
                    "url": await link.get_attribute("href"),
                    "snippet": await snippet.inner_text()
                })
        
        await browser.close()
        
        if not results:
            return "No search results found"
        
        formatted_results = "\n\n".join(
            f"Result {i+1}:\nTitle: {r['title']}\nURL: {r['url']}\nSnippet: {r['snippet']}"
            for i, r in enumerate(results)
        )
        return f"Google search results for '{query}':\n\n{formatted_results}"

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