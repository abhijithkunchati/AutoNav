import asyncio
import logging
from typing import Optional
from flags import CHROME_ARGS
import re 

from playwright.async_api import (
    Playwright,
    async_playwright,
    Browser as PlaywrightBrowser,
    BrowserContext as PlaywrightContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
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

    async def start(self) -> None:
        async with self._start_lock:
            if self._is_initialized:
                logger.warning("Browser is already initialized.")
                return
            logger.info("Starting browser...")
            try:
                self.playwright = await async_playwright().start()
                chrome_args = list(CHROME_ARGS)
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
                logger.info("Browser started successfully.")
            except PlaywrightError as e:
                logger.error(f"Failed to start browser: {e}")
                await self.close()
                raise BrowserError(f"Failed to initialize browser: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error starting browser: {e}")
                await self.close()
                raise BrowserError(f"Unexpected error initializing browser: {e}") from e

    async def close(self) -> None:
        if not self._is_initialized and not self.playwright and not self.browser:
            logger.info("Browser not initialized or already closed.")
            return
        logger.info("Closing browser...")
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

    def _ensure_page(self) -> Page:
        if not self._is_initialized:
             raise BrowserError("Browser is not initialized. Call start() first.")
        if not self.page or self.page.is_closed():
            raise BrowserError("Browser page is not available or closed.")
        return self.page

    async def navigate_to_url(self, url: str, wait_until: str = "domcontentloaded", timeout_ms: int = 30000) -> None:
        page = self._ensure_page()
        logger.info(f"Navigating to: {url}")
        try:
            response = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            status = response.status if response else 'unknown'
            logger.info(f"Navigation to {url} successful (status: {status}).")
            if response and not response.ok:
                 logger.warning(f"Navigation to {url} resulted in non-OK status: {status}")
        except PlaywrightTimeoutError:
            logger.error(f"Timeout navigating to {url}")
            raise BrowserError(f"Timeout error when navigating to {url}")
        except PlaywrightError as e:
            logger.error(f"Error navigating to {url}: {e}")
            raise BrowserError(f"Failed to navigate to {url}: {e}") from e

    async def click(self, selector: str, timeout_ms: int = 10000) -> None:
        page = self._ensure_page()
        logger.info(f"Attempting to click element: {selector}")
        try:
            locator = page.locator(selector)
            await locator.wait_for(state="visible", timeout=timeout_ms / 2)
            await locator.wait_for(state="enabled", timeout=timeout_ms / 2)
            await locator.click(timeout=timeout_ms)
            logger.info(f"Clicked element: {selector}")
        except PlaywrightTimeoutError:
            logger.error(f"Timeout waiting for or clicking element: {selector}")
            try:
                box = await page.locator(selector).bounding_box(timeout=1000)
                logger.error(f"Element {selector} found but timed out on click/wait. Bounding box: {box}")
            except Exception:
                 logger.error(f"Element {selector} likely not present or visible.")
            raise BrowserError(f"Timeout error interacting with element: {selector}")
        except PlaywrightError as e:
            logger.error(f"Error clicking element {selector}: {e}")
            raise BrowserError(f"Failed to click element {selector}: {e}") from e

    async def type(self, selector: str, text: str, delay_ms: int = 30, timeout_ms: int = 10000) -> None:
        page = self._ensure_page()
        logger.info(f"Attempting to type into element: {selector}")
        try:
            locator = page.locator(selector)
            await locator.wait_for(state="visible", timeout=timeout_ms)
            await locator.fill("", timeout=timeout_ms / 2)
            await locator.type(text, delay=delay_ms, timeout=timeout_ms)
            logger.info(f"Typed '{text[:20]}...' into element: {selector}")
        except PlaywrightTimeoutError:
            logger.error(f"Timeout waiting for or typing into element: {selector}")
            raise BrowserError(f"Timeout error interacting with element: {selector}")
        except PlaywrightError as e:
            logger.error(f"Error typing into element {selector}: {e}")
            raise BrowserError(f"Failed to type into element {selector}: {e}") from e

    async def get_current_url(self) -> str:
        page = self._ensure_page()
        return page.url

    async def get_title(self) -> str:
        page = self._ensure_page()
        try:
            return await page.title()
        except PlaywrightError as e:
            logger.error(f"Error getting page title: {e}")
            raise BrowserError(f"Failed to get page title: {e}") from e

    async def get_content(self, format: str = "text", max_length: int = 10000) -> str:
        page = self._ensure_page()
        logger.info(f"Getting page content (format: {format})")
        try:
            if format == "html":
                content = await page.content()
                logger.info(f"Retrieved HTML content (length: {len(content)})")
                return content
            elif format == "text":
                text_content = await page.inner_text('body')
                cleaned_text = re.sub(r'\s+', ' ', text_content).strip()
                logger.info(f"Retrieved and cleaned text content (original length: {len(text_content)}, cleaned length: {len(cleaned_text)})")
                if len(cleaned_text) > max_length:
                    logger.warning(f"Truncating text content from {len(cleaned_text)} to {max_length} characters.")
                    return cleaned_text[:max_length] + "... [Content Truncated]"
                return cleaned_text
            else:
                raise ValueError("Invalid format specified. Use 'text' or 'html'.")
        except PlaywrightError as e:
            logger.error(f"Error getting page content (format: {format}): {e}")
            raise BrowserError(f"Failed to get page content: {e}") from e
        
    async def wait_for_load_state(self, state: str = "domcontentloaded", timeout_ms: int = 30000) -> None:
        page = self._ensure_page()
        logger.info(f"Waiting for load state: {state}")
        try:
            await page.wait_for_load_state(state, timeout=timeout_ms)
            logger.info(f"Load state '{state}' reached.")
        except PlaywrightTimeoutError:
            logger.error(f"Timeout waiting for load state: {state}")
            raise BrowserError(f"Timeout waiting for load state: {state}")
        except PlaywrightError as e:
            logger.error(f"Error waiting for load state {state}: {e}")
            raise BrowserError(f"Failed to wait for load state {state}: {e}") from e

    async def navigate_back(self, wait_until: str = "domcontentloaded", timeout_ms: int = 10000) -> None:
        page = self._ensure_page()
        logger.info("Navigating back")
        try:
            await page.go_back(wait_until=wait_until, timeout=timeout_ms)
        except PlaywrightError as e:
            logger.warning(f"Could not navigate back (may be at start of history): {e}")

    async def navigate_forward(self, wait_until: str = "domcontentloaded", timeout_ms: int = 10000) -> None:
        page = self._ensure_page()
        logger.info("Navigating forward")
        try:
            await page.go_forward(wait_until=wait_until, timeout=timeout_ms)
        except PlaywrightError as e:
            logger.warning(f"Could not navigate forward (may be at end of history): {e}")

    async def refresh(self, wait_until: str = "domcontentloaded", timeout_ms: int = 30000) -> None:
        page = self._ensure_page()
        logger.info("Refreshing page")
        try:
            await page.reload(wait_until=wait_until, timeout=timeout_ms)
        except PlaywrightError as e:
            logger.error(f"Error refreshing page: {e}")
            raise BrowserError(f"Failed to refresh page: {e}") from e

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
