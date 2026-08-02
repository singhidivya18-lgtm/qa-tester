import os
import base64
import json
import re
from datetime import datetime


SCREENSHOT_DIR = os.path.join(os.path.expanduser("~"), ".react_qa_screenshots")


def ensure_screenshot_dir():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def save_screenshot(screenshot_b64: str, screen_id: str, check_id: str) -> str:
    ensure_screenshot_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{screen_id}_{check_id}_{timestamp}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    img_data = base64.b64decode(screenshot_b64)
    with open(filepath, "wb") as f:
        f.write(img_data)
    return filepath


def extract_and_save_screenshots(evidence, screen_id: str) -> int:
    text = json.dumps(evidence) if not isinstance(evidence, str) else evidence
    pattern = r"data:image/png;base64,([A-Za-z0-9+/=]+)"
    matches = re.findall(pattern, text)
    count = 0
    for idx, b64 in enumerate(matches):
        try:
            save_screenshot(b64, screen_id, f"screenshot_{idx}")
            count += 1
        except Exception:
            pass
    return count


def get_screenshot_dir() -> str:
    ensure_screenshot_dir()
    return SCREENSHOT_DIR
