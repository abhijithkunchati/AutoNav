import asyncio
import gc
import logging
import time
from importlib import resources # Use importlib.resources for package data
from typing import Dict, List, Optional, Tuple, Any

from playwright.async_api import Page

# Import the new view classes
from parse_dom.dom_view import (
    DOMBaseNode,
    DOMElementNode,
    DOMTextNode,
    DOMState,
    SelectorMap,
)

logger = logging.getLogger(__name__)

class DomService:
    def __init__(self, page: Page):
        self.page = page
        try:
            # Load JS code once during initialization
            self._get_dom_snapshot_js = resources.read_text(__package__, 'get_dom_snapshot.js')
            logger.info("get_dom_snapshot.js loaded successfully.")
        except FileNotFoundError:
            logger.error("CRITICAL: get_dom_snapshot.js not found in package.")
            raise
        except Exception as e:
             logger.error(f"CRITICAL: Error loading get_dom_snapshot.js: {e}")
             raise

    async def _fetch_dom_snapshot_from_browser(self) -> Optional[Dict[str, Any]]:
        """Executes the JS snapshot script in the browser."""
        if self.page.is_closed():
            logger.warning("Page is closed, cannot fetch DOM snapshot.")
            return None
        if not self._get_dom_snapshot_js:
             logger.error("JS snapshot code is not loaded.")
             return None

        logger.debug("Executing get_dom_snapshot.js in browser...")
        start_time = time.time()
        try:
            # Ensure page is somewhat stable before evaluation
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)

            # Execute the script
            js_result = await self.page.evaluate(self._get_dom_snapshot_js)

            elapsed = time.time() - start_time
            node_count = len(js_result.get('map', {}))
            logger.debug(f"JS DOM snapshot finished in {elapsed:.3f}s. Nodes processed: {node_count}")

            if not js_result or 'map' not in js_result or 'rootId' not in js_result:
                logger.error("JS snapshot result is missing 'map' or 'rootId'.")
                return None

            return js_result
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Unexpected error executing JS snapshot after {elapsed:.3f}s: {e}", exc_info=True)
            return None

    def _construct__tree(
        self,
        js_result: Dict[str, Any]
    ) -> Tuple[Optional[DOMElementNode], SelectorMap]:
        """Reconstructs the Python DOM tree from the JS snapshot map."""
        if not js_result:
            return None, {}

        js_map = js_result.get('map')
        root_id = js_result.get('rootId')

        if not js_map or root_id is None:
             logger.warning("JS map or rootId is missing, cannot construct tree.")
             return None, {}

        py_node_map: Dict[int, DOMBaseNode] = {}
        selector_map: SelectorMap = {}
        root_node: Optional[DOMElementNode] = None

        logger.debug(f"Reconstructing tree from {len(js_map)} JS nodes...")
        start_time = time.time()

        # First pass: Create all Python node objects
        for js_id_str, node_data in js_map.items():
            js_id = int(js_id_str)
            node_type = node_data.get('type')

            if node_type == 'TEXT_NODE':
                py_node = DOMTextNode(
                    js_id=js_id,
                    text=node_data.get('text', ''),
                    is_visible=node_data.get('isVisible', False)
                )
            elif node_type == 'ELEMENT_NODE':
                py_node = DOMElementNode(
                    js_id=js_id,
                    tag_name=node_data.get('tagName', 'unknown'),
                    xpath=node_data.get('xpath', ''),
                    attributes=node_data.get('attributes', {}),
                    is_visible=node_data.get('isVisible', False),
                    is_interactive=node_data.get('isInteractive', False),
                    highlight_index=node_data.get('highlightIndex') # Can be None
                )
                if py_node.highlight_index is not None:
                    selector_map[py_node.highlight_index] = py_node
            else:
                logger.warning(f"Unknown node type '{node_type}' for js_id {js_id}. Skipping.")
                continue

            py_node_map[js_id] = py_node

        # Second pass: Link children and parents
        for js_id, py_node in py_node_map.items():
            if isinstance(py_node, DOMElementNode):
                node_data = js_map.get(str(js_id)) # Get original JS data again
                if node_data:
                    child_ids = node_data.get('children', [])
                    for child_js_id in child_ids:
                        child_py_node = py_node_map.get(child_js_id)
                        if child_py_node:
                            child_py_node.parent = py_node # Set parent link
                            py_node.children.append(child_py_node)
                        else:
                             logger.warning(f"Child node with js_id {child_js_id} not found in py_node_map (parent js_id {js_id}).")


        # Find the root node
        if root_id in py_node_map:
            root_node_candidate = py_node_map[root_id]
            if isinstance(root_node_candidate, DOMElementNode):
                root_node = root_node_candidate
            else:
                 logger.error(f"Root node (js_id {root_id}) is not an ElementNode in Python map.")
        else:
             logger.error(f"Root node with js_id {root_id} not found in Python map.")

        elapsed = time.time() - start_time
        logger.debug(f"Python tree reconstruction finished in {elapsed:.3f}s.")

        # Clean up large intermediate structures
        del py_node_map
        del js_map
        gc.collect()

        return root_node, selector_map

    async def get__dom_state(self) -> DOMState:
        """
        Builds a  DOM tree and selector map using JS execution.
        """
        logger.info("Building  DOM state via JS snapshot...")
        page_url = ""
        page_title = ""
        root_node = None
        selector_map = {}

        try:
            if self.page.is_closed():
                 logger.warning("Page is closed, cannot build DOM state.")
                 return DOMState() # Return empty state

            # Get URL and Title first
            try:
                page_url = self.page.url
                page_title = await self.page.title()
            except Exception as e:
                 logger.warning(f"Could not get page URL/title: {e}")
                 page_url = "unknown"
                 page_title = "unknown"


            # Fetch the snapshot from the browser
            js_result = await self._fetch_dom_snapshot_from_browser()

            if js_result:
                # Reconstruct the Python tree
                root_node, selector_map = self._construct__tree(js_result)
            else:
                 logger.error("Failed to fetch DOM snapshot from browser.")

        except Exception as e:
            logger.error(f"Error building  DOM state: {e}", exc_info=True)
            # Return potentially partial state or empty state on error

        highlight_count = len(selector_map)
        logger.info(f"Finished building  DOM state. Found {highlight_count} interactive elements.")

        return DOMState(
            root_node=root_node,
            selector_map=selector_map,
            url=page_url,
            title=page_title
        )