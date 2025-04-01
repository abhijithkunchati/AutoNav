import asyncio
from typing import List, Optional
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import Tool
from browser import Browser
from browser_tools import create_browser_tools
from prompt_utils import create_observation_message, load_prompt

class Agent:
    """Encapsulates the agent logic, browser interaction, and LLM communication."""
    def __init__(
        self,
        llm,
        max_iterations: int = 40,
    ):
        self.llm = llm
        self.max_iterations = max_iterations
        self.browser: Optional[Browser] = None
        self.tools: List[Tool] = []
        self.model_with_tools = None 

    async def setup(self):
        await self._initialize_browser_and_tools()
    
    async def _initialize_browser_and_tools(self):
        if self.browser:
            return
        self.browser = Browser()
        await self.browser.start()
        self.tools = create_browser_tools(self.browser)
        self.model_with_tools = self.llm.bind_tools(self.tools)

    async def interact(self, task: str) -> str:
        """Runs the agent for the given task."""
        if not self.browser or not self.model_with_tools:
            raise RuntimeError("Agent is not set up. Call agent.setup() before running.")
        main_prompt = load_prompt()
        message_history: List[BaseMessage] = [main_prompt]
        message_history.append(task)

        print(f"\n--- Running Agent for Task: {task} ---")
        current_iteration = 0
        current_browser_state_message = await create_observation_message(self.browser, current_iteration, self.max_iterations)
        message_history.append(current_browser_state_message)
        response = await self.model_with_tools.ainvoke(message_history)
        message_history.pop()
        message_history.append(response)

        print(f"\nInitial LLM Response Type: {type(response)}")
        print(f"Initial LLM Response Content:\n{response.content}")
        print(f"Initial LLM Tool Calls: {response.tool_calls}")
        empty_tool_calls = 0


        while empty_tool_calls<5 and current_iteration < self.max_iterations:
            current_iteration += 1
            print(f"\nIteration {current_iteration + 1}/{self.max_iterations}: LLM requested {len(response.tool_calls)} tool call(s)...")
            tool_messages: List[ToolMessage] = []

            for tool_call in response.tool_calls:
                if tool_call.get("name") == "ultimate_task_done":
                    print("Ultimate task done. Breaking the loop.")
                    break
                tool_result: ToolMessage = await self._execute_tool_call(tool_call)
                tool_messages.append(tool_result)

            print(f"\nSending {len(tool_messages)} tool results back to LLM...")
            message_history.extend(tool_messages)
            current_browser_state_message = await create_observation_message(self.browser, current_iteration, self.max_iterations)
            message_history.append(current_browser_state_message)
            response = await self.model_with_tools.ainvoke(message_history)
            message_history.pop()
            message_history.append(response)
            print(f"\nLLM Response Content:\n{response.content}")
            print(f"LLM Tool Calls: {response.tool_calls}")

        print("\n--- Agent Finished ---")
        print(message_history)
        if response.tool_calls and current_iteration >= self.max_iterations:
            print("Reached max iterations, stopping.")
            return "Agent reached maximum iterations without completing the task."
        elif response.content:
            print("LLM provided final content response.")
            return response.content
        else:
            # If the last action was successful but didn't yield content
            last_message = message_history[-1]
            if isinstance(last_message, ToolMessage) and "Error" not in last_message.content:
                 return "Agent finished actions successfully, but provided no final summary."
            elif isinstance(last_message, ToolMessage):
                 return f"Agent finished with an error in the last tool call: {last_message.content}"
            else: # Should typically have content or tool_calls unless something went wrong
                print("LLM did not provide a final content response after last action.")
                return f"Agent finished without a final text response. Last response object: {response!r}"


    async def _execute_tool_call(self, tool_call: dict) -> ToolMessage:
        """Executes a single tool call requested by the LLM."""
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        tool_id = tool_call.get("id")
        print(f"  Invoking tool '{tool_name}' with args: {tool_args} (Call ID: {tool_id})")
        tool = next((t for t in self.tools if t.name == tool_name), None)
        try:
            # The tool.func here is the lambda created in create_browser_tools,
            # which already captures the browser instance and calls the correct underlying function.
            if tool.args_schema:
                validated_args = tool.args_schema(**tool_args)
                result = await tool.func(**validated_args.dict())
            else:
                result = await tool.func()

            print(f"  Tool '{tool_name}' result type: {type(result)}")
            # Ensure result is a string for ToolMessage content
            content_result = str(result) if result is not None else "Action completed successfully."
            print(f"  Tool '{tool_name}' completed.")
            return ToolMessage(content=content_result, tool_call_id=tool_id)

        except Exception as e:
            error_msg = f"Error executing tool '{tool_name}': {e}"
            print(f"  Error invoking tool {tool_name}: {e}")
            return ToolMessage(content=error_msg, tool_call_id=tool_id)


    async def close(self):
        if self.browser:
            try:
                await self.browser.close()
                self.browser = None
            except Exception as e:
                print(f"Error closing browser: {e}")