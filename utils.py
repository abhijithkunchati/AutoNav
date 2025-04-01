from __future__ import annotations

import json
from typing import List, Optional, Dict, Any
from browser import Browser
import importlib.resources

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)



async def create_observation_message(
    browser: Browser, 
    step_number: int,
    max_steps: int,
    ) -> HumanMessage:

    url = await browser.get_current_url()
    dom_state = await browser.get__dom_state()
    elements = dom_state.get_string()
    #elements = await browser.get_content()
    elements_text = f'[Start of page]\n{elements}\n[End of page]'
    step_info_description = f'Current step: {step_number + 1}/{max_steps}'
    state_description = f"""
[Task history memory ends]
[Current state starts here]
The following is one-time information - if you need to remember it mention it in your response.
Specify the reasoning for toolcalls in your response content. 
Current url: {url}
HTML of the page:
{elements_text}
{step_info_description}
"""
    screenshot = await browser.get_screenshot()
    return HumanMessage(
				content=[
					{'type': 'text', 'text': state_description},
					{
						'type': 'image_url',
						'image_url': {'url': f'data:image/png;base64,{screenshot}'},
					},
				]
			)

def load_prompt() -> str:
    """Load the prompt template from the markdown file."""
    try:
        with open('prompt.md', 'r') as f:
            return f.read()
    except Exception as e:
        raise RuntimeError(f'Failed to load system prompt template: {e}')
