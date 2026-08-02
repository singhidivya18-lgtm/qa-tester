import os
import asyncio
import functools
from datetime import datetime
from .screenshot_tool import SCREENSHOT_DIR, ensure_screenshot_dir
from .browser_server import CDP_URL


def _find_page(browser):
    for context in browser.contexts:
        for page in context.pages:
            if page.url and page.url != "about:blank":
                return page
    for context in browser.contexts:
        if context.pages:
            return context.pages[0]
    return None


def _sync_screenshot(url: str, filepath: str) -> bool:
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(CDP_URL)
                page = _find_page(browser)
                if page is not None:
                    page.bring_to_front()
                    page.screenshot(path=filepath, full_page=True)
                    return True
            except Exception:
                pass
            with p.chromium.launch(headless=True) as browser:
                page = browser.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    pass
                page.screenshot(path=filepath, full_page=True)
            return True
    except Exception:
        return False


async def take_screenshot(url: str, screen_id: str, check_id: str) -> str:
    ensure_screenshot_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{screen_id}_{check_id}_{timestamp}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)

    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(
        None, functools.partial(_sync_screenshot, url, filepath)
    )

    if not success:
        return f"Screenshot failed for {url}"
    return filepath
