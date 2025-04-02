import asyncio
import base64
import logging
from typing import Optional
import time
from dom_utils import get_elements, dom_to_string, DOM

from playwright.async_api import (
    Playwright,
    async_playwright,
    Browser as PlaywrightBrowser,
    BrowserContext as PlaywrightContext,
    Page,
    Error as PlaywrightError
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BrowserError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        logger.error(f"BrowserError: {message}")

class Browser:

    def __init__(self, user_agent: Optional[str] = None):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[PlaywrightBrowser] = None
        self.context: Optional[PlaywrightContext] = None
        self.page: Optional[Page] = None
        self.user_agent = user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
        self._is_initialized = False
        self._start_lock = asyncio.Lock()
        self.dom: Optional[DOM] = None

    async def start(self) -> None:
        async with self._start_lock:
            if self._is_initialized:
                logger.warning("Browser is already initialized.")
                return
            logger.info("Starting browser...")
            try:
                self.playwright = await async_playwright().start()
                chrome_args = [
				'--disable-blink-features=AutomationControlled',
				'--no-sandbox',
				'--window-size=1280,1024',
				'--disable-extensions',
				'--disable-infobars',
				'--disable-background-timer-throttling',
				'--disable-popup-blocking',
				'--disable-backgrounding-occluded-windows',
				'--disable-renderer-backgrounding',
			]
                self.browser = await self.playwright.chromium.launch(
                    headless=False,
                    args=chrome_args,
                    handle_sigterm=False,
                    handle_sigint=False,
                )
                self.context = await self.browser.new_context(
                    user_agent=self.user_agent,
                    viewport=None, 
                    java_script_enabled=True,
                )
                self.page = await self.context.new_page()
                await self.page.goto("about:blank")
                self._is_initialized = True
                self.MINIMUM_WAIT_TIME = 2
                self.dom = await get_elements(self.page)
                logger.info("Browser started successfully.")

            except Exception as e:
                logger.error(f"Unexpected error starting browser: {e}")
                await self.close()
                raise BrowserError(f"Unexpected error initializing browser: {e}") from e

    async def close(self) -> None:
        if not self._is_initialized and not self.playwright and not self.browser:
            logger.info("Browser not initialized or already closed.")
            return
        logger.info("Closing browser...")
        await self.playwright.stop()
        if self.page and not self.page.is_closed():
            try:
                await self.page.close()
            except PlaywrightError as e:
                logger.warning(f"Error closing page: {e}")
        if self.context:
            try:
                await self.context.close()
            except PlaywrightError as e:
                logger.warning(f"Error closing context: {e}")
        if self.browser and self.browser.is_connected():
            try:
                await self.browser.close()
            except PlaywrightError as e:
                logger.warning(f"Error closing browser: {e}")
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        self._is_initialized = False
        logger.info("Browser closed.")

    def get_page(self) -> Page:
        if not self.page or self.page.is_closed():
            raise BrowserError("Browser page is not available or closed.")
        return self.page
    
    async def wait_for_page_load(self):
        """
		Ensures page is fully loaded before continuing.
		Waits for either document.readyState to be complete or minimum WAIT_TIME, whichever is longer.
		"""
        page = self.get_page()
        start_time = time.time()
        try:
            await page.wait_for_load_state('load', timeout=5000)
        except Exception:
            pass
        elapsed = time.time() - start_time
        remaining = max(self.MINIMUM_WAIT_TIME - elapsed, 0)
        logger.debug(
			f'--Page loaded in {elapsed:.2f} seconds, waiting for additional {remaining:.2f} seconds'
		)
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def navigate_to_url(self, url: str) -> None:
        page = self.get_page()
        await page.goto(url)
        await self.wait_for_page_load()

    async def get_current_url(self) -> str:
        page = self.get_page()
        return page.url

    async def get_title(self) -> str:
        page = self.get_page()
        try:
            return await page.title()
        except PlaywrightError as e:
            logger.error(f"Error getting page title: {e}")
            raise BrowserError(f"Failed to get page title: {e}") from e

    async def navigate_back(self, wait_until: str = "domcontentloaded", timeout_ms: int = 10000) -> None:
        page = self.get_page()
        try:
            await page.go_back(wait_until=wait_until, timeout=timeout_ms)
        except PlaywrightError as e:
            logger.warning(f"Could not navigate back (may be at start of history): {e}")

    async def navigate_forward(self, wait_until: str = "domcontentloaded", timeout_ms: int = 10000) -> None:
        page = self.get_page()
        try:
            await page.go_forward(wait_until=wait_until, timeout=timeout_ms)
        except PlaywrightError as e:
            logger.warning(f"Could not navigate forward (may be at end of history): {e}")

    async def refresh(self, wait_until: str = "domcontentloaded", timeout_ms: int = 30000) -> None:
        page = self.get_page()
        logger.info("Refreshing page")
        try:
            await page.reload(wait_until=wait_until, timeout=timeout_ms)
        except PlaywrightError as e:
            logger.error(f"Error refreshing page: {e}")
            raise BrowserError(f"Failed to refresh page: {e}") from e
        
    async def update_dom(self) -> str:
        """
        Updates dom and returns string
        """
        try:
            page = self.get_page()
            self.dom = await get_elements(page) 
            return dom_to_string(self.dom.elements)
        except Exception as e:
            logger.error(f"Error getting  DOM state: {e}", exc_info=True)
            raise BrowserError(f"Failed to get  DOM state: {e}") from e
        
    async def click_element_by_index(self, index: int, timeout_ms: int = 10000):
        if index not in self.dom.element_map:
            raise Exception(
                f'Element with index {index} does not exist - retry or use alternative actions'
            )
        xpath = self.dom.element_map[index]
        await self._click_element_by_xpath(xpath)

    async def type_element_by_index(self, index: int, text: str) -> None:
        if index not in self.dom.element_map:
                raise Exception(
					f'Element with index {index} does not exist - retry or use alternative actions'
				)
        xpath = self.dom.element_map[index]
        await self._input_text_by_xpath(xpath, text)
    
    async def _input_text_by_xpath(self, xpath: str, text: str):
        page = self.get_page()
        try:
            element = await page.wait_for_selector(f'xpath={xpath}', timeout=10000, state='visible')

            if element is None:
                raise Exception(f'Element with xpath: {xpath} not found')
            await element.scroll_into_view_if_needed()
            await element.fill('')
            await element.type(text)
            await self.wait_for_page_load()

        except Exception as e:
            raise Exception(
				f'Failed to input text into element with xpath: {xpath}. Error: {str(e)}'
			)

    async def _click_element_by_xpath(self, xpath: str):
        page = self.get_page()
        try:
            element = await page.wait_for_selector(f'xpath={xpath}', timeout=10000, state='visible')
            if element is None:
                raise Exception(f'Element with xpath: {xpath} not found')
            await element.scroll_into_view_if_needed()
            try:
                await element.click()
                await self.wait_for_page_load()
                return
            except Exception:
                pass
            try:
                await page.evaluate('(el) => el.click()', element)
                await self.wait_for_page_load()
                return
            except Exception as e:
                raise Exception(f'Failed to click element: {str(e)}')

        except Exception as e:
            raise Exception(f'Failed to click element with xpath: {xpath}. Error: {str(e)}')

    async def take_screenshot(
        self,  full_page: bool = False
    ) -> str:
        """
        Returns a base64 encoded screenshot of the current page.
        """
        try: 
            await self.wait_for_page_load()
            page = self.get_page()
            await self.highlight_elements_in_page()
            screenshot = await page.screenshot(full_page=full_page, animations='disabled')
            screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
            await self.remove_highlights()
            return screenshot_b64
        except Exception as e:
            raise Exception(f'Error While taking Screenshot: {str(e)}')

    async def highlight_elements_in_page(self):
        page = self.get_page()
        await self.remove_highlights()
        script = """
        const highlights = {
        """
        try: 
        # Build the highlights object with all selectors and indices
            if(not self.dom and not self.dom.element_map):
                raise Exception(f'Error when getting element map for highlighting')
            for index, selector in self.dom.element_map.items():
                # Adjusting the JavaScript code to accept variables
                script += f'"{index}": "{selector}",\n'
            script += """
            };
            
            for (const [index, selector] of Object.entries(highlights)) {
                const el = document.evaluate(selector, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (!el) continue;  // Skip if element not found
                el.style.outline = "2px solid red";
                el.setAttribute('browser-user-highlight-id', 'playwright-highlight');
                
                const label = document.createElement("div");
                label.className = 'playwright-highlight-label';
                label.style.position = "fixed";
                label.style.background = "red";
                label.style.color = "white";
                label.style.padding = "2px 6px";
                label.style.borderRadius = "10px";
                label.style.fontSize = "12px";
                label.style.zIndex = "9999999";
                label.textContent = index;
                const rect = el.getBoundingClientRect();
                label.style.top = (rect.top - 20) + "px";
                label.style.left = rect.left + "px";
                document.body.appendChild(label);
            }
            """

            await page.evaluate(script)
        except Exception as e:
            raise Exception(f'Error While Highlighting: {str(e)}')

    async def remove_highlights(self):
        try: 
            page = self.get_page()
            await page.evaluate(
                """
                // Remove all highlight outlines
                const highlightedElements = document.querySelectorAll('[browser-user-highlight-id="playwright-highlight"]');
                highlightedElements.forEach(el => {
                    el.style.outline = '';
                    el.removeAttribute('browser-user-highlight-id');
                });
                

                // Remove all labels
                const labels = document.querySelectorAll('.playwright-highlight-label');
                labels.forEach(label => label.remove());
                """
            )
        except Exception as e: 
            raise Exception(f'Error While removing Highlights: {str(e)}')


    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
