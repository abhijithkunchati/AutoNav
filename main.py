import os
import asyncio
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from agent import Agent 

# --- Environment Setup ---
load_dotenv()

api_key = os.getenv('GEMINI_API_KEY', '')
if not api_key:
    raise ValueError("Environment variable 'GEMINI_API_KEY' not found. Please set it in your .env file or environment.")


async def main():
    task = (
        '''You are an AI agent designed to automate browser tasks. Your goal is to accomplish the ultimate task following the rules. 
        Use the tools provided.
        first get interactive elements before clicking on them.
        You can execute in multiple steps. If you need to know the webpage state before proceeding. 
        Use the last tool in the sequence to get the webpage state, so in the next interaction you can use the knowledge of the webpage state to proceed.
        (eg: when you search for something, you need to know the webpage state before clicking on the first link),
        Go to duckduckgo.com and search for latest news on elon musk and click on first link, and summarize the article. 
        '''
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
    except ValueError as e:
        print(f"Configuration Error: {e}")
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")