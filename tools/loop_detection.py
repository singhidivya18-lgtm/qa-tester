"""Loop detection tool for the QA orchestrator.

Tracks agent call history and detects when the orchestrator is stuck
in a loop (same agent called 3+ times consecutively, or same
agent+args pattern repeating).
"""

import json
from collections import Counter

MAX_CONSECUTIVE_CALLS = 3
MAX_TOTAL_CALLS_PER_AGENT = 8


def check_loop(call_history_json: str) -> dict:
    """Check if the orchestrator is stuck in a loop.

    Args:
        call_history_json: JSON string of recent agent calls, e.g.
            '["mapper", "navigator", "navigator", "navigator"]'

    Returns:
        dict with 'loop_detected' (bool), 'reason' (str), 'recommendation' (str)
    """
    try:
        history = json.loads(call_history_json)
    except (json.JSONDecodeError, TypeError):
        return {"loop_detected": False, "reason": "Could not parse call history", "recommendation": "Continue"}

    if not history:
        return {"loop_detected": False, "reason": "No calls recorded", "recommendation": "Continue"}

    # Check 1: Same agent called MAX_CONSECUTIVE_CALLS times in a row
    if len(history) >= MAX_CONSECUTIVE_CALLS:
        last_n = history[-MAX_CONSECUTIVE_CALLS:]
        if len(set(last_n)) == 1:
            return {
                "loop_detected": True,
                "reason": f"Agent '{last_n[0]}' called {MAX_CONSECUTIVE_CALLS} times consecutively",
                "recommendation": f"STOP calling {last_n[0]}. Skip to next state or report error to user.",
            }

    # Check 2: Same agent called too many times total
    counts = Counter(history)
    for agent, count in counts.items():
        if count >= MAX_TOTAL_CALLS_PER_AGENT:
            return {
                "loop_detected": True,
                "reason": f"Agent '{agent}' called {count} times total (limit: {MAX_TOTAL_CALLS_PER_AGENT})",
                "recommendation": f"STOP. Agent '{agent}' is not making progress. Move to next state or report error.",
            }

    # Check 3: Alternating pattern (A, B, A, B, ...)
    if len(history) >= 6:
        pattern = history[-6:]
        if pattern[0] == pattern[2] == pattern[4] and pattern[1] == pattern[3] == pattern[5] and pattern[0] != pattern[1]:
            return {
                "loop_detected": True,
                "reason": f"Alternating loop detected: '{pattern[0]}' ↔ '{pattern[1]}'",
                "recommendation": "STOP. Break the cycle by moving to the next state.",
            }

    return {"loop_detected": False, "reason": "No loop detected", "recommendation": "Continue"}
