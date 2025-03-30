() => {
    // --- Configuration ---
    const INTERACTIVE_TAGS = new Set([
      'a', 'button', 'input', 'textarea', 'select', 'option', 'details', 'summary', 'label'
    ]);
    const INTERACTIVE_ROLES = new Set([
      'button', 'link', 'menuitem', 'tab', 'checkbox', 'radio', 'textbox', 'listbox', 'option', 'combobox', 'slider', 'spinbutton', 'treeitem'
    ]);
    // Attributes to collect for elements
    const INCLUDED_ATTRIBUTES = new Set([
      'id', 'class', 'name', 'type', 'role', 'aria-label', 'aria-labelledby', 'aria-describedby',
      'placeholder', 'value', 'title', 'alt', 'href', 'for', 'disabled', 'readonly', 'checked', 'selected'
    ]);
    // Tags to generally skip processing children of (unless interactive itself)
    const SKIP_CHILDREN_TAGS = new Set([
        "svg", "script", "style", "link", "meta", "noscript", "template", "img", "canvas", "video", "audio"
    ]);
  
    // --- State ---
    const nodeMap = {};
    let nextId = 0;
    let highlightIndexCounter = 1; // Start highlight indices from 1
  
    // --- Helper Functions ---
  
    function getXPathSegment(element) {
      const tagName = element.tagName.toLowerCase();
      let index = 1;
      let sibling = element.previousElementSibling;
      while (sibling) {
        if (sibling.tagName.toLowerCase() === tagName) {
          index++;
        }
        sibling = sibling.previousElementSibling;
      }
      // Check if element is the only one of its tag type
      let nextSibling = element.nextElementSibling;
      let isOnlyOfType = true;
      while(nextSibling) {
          if (nextSibling.tagName.toLowerCase() === tagName) {
              isOnlyOfType = false;
              break;
          }
          nextSibling = nextSibling.nextElementSibling;
      }
       // Don't add index [1] if it's the only one or the first one
      return (index === 1 && isOnlyOfType) ? tagName : `${tagName}[${index}]`;
    }
  
    /**
     * Basic visibility check using offset dimensions and computed style.
     */
    function isElementVisible(element) {
      if (!element.checkVisibility) { // Basic fallback for older envs/iframes
          const style = window.getComputedStyle(element);
          return (
              element.offsetWidth > 0 &&
              element.offsetHeight > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none" &&
              style.opacity !== "0"
          );
      }
      // Use modern checkVisibility API where available (more accurate for opacity, clipping etc)
      try {
          return element.checkVisibility({
            checkOpacity: true,      // Check computed opacity
            checkVisibilityCSS: true // Check display and visibility styles
          });
      } catch(e) {
          // Fallback if checkVisibility fails for some reason
          const style = window.getComputedStyle(element);
           return (
              element.offsetWidth > 0 &&
              element.offsetHeight > 0 &&
              style.visibility !== "hidden" &&
              style.display !== "none" &&
              style.opacity !== "0"
          );
      }
    }
  
   /**
    *  check for interactivity.
    */
   function isElementInteractive(element) {
      const tagName = element.tagName.toLowerCase();
  
      // 1. Check natively interactive tags
      if (INTERACTIVE_TAGS.has(tagName)) {
        // Check if disabled
        if (element.hasAttribute('disabled') || element.disabled) {
          return false;
        }
         // Special case: <option> inside disabled <select> or <optgroup>
         if (tagName === 'option') {
             const parentSelect = element.closest('select');
             const parentOptgroup = element.closest('optgroup');
             if ((parentSelect && parentSelect.disabled) || (parentOptgroup && parentOptgroup.disabled)) {
                 return false;
             }
         }
        return true;
      }
  
      // 2. Check interactive ARIA roles
      const role = element.getAttribute('role');
      if (role && INTERACTIVE_ROLES.has(role.toLowerCase())) {
        // Check aria-disabled
        const ariaDisabled = element.getAttribute('aria-disabled');
        if (ariaDisabled && ariaDisabled.toLowerCase() === 'true') {
          return false;
        }
        return true;
      }
  
      // 3. Check tabindex (explicitly focusable)
      const tabIndex = element.getAttribute('tabindex');
      if (tabIndex && parseInt(tabIndex, 10) >= 0) {
        return true;
      }
  
      // 4. Check contentEditable
      if (element.isContentEditable || element.getAttribute('contenteditable') === 'true') {
          return true;
      }
  
      // 5. Check for click handlers (basic check)
      if (element.hasAttribute('onclick') || (typeof element.onclick === 'function')) {
        return true;
      }
  
      // 6. Check cursor style (heuristic)
      try {
        const style = window.getComputedStyle(element);
        if (style.cursor === 'pointer') {
          return true;
        }
      } catch(e) { /* ignore errors getting style */ }
  
  
      return false;
    }
  
  
    // --- Core Recursive Function ---
  
    /**
     * Processes a DOM node and its children, adding data to the nodeMap.
     * Returns the ID assigned to the node in the map, or null if skipped.
     */
    function buildNodeData(node, parentXPath) {
      const nodeType = node.nodeType;
  
      // 1. Skip nodes we don't care about (comments, doctype, etc.) or hidden scripts/styles
      if (![Node.ELEMENT_NODE, Node.TEXT_NODE].includes(nodeType) ||
          (nodeType === Node.ELEMENT_NODE && ['script', 'style', 'meta', 'noscript', 'link'].includes(node.tagName.toLowerCase())) ||
          node.id === '__playwright_runner__' // Skip playwright internal elements
         ) {
        return null;
      }
  
      const currentId = nextId++;
      let nodeData = {};
  
      // 2. Process Text Nodes
      if (nodeType === Node.TEXT_NODE) {
        const text = node.textContent?.trim() || '';
        if (!text) return null; // Skip empty/whitespace text nodes
  
        // Basic visibility check based on parent
        const parentVisible = node.parentElement ? isElementVisible(node.parentElement) : false;
  
        nodeData = {
          id: currentId,
          type: 'TEXT_NODE',
          text: text,
          isVisible: parentVisible, // Approx visibility based on parent
          children: [], // Text nodes have no children in this model
          xpath: null // Text nodes don't get an XPath segment
        };
      }
      // 3. Process Element Nodes
      else if (nodeType === Node.ELEMENT_NODE) {
        const tagName = node.tagName.toLowerCase();
        const isVisible = isElementVisible(node);
  
        // Skip non-visible elements entirely (unless they are structural parents like body/html)
        // if (!isVisible && !['body', 'html'].includes(tagName)) {
        //     return null; // Option: Aggressively prune non-visible branches
        // }
  
        const isInteractive = isVisible ? isElementInteractive(node) : false; // Only check interactivity if visible
        const currentXPathSegment = getXPathSegment(node);
        const currentXPath = parentXPath ? `${parentXPath}/${currentXPathSegment}` : currentXPathSegment;
  
        nodeData = {
          id: currentId,
          type: 'ELEMENT_NODE',
          tagName: tagName,
          xpath: currentXPath,
          attributes: {},
          children: [],
          isVisible: isVisible,
          isInteractive: isInteractive,
          highlightIndex: null,
        };
  
        // Collect specified attributes
        for (const attr of node.attributes) {
          if (INCLUDED_ATTRIBUTES.has(attr.name)) {
            nodeData.attributes[attr.name] = attr.value;
          }
        }
        // Special handling for input/textarea/select value
        if (['input', 'textarea', 'select'].includes(tagName)) {
           if (node.value !== undefined && node.value !== null && nodeData.attributes.value === undefined) { // Don't overwrite existing 'value' attribute
               nodeData.attributes.value = String(node.value); // Ensure it's a string
           }
        }
         // Assign highlight index if applicable
        if (isVisible && isInteractive) {
          nodeData.highlightIndex = highlightIndexCounter++;
        }
  
        // Recursively process children (unless tag suggests skipping)
        if (!SKIP_CHILDREN_TAGS.has(tagName)) {
            for (const child of node.childNodes) {
              const childId = buildNodeData(child, currentXPath);
              if (childId !== null) {
                nodeData.children.push(childId);
              }
            }
        }
      } else {
          return null; // Should not happen based on initial check
      }
  
      // Store in map and return ID
      nodeMap[currentId] = nodeData;
      return currentId;
    }
  
    // --- Execution ---
    const rootElement = document.body || document.documentElement;
    if (!rootElement) {
        return { rootId: null, map: {}};
    }
  
    // Clear state for fresh run
    nextId = 0;
    highlightIndexCounter = 1;
  
    // Start building from the root element
    const rootId = buildNodeData(rootElement, ''); // Start with empty parent XPath
  
    return { rootId: rootId, map: nodeMap };
  };