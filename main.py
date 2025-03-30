import os
import asyncio
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from agent import Agent # Import the Agent class
# Assuming 'browser.py' exists and defines BrowserError if needed
# from browser import BrowserError

# --- Environment Setup ---
load_dotenv()

api_key = os.getenv('GEMINI_API_KEY', '')
if not api_key:
    raise ValueError("Environment variable 'GEMINI_API_KEY' not found. Please set it in your .env file or environment.")

# --- Main Execution ---
async def main():
    task = (
        "Please navigate to duckduckgo.com, search for 'latest AI news Gemini model', "
        "press the Enter key after typing the search query, "
        "and then read the main content of the results page and summarize the first few results."
    )

    llm = ChatGoogleGenerativeAI(model='gemini-1.5-flash-latest', api_key=api_key)
    agent = Agent(llm=llm, max_iterations=7) 
    final_result = "Agent execution failed."
    try:
        await agent.setup()
        final_result = await agent.interact(task)

    except RuntimeError as e:
         print(f"Agent runtime error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during agent execution: {e}")

    finally:
        await agent.close() 

    print("\n--- Final Agent Output ---")
    print(final_result)
    print("--------------------------")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ValueError as e: # Catch env variable error
        print(f"Configuration Error: {e}")
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")