"""Shared headless Chrome lifecycle for the QA pipeline.

The whole run uses ONE browser instance so that:
  1. Login state persists across all tested screens.
  2. Screenshots (connect_over_cdp) capture the real authenticated pages.

The Playwright MCP server connects to this browser via --cdp-endpoint, and the
take_screenshot tool connects the same way.
"""

import glob
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request

CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"

_proc = None
_data_dir = None


def _find_chrome() -> str:
    candidates = [
        os.environ.get("CHROME_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    for name in ("chrome", "msedge", "chromium", "google-chrome"):
        p = shutil.which(name)
        if p:
            return p
    pattern = os.path.join(
        os.path.expanduser("~"), "AppData", "Local",
        "ms-playwright", "chromium-*", "chrome-win", "chrome.exe",
    )
    matches = sorted(glob.glob(pattern))
    if matches:
        return matches[-1]
    raise FileNotFoundError("Chrome/Edge not found. Set CHROME_PATH env var.")


def is_browser_alive(timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(CDP_URL + "/json/version", timeout=timeout):
            return True
    except Exception:
        return False


def start_browser(port: int = CDP_PORT) -> None:
    """Launch a headless Chrome/Edge with a CDP debugging endpoint."""
    global _proc, _data_dir
    if is_browser_alive():
        return
    chrome = _find_chrome()
    _data_dir = tempfile.mkdtemp(prefix="qa_chrome_")
    cmd = [
        chrome,
        "--headless=new",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "about:blank",
    ]
    _proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if is_browser_alive():
            return
        time.sleep(0.5)
    raise TimeoutError("Chrome CDP endpoint did not start")


def stop_browser() -> None:
    global _proc, _data_dir
    if _proc is not None:
        try:
            _proc.terminate()
            _proc.wait(timeout=5)
        except Exception:
            try:
                _proc.kill()
            except Exception:
                pass
    _proc = None
    if _data_dir and os.path.isdir(_data_dir):
        shutil.rmtree(_data_dir, ignore_errors=True)
    _data_dir = None
