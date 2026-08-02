"""Evidence recording tool.

The navigator model is unreliable at emitting a final JSON evidence block.
Instead it reliably calls tools. record_evidence() gives the model a direct,
deterministic way to persist each check's evidence into session state, which
the pipeline reads after the agent finishes.
"""

from typing import Any

from google.adk.tools.tool_context import ToolContext


def record_evidence(
    tool_context: ToolContext,
    check_id: str,
    status: str,
    note: str = "",
    screenshot_path: str = "",
) -> str:
    """Record the test result for one check into session state.

    Args:
        check_id: The check_id from the contract being tested.
        status: One of PASS, FAIL, BLOCKED.
        note: Short human-readable note about what was observed.
        screenshot_path: Path of the screenshot captured for this check ("" if none).
    """
    status = str(status).strip().upper()
    if status not in ("PASS", "FAIL", "BLOCKED"):
        status = "BLOCKED"
    evidence = tool_context.state.get("test_evidence") or []
    if not isinstance(evidence, list):
        evidence = []
    evidence.append({
        "check_id": check_id,
        "status": status,
        "note": note,
        "screenshot_path": screenshot_path,
    })
    tool_context.state["test_evidence"] = evidence
    return f"Recorded evidence for check '{check_id}' with status {status}."


def record_verdict(
    tool_context: ToolContext,
    check_id: str,
    verdict: str,
    reason: str = "",
    screen_id: str = "",
) -> str:
    """Record the judge's verdict for one check into session state.

    Args:
        check_id: The check_id from the contract being judged.
        verdict: One of PASS, FAIL, BLOCKED.
        reason: Explanation of why the check passed or failed.
        screen_id: The screen_id the check belongs to ("" if unknown).
    """
    verdict = str(verdict).strip().upper()
    if verdict not in ("PASS", "FAIL", "BLOCKED"):
        verdict = "BLOCKED"
    verdicts = tool_context.state.get("judge_verdicts") or []
    if not isinstance(verdicts, list):
        verdicts = []
    verdicts.append({
        "check_id": check_id,
        "verdict": verdict,
        "reason": reason,
        "screen_id": screen_id,
    })
    tool_context.state["judge_verdicts"] = verdicts
    return f"Recorded verdict for check '{check_id}' with status {verdict}."
