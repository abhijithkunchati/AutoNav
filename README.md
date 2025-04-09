# Auto Nav
AI Agent for automating browser workflows

## Demo
 
 ![til](./assets/AI_Agent_Demo_2.gif)



### Instructions

```
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -r requirements.txt
playwright install        # playwright's own browser for now
# add your gemini api key in .env file. Look into .env.example for example
python main.py
```



- main.py - boilerplate for running the project, you can customize the task here
- agent.py - main logic resides here
- browser.py - wrapper on playwright browser
- browser_tools.py - tool bindings for llm and browser API's
- .*utils.py - utility functions for prompt formatting and html dom-parsing 
- prompt.md - The main system prompt


# Workflow
- We send prompts to LLM (Instructions, task, previous responses, toolcall results and current page state)
- It sends a sequence of tool calls to execute
- We execute those tool calls and then add those results to the existing prompt
- Repeat until task is done

