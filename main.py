import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import Tool
from pydantic import BaseModel, Field
from typing import Optional, Type

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY', '')
if not api_key:
    raise ValueError('Provide GEMINI_API_KEY')


class ContinentSchema(BaseModel):
    continent: str = Field(
        ...,
        description="The continent",
        enum=["Europe", "Asia", "Africa", "North America", "South America", "Australia", "Antarctica"]
    )

async def book_flight(continent: str) -> str:
    """Book a flight from USA to the specified continent"""
    print(f"Booking flight to the {continent}")
    return f"Successfully booked flight to {continent}"

async def book_return_flight(continent: str) -> str:
    """Book a return flight from the specified continent to USA"""
    print(f"Booking return flight to {continent}")
    return f"Successfully booked return flight from {continent}"


tools = [
    Tool.from_function(
        func=book_flight,
        name="book_flight",
        description="Book a forward flight from USA to the specified continent",
        args_schema=ContinentSchema
    ),
    Tool.from_function(
        func=book_return_flight,
        name="book_return_flight",
        description="Book a return flight from the specified continent to USA",
        args_schema=ContinentSchema
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

if __name__ == "__main__":
    import asyncio
    task = "I want to go to europe and come back to the USA"
    result = asyncio.run(run_agent(task))