from __future__ import annotations
from auto_nav.browser import Browser
import importlib.resources
from langchain_core.messages import (
    HumanMessage,
)



async def create_observation_message(
    browser: Browser, 
    step_number: int,
    max_steps: int,
    ) -> HumanMessage:

    url = await browser.get_current_url()
    elements = await browser.update_dom()
    elements_text = f'[Start of page]\n{elements}\n[End of page]'
    step_info_description = f'Current step: {step_number}/{max_steps}'
    state_description = f"""
[Task history memory ends]
[Current state starts here]
The following is one-time information - if you need to remember it mention it in your response (as instructed in the beginning)
An image is provided, use it to understand the context, the bounding boxes around the buttons have the same indexes as the interactive elements.
Current url: {url}
Interactive elements of the page:
{elements_text}
{step_info_description}
"""
    screenshot = await browser.take_screenshot()
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
        with importlib.resources.files('auto_nav').joinpath('prompt.md').open('r') as f:
            return f.read()
    except Exception as e:
        raise RuntimeError(f'Failed to load system prompt template: {e}')
