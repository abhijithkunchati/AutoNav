# crustdata-challenge
Instructions

```
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -r requirements.txt
playwright install        # playwright's own browser for now
python main.py
```

  

# Project Details
- Does simple flows. (or Complex, depends on how you define complexity)
- Only been tested with gemini, cause it's the only api key I have 
- I have included my api key in .env to make it easier for you to test. (It's free api keys, so no security issues)
- Change google api key if rate limits are triggered
- run main.py,

main.py - boilerplate for running the project, you can customize the task here
agent.py - main logic resides here
browser.py - wrapper on playwright browser ( I am currently working on own playwright impl using chrome-dev-tools protocol )
browser_tools.py - tool bindings for llm and browser API's
utils.py - utility functions for prompt formatting and html dom-parsing 
prompt.md - The main system prompt, taken from browser-use (Changing the prompt is giving better perf, working on writing better prompt)
I intentionally kept the project structure flat because the files are small (less than 500 lines). I will refactor it when I add more features.


# Workflow
We send prompts to LLM (Instructions, task, previous responses, toolcall results and current page state)
It sends a sequence of tool calls to execute
We execute those tool calls and then add those results to the existing prompt
Repeat until task is done

