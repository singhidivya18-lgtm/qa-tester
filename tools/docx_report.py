"""DOCX report generator tool.

Converts the QA report text into a professionally formatted .docx file.
Supports embedding screenshots from the testing run.
"""

import os
import json
from datetime import datetime

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from .screenshot_tool import SCREENSHOT_DIR, get_screenshot_dir


def generate_docx_report(report_text, all_screen_results_json="[]", site_url="", screenshots_dir=None, output_dir=None):
    """Generate a formatted .docx file from report text with embedded screenshots.

    Args:
        report_text: The full markdown/text report from the report agent.
        all_screen_results_json: JSON string of all screen results with verdicts.
        site_url: The tested site URL.
        screenshots_dir: Directory containing screenshot PNGs (defaults to SCREENSHOT_DIR).
        output_dir: Directory to save the .docx file (defaults to pipeline root).

    Returns:
        str: Path to the generated .docx file.
    """
    if screenshots_dir is None:
        screenshots_dir = SCREENSHOT_DIR
    if output_dir is None:
        output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        screen_results = json.loads(all_screen_results_json) if all_screen_results_json else []
    except (json.JSONDecodeError, TypeError):
        screen_results = []

    doc = Document()
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(11)

    title = doc.add_heading("React QA Test Report", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    timestamp_paragraph = doc.add_paragraph()
    timestamp_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = timestamp_paragraph.add_run(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(128, 128, 128)

    if site_url:
        url_paragraph = doc.add_paragraph()
        url_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        url_run = url_paragraph.add_run(f"Site: {site_url}")
        url_run.font.size = Pt(10)
        url_run.font.color.rgb = RGBColor(100, 100, 100)

    doc.add_page_break()

    lines = report_text.split("\n")
    in_code_block = False
    code_lines = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                if code_lines:
                    code_text = "\n".join(code_lines)
                    p = doc.add_paragraph()
                    run = p.add_run(code_text)
                    run.font.name = "Consolas"
                    run.font.size = Pt(9)
                code_lines = []
            in_code_block = not in_code_block
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if not stripped:
            continue

        if stripped.startswith("# "):
            doc.add_heading(stripped[2:].strip(), level=1)
        elif stripped.startswith("## "):
            doc.add_heading(stripped[3:].strip(), level=2)
        elif stripped.startswith("### "):
            doc.add_heading(stripped[4:].strip(), level=3)
        elif stripped in ("---", "***", "___"):
            doc.add_paragraph("_" * 50)
        elif stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:].strip()
            text = _clean_markdown(text)
            doc.add_paragraph(text, style="List Bullet")
        elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in (".", ")"):
            text = stripped[2:].strip()
            text = _clean_markdown(text)
            doc.add_paragraph(text, style="List Number")
        elif "|" in stripped and stripped.startswith("|"):
            text = _clean_markdown(stripped)
            text = text.replace("|", "  •  ")
            p = doc.add_paragraph(text)
            for run in p.runs:
                run.font.size = Pt(9)
        else:
            text = _clean_markdown(stripped)
            p = doc.add_paragraph(text)
            _apply_inline_formatting(p, stripped)

    doc.add_page_break()
    doc.add_heading("Screenshots", level=1)
    _add_screenshots_section(doc, screen_results, screenshots_dir)

    os.makedirs(output_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"qa_report_{timestamp_str}.docx"
    filepath = os.path.join(output_dir, filename)
    doc.save(filepath)

    return filepath


def _add_screenshots_section(doc, screen_results, screenshots_dir):
    """Embed screenshots for each screen in the document."""
    if not os.path.isdir(screenshots_dir):
        doc.add_paragraph("No screenshots directory found — screenshots were not saved during testing.")
        return

    screenshot_files = sorted(
        [f for f in os.listdir(screenshots_dir) if f.endswith(".png")],
        key=lambda f: os.path.getmtime(os.path.join(screenshots_dir, f)),
    )

    if not screenshot_files:
        doc.add_paragraph("No screenshots were captured during testing.")
        return

    screen_ids_in_results = set()
    for r in screen_results:
        if isinstance(r, dict):
            screen_ids_in_results.add(r.get("screen_id", ""))

    grouped = {}
    for sf in screenshot_files:
        parts = sf.replace(".png", "").split("_")
        if len(parts) >= 2:
            sid = parts[0] + "_" + parts[1]
            grouped.setdefault(sid, []).append(sf)
        else:
            grouped.setdefault("other", []).append(sf)

    for screen_id, files in sorted(grouped.items()):
        if screen_id != "other":
            heading_text = f"Screen: {screen_id}"
        else:
            heading_text = "General screenshots"
        doc.add_heading(heading_text, level=2)

        for fname in files[:4]:
            fpath = os.path.join(screenshots_dir, fname)
            if os.path.exists(fpath):
                try:
                    p = doc.add_paragraph()
                    p_run = p.add_run(f"{fname}")
                    p_run.font.size = Pt(8)
                    p_run.font.color.rgb = RGBColor(100, 100, 100)
                    doc.add_picture(fpath, width=Inches(5.5))
                except Exception:
                    doc.add_paragraph(f"[Could not embed: {fname}]")
            if len(files) > 4:
                remaining = len(files) - 4
                doc.add_paragraph(f"(+ {remaining} more screenshots for this screen)")
                break


def _clean_markdown(text):
    import re
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text


def _apply_inline_formatting(paragraph, text):
    import re
    paragraph.clear()
    parts = re.split(r"(\*\*.*?\*\*|\*.*?\*|`.*?`)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("*") and part.endswith("*"):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        else:
            paragraph.add_run(part)


