from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass(frozen=False)
class DOMBaseNode:
    """Base class for  DOM nodes."""
    js_id: int # The temporary ID assigned by the JavaScript snapshot
    is_visible: bool = False
    parent: Optional[DOMElementNode] = None # Set during Python reconstruction

@dataclass(frozen=False)
class DOMTextNode(DOMBaseNode):
    """Represents a text node in the  DOM."""
    text: str = ""
    type: str = 'TEXT_NODE'

    def __repr__(self) -> str:
        display_text = (self.text[:30] + '...') if len(self.text) > 30 else self.text
        return f'"{display_text}" (Visible: {self.is_visible})'

@dataclass(frozen=False)
class DOMElementNode(DOMBaseNode):
    """Represents an element node in the  DOM."""
    tag_name: str = ""
    xpath: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[DOMBaseNode] = field(default_factory=list)
    is_interactive: bool = False
    highlight_index: Optional[int] = None
    type: str = 'ELEMENT_NODE'

    def __repr__(self) -> str:
        tag_str = f'<{self.tag_name}'
        if self.highlight_index is not None:
            tag_str += f' [#{self.highlight_index}]'

        # Add a few important attributes if they exist
        repr_attrs = {}
        for key in ['id', 'class', 'name', 'type', 'role', 'aria-label', 'placeholder', 'value']:
             if key in self.attributes:
                 val = self.attributes[key]
                 # Limit length for display
                 repr_attrs[key] = (str(val)[:25] + '...') if len(str(val)) > 25 else str(val)

        for key, value in repr_attrs.items():
            tag_str += f' {key}="{value}"'

        extras = []
        if self.is_interactive: extras.append("Interactive")
        if not self.is_visible: extras.append("Hidden") # Note if hidden

        if extras:
            tag_str += f' ({", ".join(extras)})'

        if not self.children:
            tag_str += ' />'
        else:
            tag_str += '>'
        return tag_str

    def get_all_text_content(self, include_hidden: bool = False) -> str:
        """Recursively get text from this node and visible descendants."""
        parts = []
        for child in self.children:
            if isinstance(child, DOMTextNode):
                if child.is_visible or include_hidden:
                    cleaned_text = child.text.strip()
                    if cleaned_text:
                        parts.append(cleaned_text)
            elif isinstance(child, DOMElementNode):
                # Only recurse into visible elements unless include_hidden is True
                 if child.is_visible or include_hidden:
                    parts.append(child.get_all_text_content(include_hidden=include_hidden))

        full_text = ' '.join(filter(None, parts))
        return ' '.join(full_text.split()) # Normalize whitespace

    def to__string(self) -> str:
        """Generate the  string representation for the LLM."""
        formatted_text = []

        def process_node(node: DOMBaseNode, is_inside_highlighted: bool = False):
            if not node.is_visible: # Skip entirely non-visible branches
                 return

            if isinstance(node, DOMElementNode):
                # Process this node if it's highlighted
                if node.highlight_index is not None:
                    text = node.get_all_text_content(include_hidden=False) # Get only visible text within
                    attrs_to_include = ['aria-label', 'placeholder', 'alt', 'value', 'name', 'title', 'type']
                    attrs_str_parts = []
                    for key in attrs_to_include:
                         # Use get() for safer access
                        attr_val = node.attributes.get(key, '').strip()
                        if attr_val and attr_val != text: # Avoid duplicating text content in attributes
                            attrs_str_parts.append(f'{key}="{attr_val}"')
                    attrs_str = ' '.join(attrs_str_parts)

                    line = f"[{node.highlight_index}] <{node.tag_name}"
                    if attrs_str:
                       line += f" {attrs_str}"
                    # Include text only if it's meaningful
                    if text and len(text) > 0 and len(text) < 100: # Avoid very long text blocks in brackets
                        line += f">{text}</{node.tag_name}>"
                    else:
                        line += " />"
                    formatted_text.append(line)
                    # Mark children as inside highlighted
                    for child in node.children:
                         process_node(child, is_inside_highlighted=True)
                else:
                    # If not highlighted, just process children
                     for child in node.children:
                        process_node(child, is_inside_highlighted)

            elif isinstance(node, DOMTextNode):
                # Include text only if visible and *not* inside an already highlighted element
                cleaned_text = node.text.strip()
                if cleaned_text and not is_inside_highlighted:
                    formatted_text.append(cleaned_text)

        process_node(self)
        result = '\n'.join(line.strip() for line in formatted_text if line.strip())
        result = '\n'.join(filter(None, result.splitlines()))
        return result.strip()


SelectorMap = Dict[int, DOMElementNode]

@dataclass
class DOMState:
    """Holds the  DOM tree, selector map, URL, and title."""
    root_node: Optional[DOMElementNode] = None
    selector_map: SelectorMap = field(default_factory=dict)
    url: str = ""
    title: str = ""

    def get_string(self) -> str:
        if not self.root_node:
            return "Page DOM is empty or could not be processed."
        return self.root_node.to__string()

    def get_element_by_index(self, index: int) -> Optional[DOMElementNode]:
        return self.selector_map.get(index)