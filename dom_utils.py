from playwright.async_api import Page
from bs4 import BeautifulSoup, NavigableString, PageElement, Tag
from typing import Optional
from typing import Dict, List
from pydantic import BaseModel
import json

class ElementCheckResult(BaseModel):
	xpath: str
	isVisible: bool
	isTopElement: bool

class TextCheckResult(BaseModel):
	xpath: str
	isVisible: bool

class BatchCheckResults(BaseModel):
	elements: Dict[str, ElementCheckResult]
	texts: Dict[str, TextCheckResult]

class DomContentItem(BaseModel):
	index: int
	text: str
	is_text_only: bool
	depth: int

class DOM(BaseModel):
	elements: list[DomContentItem]
	element_map: dict[int, str]

async def get_elements(page:Page) -> DOM:
    html = await page.content()
    soup = BeautifulSoup(html, 'html.parser')

    output_items: list[DomContentItem] = []
    element_map: dict[int, str] = {}
    current_index = 0
    interactive_elements: dict[str, tuple[Tag, int]] = {}  # xpath -> (element, order)
    text_nodes: dict[str, tuple[NavigableString, int]] = {}  # xpath -> (text_node, order)
    xpath_order_counter = 0  # Track order of appearance

    dom_queue: list[tuple[PageElement, list, Optional[str]]] = (
        [(element, [], None) for element in reversed(list(soup.body.children))]
        if soup.body
        else []
    )

    # First pass: collect all elements that need checking
    while dom_queue:
        element, path_indices, parent_xpath = dom_queue.pop()

        if isinstance(element, Tag):
            if not _is_element_accepted(element):
                element.decompose()
                continue

            siblings = (
                list(element.parent.find_all(element.name, recursive=False))
                if element.parent
                else []
            )
            sibling_index = siblings.index(element) + 1 if siblings else 1
            current_path = path_indices + [(element.name, sibling_index)]
            element_xpath = '//' + '/'.join(f'{tag}[{idx}]' for tag, idx in current_path)

            # Add children to queue with their path information
            for child in reversed(list(element.children)):
                dom_queue.append((child, current_path, element_xpath))  # Pass parent's xpath

            # Collect interactive elements with their order
            if (
                _is_interactive_element(element) or _is_leaf_element(element)
            ) and _is_active(element):
                interactive_elements[element_xpath] = (element, xpath_order_counter)
                xpath_order_counter += 1

        elif isinstance(element, NavigableString) and element.strip():
            if element.parent and element.parent not in [e[0] for e in dom_queue]:
                if parent_xpath:
                    text_nodes[parent_xpath] = (element, xpath_order_counter)
                    xpath_order_counter += 1

    # Batch check all elements
    element_results = await _batch_check_elements(page, interactive_elements)
    text_results = await _batch_check_texts(page, text_nodes)

    # Create ordered results
    ordered_results: list[
        tuple[int, str, bool, str, int, bool]
    ] = []  # [(order, xpath, is_clickable, content, depth, is_text_only), ...]

    # Process interactive elements
    for xpath, (element, order) in interactive_elements.items():
        if xpath in element_results.elements:
            result = element_results.elements[xpath]
            if result.isVisible and result.isTopElement:
                text_content = _extract_text_from_all_children(element)
                tag_name = element.name
                attributes = _get_essential_attributes(element)
                output_string = f"<{tag_name}{' ' + attributes if attributes else ''}>{text_content}</{tag_name}>"

                depth = len(xpath.split('/')) - 2
                ordered_results.append((order, xpath, True, output_string, depth, False))

    # Process text nodes
    for xpath, (text_node, order) in text_nodes.items():
        if xpath in text_results.texts:
            result = text_results.texts[xpath]
            if result.isVisible:
                text_content = _cap_text_length(text_node.strip())
                if text_content:
                    depth = len(xpath.split('/')) - 2
                    ordered_results.append((order, xpath, False, text_content, depth, True))

    # Sort by original order
    ordered_results.sort(key=lambda x: x[0])

    # Build final output maintaining order
    for i, (_, xpath, is_clickable, content, depth, is_text_only) in enumerate(ordered_results):
        output_items.append(
            DomContentItem(
                index=i,
                text=content,
                # clickable=is_clickable,
                depth=depth,
                is_text_only=is_text_only,
            )
        )
        if not is_text_only:
            element_map[i] = xpath

    return DOM(elements=output_items, element_map=element_map)

async def _batch_check_elements(
    page:Page, elements: dict[str, tuple[Tag, int]]
) -> BatchCheckResults:
    if not elements:
        return BatchCheckResults(elements={}, texts={})

    check_script = """
        (function() {
            const results = {};
            const elements = %s;
            
            for (const [xpath, elementData] of Object.entries(elements)) {
                const element = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (!element) continue;
                
                const isVisible = element.offsetWidth > 0 && 
                                element.offsetHeight > 0 && 
                                window.getComputedStyle(element).visibility !== 'hidden' &&
                                window.getComputedStyle(element).display !== 'none';
                
                if (!isVisible) continue;
                
                const rect = element.getBoundingClientRect();
                const points = [
                    {x: rect.left + rect.width * 0.25, y: rect.top + rect.height * 0.25},
                    {x: rect.left + rect.width * 0.75, y: rect.top + rect.height * 0.25},
                    {x: rect.left + rect.width * 0.25, y: rect.top + rect.height * 0.75},
                    {x: rect.left + rect.width * 0.75, y: rect.top + rect.height * 0.75},
                    {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2}
                ];
                
                const isTopElement = points.some(point => {
                    const topEl = document.elementFromPoint(point.x, point.y);
                    let current = topEl;
                    while (current && current !== document.body) {
                        if (current === element) return true;
                        current = current.parentElement;
                    }
                    return false;
                });
                
                if (isTopElement) {
                    results[xpath] = {
                        xpath: xpath,
                        isVisible: true,
                        isTopElement: true
                    };
                }
            }
            return results;
        })();
    """ % json.dumps({xpath: {} for xpath in elements.keys()})

    try:
        await page.wait_for_load_state('load')
        results = await page.evaluate(check_script)
        return BatchCheckResults(
            elements={xpath: ElementCheckResult(**data) for xpath, data in results.items()},
            texts={},
        )
    except Exception as e:
        print('Error in batch element check: %s', e)
        return BatchCheckResults(elements={}, texts={})

async def _batch_check_texts(
    page:Page, texts: dict[str, tuple[NavigableString, int]]
) -> BatchCheckResults:
    if not texts:
        return BatchCheckResults(elements={}, texts={})

    check_script = """
        (function() {
            const results = {};
            const texts = %s;
            
            for (const [xpath, textData] of Object.entries(texts)) {
                const parent = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (!parent) continue;
                
                try {
                    const range = document.createRange();
                    const textNode = parent.childNodes[textData.index];
                    range.selectNodeContents(textNode);
                    const rect = range.getBoundingClientRect();
                    
                    const isVisible = (
                        rect.width !== 0 && 
                        rect.height !== 0 && 
                        rect.top >= 0 && 
                        rect.top <= window.innerHeight &&
                        parent.checkVisibility({
                            checkOpacity: true,
                            checkVisibilityCSS: true
                        })
                    );
                    
                    if (isVisible) {
                        results[xpath] = {
                            xpath: xpath,
                            isVisible: true
                        };
                    }
                } catch (e) {
                    continue;
                }
            }
            return results;
        })();
    """ % json.dumps(
        {
            xpath: {'index': list(text_node[0].parent.children).index(text_node[0])}
            for xpath, text_node in texts.items()
            if text_node[0].parent
        }
    )

    try:
        results = await page.evaluate(check_script)
        return BatchCheckResults(
            elements={},
            texts={xpath: TextCheckResult(**data) for xpath, data in results.items()},
        )
    except Exception as e:
        print('Error in batch text check: %s', e)
        return BatchCheckResults(elements={}, texts={})

def _cap_text_length(text: str, max_length: int = 250) -> str:
    if len(text) > max_length:
        half_length = max_length // 2
        return text[:half_length] + '...' + text[-half_length:]
    return text

def _extract_text_from_all_children(element: Tag) -> str:
    text_content = ''
    for child in element.descendants:
        if isinstance(child, NavigableString):
            current_child_text = child.strip()
        else:
            current_child_text = child.get_text(strip=True)

        text_content += '\n' + current_child_text

    return _cap_text_length(text_content.strip()) or ''

def _is_interactive_element(element: Tag) -> bool:
    """Check if element is interactive based on tag name and attributes."""
    interactive_elements = {
        'a',
        'button',
        'details',
        'embed',
        'input',
        'label',
        'menu',
        'menuitem',
        'object',
        'select',
        'textarea',
        'summary',
    }

    interactive_roles = {
        'button',
        'menu',
        'menuitem',
        'link',
        'checkbox',
        'radio',
        'slider',
        'tab',
        'tabpanel',
        'textbox',
        'combobox',
        'grid',
        'listbox',
        'option',
        'progressbar',
        'scrollbar',
        'searchbox',
        'switch',
        'tree',
        'treeitem',
        'spinbutton',
        'tooltip',
        'menuitemcheckbox',
        'menuitemradio',
    }

    return (
        element.name in interactive_elements
        or element.get('role') in interactive_roles
        or element.get('aria-role') in interactive_roles
        or element.get('tabindex') == '0'
    )

def _is_leaf_element(element: Tag) -> bool:
    """Check if element is a leaf element."""
    if not element.get_text(strip=True):
        return False

    if not list(element.children):
        return True

    # Check for simple text-only elements
    children = list(element.children)
    if len(children) == 1 and isinstance(children[0], str):
        return True

    return False

def _is_element_accepted(element: Tag) -> bool:
    """Check if element is accepted based on tag name and special cases."""
    leaf_element_deny_list = {'svg', 'iframe', 'script', 'style', 'link', 'meta'}

    # First check if it's in deny list
    if element.name in leaf_element_deny_list:
        return False

    return element.name not in leaf_element_deny_list

def _get_essential_attributes(element: Tag) -> str:
    """
    Collects essential attributes from an element.
    Args:
        element: The BeautifulSoup PageElement
    Returns:
        A string of formatted essential attributes
    """
    essential_attributes = [
        'id',
        'class',
        'href',
        'src',
        'readonly',
        'disabled',
        'checked',
        'selected',
        'role',
        'type',  # Important for inputs, buttons
        'name',  # Important for form elements
        'value',  # Current value of form elements
        'placeholder',  # Helpful for understanding input purpose
        'title',  # Additional descriptive text
        'alt',  # Alternative text for images
        'for',  # Important for label associations
        'autocomplete',  # Form field behavior
    ]

    # Collect essential attributes that have values
    attrs = []
    for attr in essential_attributes:
        if attr in element.attrs:
            element_attr = element[attr]
            if isinstance(element_attr, str):
                element_attr = element_attr
            elif isinstance(element_attr, (list, tuple)):
                element_attr = ' '.join(str(v) for v in element_attr)

            attrs.append(f'{attr}="{_cap_text_length(element_attr, 25)}"')

    state_attributes_prefixes = (
        'aria-',
        'data-',
    )

    # Collect data- attributes
    for attr in element.attrs:
        if attr.startswith(state_attributes_prefixes):
            attrs.append(f'{attr}="{element[attr]}"')

    return ' '.join(attrs)

def _is_active(element: Tag) -> bool:
    """Check if element is active (not disabled)."""
    return not (
        element.get('disabled') is not None
        or element.get('hidden') is not None
        or element.get('aria-disabled') == 'true'
    )

def dom_to_string(dom_elements: list[DomContentItem] ) -> str:
		"""Convert the processed DOM content to HTML."""
		string = ''
		for element in dom_elements:
			element_depth = '\t' * element.depth * 1
			if element.is_text_only:
				string += f'_[:]{element_depth}{element.text}\n'
			else:
				string += f'{element.index}[:]{element_depth}{element.text}\n'
		return string