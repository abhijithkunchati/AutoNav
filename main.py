import os
import asyncio
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from auto_nav.agent import Agent 

# --- Environment Setup ---
load_dotenv()

api_key = os.getenv('GEMINI_API_KEY', '')
if not api_key:
    raise ValueError("Environment variable 'GEMINI_API_KEY' not found. Please set it in your .env file or environment.")


task = (
    '''
    Ultimate Task: 
    go to ebay and buy a new hp laptop with 16GB RAM and 512GB SSD.
    '''
)

llm = ChatGoogleGenerativeAI(model='gemini-2.0-flash', api_key=api_key)
async def main():
    agent = Agent(llm=llm)
    final_result = None
    try:
        final_result = await agent.interact(task)
    except RuntimeError as e:
         print(f"Agent runtime error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during agent execution: {e}")
    finally:
        await agent.close() 

    print("\n--- Final Agent Output ---")
    print(final_result if final_result is not None else "Failed to retrieve the final result.")
    print("--------------------------")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ValueError as e:
        print(f"Configuration Error: {e}")
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")