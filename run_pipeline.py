"""Deterministic QA Pipeline Runner.

Runs the full QA testing pipeline WITHOUT an LLM orchestrator.
Each step is executed in sequence with Python control flow — no prompt following,
no loop detection needed, no state machine drift.

Usage:
    python -m react_qa_agent.run_pipeline --repo-url <url> --site-url <url> [--test-file <path>]
"""

import argparse
import asyncio
import json
import sys
import os
import time
from datetime import datetime

from google.adk.workflow import Workflow, FunctionNode, START
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.genai import types

from .config import LLM_MODEL, TEST_FILE_PATH, SITE_EMAIL, SITE_PASSWORD, SITE_PASSWORD_FALLBACK, MAX_CHECKS_PER_SCREEN, HEARTBEAT_INTERVAL_SECONDS
from .prompts.mapper import MAPPER_PROMPT
from .prompts.contract import CONTRACT_PROMPT
from .prompts.navigator import NAVIGATOR_PROMPT
from .prompts.report import REPORT_PROMPT
from .tools.repo_analyzer import clone_repo, grep_routes, list_src
from .tools.route_parser import parse_route_config
from .tools.component_reader import read_components
from .tools.yaml_tools import read_yaml_standards, get_rules_as_json
from .tools.docx_report import generate_docx_report
from .tools.screenshot_tool import SCREENSHOT_DIR, extract_and_save_screenshots
from .tools.browser_server import start_browser, stop_browser, CDP_URL

MAX_SCREENS = 10


def build_mapper_agent():
    from google.adk.agents import Agent
    return Agent(
        name="mapper", model=LLM_MODEL, instruction=MAPPER_PROMPT,
        tools=[clone_repo, grep_routes, list_src, parse_route_config, read_components],
        output_key="screen_map", mode="chat", timeout=120,
    )

def build_contract_agent():
    from google.adk.agents import Agent
    return Agent(
        name="contract_generator", model=LLM_MODEL, instruction=CONTRACT_PROMPT,
        tools=[read_yaml_standards, get_rules_as_json],
        output_key="contracts", mode="chat", timeout=180,
    )

def build_navigator_agent():
    from google.adk.agents import Agent
    from google.adk.tools.mcp_tool import McpToolset
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from mcp import StdioServerParameters
    from .tools.playwright_screenshot import take_screenshot
    from .tools.evidence_tools import record_evidence
    return Agent(
        name="navigator", model=LLM_MODEL, instruction=NAVIGATOR_PROMPT,
        tools=[
            take_screenshot,
            record_evidence,
            McpToolset(
                connection_params=StdioConnectionParams(
                    server_params=StdioServerParameters(
                        command="npx",
                        args=["-y", "@playwright/mcp@latest",
                              "--cdp-endpoint", CDP_URL,
                              "--image-responses", "omit"],
                    ),
                    timeout=90,
                ),
                tool_filter=[
                    "browser_navigate", "browser_snapshot", "browser_click",
                    "browser_type",
                    "browser_network_requests",
                    "browser_file_upload",
                    "browser_handle_dialog", "browser_press_key",
                    "browser_navigate_back", "browser_wait_for",
                ],
            )
        ],
        # NOTE: no output_key here — output_key would overwrite the state key
        # "test_evidence" with the agent's final text response, clobbering the
        # evidence list that record_evidence() persists during the run.
        mode="chat", timeout=1800,
    )

def build_report_agent():
    from google.adk.agents import Agent
    return Agent(
        name="report_generator", model=LLM_MODEL, instruction=REPORT_PROMPT,
        tools=[generate_docx_report],
        output_key="final_report", mode="chat", timeout=600,
    )


def _maybe_print_live(agent_name, event, elapsed):
    """Print live progress as tool calls stream in, so the console never looks
    frozen during a long agent run (screen-level results only print at the end)."""
    if not event.content or not event.content.parts:
        return
    for part in event.content.parts:
        fc = getattr(part, "function_call", None)
        if fc is None:
            continue
        name = fc.name
        args = fc.args if isinstance(fc.args, dict) else {}
        if name == "record_evidence":
            print(f"  [LIVE] {agent_name} | record: {args.get('check_id', '?')} -> {args.get('status', '?')} (t={elapsed:.0f}s)")
        elif name == "take_screenshot":
            print(f"  [LIVE] {agent_name} | screenshot: {args.get('check_id', '?')} (t={elapsed:.0f}s)")


async def run_agent(runner, session_id, user_id, message, agent_name="agent", timeout_seconds=600):
    """Run a single agent with a timeout and return the events."""
    content = types.Content(
        role="user", parts=[types.Part.from_text(text=message)]
    )
    events = []
    start = time.monotonic()
    last_event_ts = {"ts": start}

    # Idle heartbeat: fire only when nothing has arrived for a while, so the
    # console confirms liveness during long silent stretches. A background task
    # avoids interrupting ADK's event generator with wait_for/cancellation.
    async def _idle_watcher():
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            if time.monotonic() - last_event_ts["ts"] > HEARTBEAT_INTERVAL_SECONDS:
                print(f"  [HEARTBEAT] {agent_name} still working "
                      f"(t={time.monotonic() - start:.0f}s, {len(events)} events, "
                      f"{count_tool_calls(events)} tool calls)...")

    watcher = asyncio.create_task(_idle_watcher())
    try:
        async def _run():
            async for event in runner.run_async(
                user_id=user_id, session_id=session_id, new_message=content
            ):
                events.append(event)
                last_event_ts["ts"] = time.monotonic()
                _maybe_print_live(agent_name, event, last_event_ts["ts"] - start)
        await asyncio.wait_for(_run(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        print(f"  [TIMEOUT] {agent_name} exceeded {timeout_seconds}s limit. Using partial results.")
    except Exception as e:
        err_str = str(e)
        if len(err_str) > 200:
            err_str = err_str[:200] + "..."
        print(f"  [ERROR] {agent_name} failed: {err_str}")
    finally:
        watcher.cancel()
    elapsed = time.monotonic() - start
    print(f"  [TIME] {agent_name} took {elapsed:.1f}s ({len(events)} events, {count_tool_calls(events)} tool calls)")
    return events


def count_tool_calls(events):
    """Count function/tool calls made by the agent across all events."""
    n = 0
    for event in events:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if getattr(part, "function_call", None) is not None:
                n += 1
            elif getattr(part, "tool_call", None) is not None:
                n += 1
    return n


def extract_text(events):
    """Extract text content from events."""
    texts = []
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    texts.append(part.text)
    return "\n".join(texts)


def extract_json_from_events(events):
    """Try to parse a JSON value from the agent's event text output."""
    text = extract_text(events).strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def normalize_json_output(value):
    """Convert a state/event value that may be a JSON string into a Python object."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    return value


def get_state_value(session, key):
    """Get a value from session state."""
    if session.state and key in session.state:
        return session.state[key]
    return None


async def get_fresh_session_state(session_service, session_id, user_id):
    """Re-fetch a session from the service and return its state dict.

    InMemorySessionService returns a COPY of the session; the runner updates
    its internal storage copy, so a previously-created session object holds
    stale state. Always re-fetch after running an agent.
    """
    fetched = await session_service.get_session(
        app_name="qa_pipeline", user_id=user_id, session_id=session_id
    )
    if fetched is None:
        return {}
    return fetched.state or {}


def screenshots_as_evidence(screen_id):
    """Build evidence items from screenshot files taken for a screen.

    The navigator takes screenshots named '{screen_id}_{check_id}_{timestamp}.png'
    for every check. If it fails to record evidence in state, the screenshots
    themselves prove which checks were exercised — the judge can still evaluate
    the checks, and the screenshots get included in the DOCX report.
    """
    if not os.path.isdir(SCREENSHOT_DIR):
        return []
    evidence = []
    prefix = f"{screen_id}_"
    for name in sorted(os.listdir(SCREENSHOT_DIR)):
        if not name.startswith(prefix) or not name.endswith(".png"):
            continue
        stem = name[len(prefix):-4]
        check_id = stem.rsplit("_", 1)[0]
        evidence.append({
            "check_id": check_id,
            "status": "BLOCKED",
            "note": "Navigator did not record a verdict, but a screenshot was captured for this check.",
            "screenshot_path": os.path.join(SCREENSHOT_DIR, name),
        })
    return evidence


def evidence_to_verdicts(evidence, screen_id):
    """Convert navigator-recorded evidence into the verdict shape used by the report.

    The judge agent was dropped: the navigator's own record_evidence() calls
    (PASS/FAIL/BLOCKED per check) are now the final verdicts, so no second
    LLM pass is needed.
    """
    verdicts = []
    if not isinstance(evidence, list):
        return verdicts
    for item in evidence:
        if not isinstance(item, dict):
            continue
        verdicts.append({
            "check_id": item.get("check_id", ""),
            "verdict": item.get("status", "BLOCKED"),
            "reason": item.get("note", ""),
            "screen_id": screen_id,
            "screenshot_path": item.get("screenshot_path", ""),
        })
    return verdicts


def render_per_check_lines(all_screen_results):
    """Deterministically render one line per check — the AI-readable report body.

    The full per-check detail already exists in all_screen_results (verdict +
    reason + screenshot path). Rendering it here never depends on the LLM, so
    the TXT report is always complete even if the report model misbehaves.
    """
    total_checks = 0
    passed = failed = blocked = 0
    lines = []
    for r in all_screen_results:
        screen_id = r.get("screen_id", "?")
        route = r.get("route", "/")
        for v in r.get("verdicts", []):
            if not isinstance(v, dict):
                continue
            verdict = v.get("verdict", "BLOCKED")
            detail = (v.get("reason") or "").strip().replace("\n", " ")
            screenshot = v.get("screenshot_path", "")
            lines.append(
                f"screen: {screen_id} | route: {route} | check: {v.get('check_id', '?')} "
                f"| verdict: {verdict} | detail: {detail or 'no detail recorded'} "
                f"| screenshot: {screenshot}"
            )
            total_checks += 1
            if verdict == "PASS":
                passed += 1
            elif verdict == "FAIL":
                failed += 1
            else:
                blocked += 1

    return lines, total_checks, passed, failed, blocked


async def pipeline_main(repo_url, site_url, test_file_path=None, max_screens=MAX_SCREENS):
    """Run the full QA pipeline deterministically."""
    # Windows consoles default to a legacy codec that crashes on emoji/unicode.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()
    user_id = "pipeline_user"

    print("=" * 60)
    print("QA PIPELINE - Deterministic Execution")
    print("=" * 60)
    print(f"Repo: {repo_url or 'none (black-box, site URL only)'}")
    print(f"Site: {site_url}")
    print(f"Test file: {test_file_path or 'None'}")
    print(f"Max screens: {max_screens}")
    print(f"Max checks per screen: {MAX_CHECKS_PER_SCREEN}")
    print()
    pipeline_start = time.monotonic()

    # Clear stale screenshots from previous runs
    if os.path.isdir(SCREENSHOT_DIR):
        for f in os.listdir(SCREENSHOT_DIR):
            fp = os.path.join(SCREENSHOT_DIR, f)
            try:
                if os.path.isfile(fp):
                    os.remove(fp)
            except OSError:
                pass

    # Create session with initial state
    session = await session_service.create_session(
        app_name="qa_pipeline", user_id=user_id,
        state={
            "repo_url": repo_url,
            "site_url": site_url,
            "test_file_path": test_file_path or TEST_FILE_PATH or "",
            "phase": "setup",
            "current_screen_index": 0,
            "all_screen_results": [],
        }
    )
    session_id = session.id

    # ─── STEP 1: MAPPER (deterministic, no LLM) ─────────────────────────
    print("[1/4] MAPPER: Analyzing repository...")
    from .tools.deterministic_mapper import deterministic_mapper
    try:
        screen_map = deterministic_mapper(repo_url, site_url)
    except Exception as e:
        print(f"  [FAIL] Mapper failed: {e}")
        return

    if not screen_map or not screen_map.get("screens"):
        print("  [FAIL] Mapper did not find any screens.")
        return

    # Parse screen map
    if isinstance(screen_map, str):
        try:
            screen_map = json.loads(screen_map)
        except json.JSONDecodeError:
            print("  [FAIL] Mapper output is not valid JSON.")
            return

    screens = screen_map.get("screens", [])
    print(f"  Found {len(screens)} screens.")
    for s in screens[:5]:
        print(f"    - {s.get('screen_id', '?')}: {s.get('route_path', '?')} ({s.get('component_name', '?')})")
    if len(screens) > 5:
        print(f"    ... and {len(screens) - 5} more")

    # ─── STEP 2: CONTRACTS (deterministic, no LLM) ──────────────────────
    print("\n[2/4] CONTRACT GENERATOR: Creating test contracts...")
    from .tools.deterministic_contract import deterministic_contract_generator
    try:
        contracts = deterministic_contract_generator(screen_map)
    except Exception as e:
        print(f"  [FAIL] Contract generator failed: {e}")
        return

    if not contracts:
        print("  [FAIL] Contract generator did not produce contracts.")
        return

    num_contracts = len(contracts)
    total_checks = sum(len(c.get("checks", [])) for c in contracts)
    print(f"  Generated contracts for {num_contracts} screens ({total_checks} total checks).")

    # ─── STEP 3: NAVIGATE + JUDGE (per screen) ─────────────────────────
    all_screen_results = []
    num_to_test = min(num_contracts, max_screens)
    print(f"\n[3/4] NAVIGATOR + JUDGE: Testing {num_to_test} screens...")

    # ONE shared browser + ONE navigator/judge instance reused for all screens.
    # The MCP browser session (and thus login state) persists across screens.
    start_browser()
    nav = build_navigator_agent()
    nav_runner = Runner(
        agent=nav, app_name="qa_pipeline",
        session_service=session_service, artifact_service=artifact_service,
    )

    try:
        # ─── LOGIN STEP (once, so login state persists for all screens) ──
        # Uses a fresh session so the shared MCP browser keeps its login state
        # without the conversation history accumulating context.
        print("  [LOGIN] Authenticating with the site...")
        login_session = await session_service.create_session(
            app_name="qa_pipeline", user_id=user_id,
            state={"site_url": site_url, "phase": "login"},
        )
        login_sid = login_session.id
        login_msg = (
            f"Log in to {site_url} using the provided credentials, then verify you are logged in.\n"
            f"Site login email: {SITE_EMAIL}\n"
            f"Site login password: {SITE_PASSWORD}\n"
            f"If the password {SITE_PASSWORD} fails, try this fallback password: {SITE_PASSWORD_FALLBACK}\n\n"
            f"Steps:\n"
            f"1. Navigate to {site_url}\n"
            f"2. If a login form appears, fill in the credentials and submit.\n"
            f"3. Wait for the page to load after login.\n"
            f"4. Verify login succeeded (you should no longer be on the login page).\n"
            f"5. Take a screenshot to record the logged-in state.\n"
            f"6. Call record_evidence(check_id='login_verification', status='PASS' if logged in else 'FAIL', "
            f"note='describe what you see', screenshot_path='<the screenshot path>')."
        )
        login_events = await run_agent(nav_runner, login_sid, user_id, login_msg,
                                       "navigator_login", timeout_seconds=420)
        login_state = await get_fresh_session_state(session_service, login_sid, user_id)
        login_evidence = login_state.get("test_evidence")
        if not login_evidence:
            login_evidence = extract_json_from_events(login_events)
        if login_evidence:
            print("  [LOGIN] Login step completed.")
        else:
            print("  [LOGIN] Login step produced no confirmation — continuing anyway.")

        for i in range(num_to_test):
            contract_entry = contracts[i] if i < len(contracts) else None
            if not contract_entry:
                continue

            screen_id = contract_entry.get("screen_id", f"screen_{i}")
            route = contract_entry.get("route", "/")
            all_checks = contract_entry.get("checks", [])
            # Trim to the most severe checks (contracts are pre-sorted critical-first)
            checks = all_checks[:MAX_CHECKS_PER_SCREEN]
            print(f"\n  --- Screen {i}: {screen_id} ({route}) ---")
            print(f"  Checks: {len(checks)} of {len(all_checks)} (trimmed to {MAX_CHECKS_PER_SCREEN})")

            # Fresh session per screen — only the current screen's contract is
            # passed so context stays small and never exceeds the model limit.
            screen_session = await session_service.create_session(
                app_name="qa_pipeline", user_id=user_id,
                state={
                    "repo_url": repo_url, "site_url": site_url,
                    "phase": "test_screen", "current_screen_index": i,
                },
            )
            screen_sid = screen_session.id
            current_contract = [{**contract_entry, "checks": checks}]

            nav_msg = (
                f"Test screen {i} at {site_url}{route}\n"
                f"Contracts: {json.dumps(current_contract)}\n"
                f"Current screen index: 0\n"
                f"You are ALREADY logged in to the site as {SITE_EMAIL} — the browser "
                f"session is shared and authenticated. Do NOT log in again unless the "
                f"page clearly shows a login form; if it does, log in once with:\n"
                f"Site login email: {SITE_EMAIL}\n"
                f"Site login password: {SITE_PASSWORD}\n"
                f"If the password {SITE_PASSWORD} fails, try this fallback password: {SITE_PASSWORD_FALLBACK}\n"
                f"Test file path: {test_file_path or ''}"
            )
            events = await run_agent(nav_runner, screen_sid, user_id, nav_msg,
                                     f"navigator_screen_{i}", timeout_seconds=1800)
            screen_state = await get_fresh_session_state(session_service, screen_sid, user_id)
            test_evidence = screen_state.get("test_evidence")
            if not test_evidence:
                test_evidence = extract_json_from_events(events)
            test_evidence = normalize_json_output(test_evidence)
            if isinstance(test_evidence, dict):
                test_evidence = test_evidence.get("evidence") or test_evidence.get("test_evidence") or []
            if not test_evidence:
                test_evidence = screenshots_as_evidence(screen_id)

            # Verdicts come straight from the navigator's recorded evidence —
            # no judge agent, no second LLM pass.
            if not test_evidence:
                print(f"  [WARN] Navigator produced no evidence for {screen_id}.")
                print("  [SKIP] No evidence — marking all checks BLOCKED.")
                verdicts = [{
                    "check_id": c.get("check_id", ""), "verdict": "BLOCKED",
                    "reason": "No evidence recorded by navigator", "screen_id": screen_id,
                } for c in checks]
            else:
                verdicts = evidence_to_verdicts(test_evidence, screen_id)
                if not verdicts:
                    print(f"  [WARN] No usable evidence entries for {screen_id} — marking all checks BLOCKED.")
                    verdicts = [{
                        "check_id": c.get("check_id", ""), "verdict": "BLOCKED",
                        "reason": "Evidence entries were not usable", "screen_id": screen_id,
                    } for c in checks]

            passed = sum(1 for v in verdicts if isinstance(v, dict) and v.get("verdict") == "PASS")
            failed = sum(1 for v in verdicts if isinstance(v, dict) and v.get("verdict") == "FAIL")
            blocked = sum(1 for v in verdicts if isinstance(v, dict) and v.get("verdict") == "BLOCKED")
            if not verdicts:
                overall = "BLOCKED"
            elif failed > 0:
                overall = "FAIL"
            elif passed == 0:
                overall = "BLOCKED"
            elif blocked > 0:
                overall = "PASS_WITH_CAVEATS"
            else:
                overall = "PASS"
            print(f"  Verdicts: PASS={passed}, FAIL={failed}, BLOCKED={blocked}, Overall={overall}")

            all_screen_results.append({
                "screen_id": screen_id,
                "route": route,
                "verdicts": verdicts,
                "overall": overall,
            })

            await asyncio.sleep(3)

        # ─── REGISTRATION TEST (optional) ───────────────────────────────
        # Runs AFTER the screen loop: the shared browser must stay logged in
        # as the main account for all screens. Signup flows typically log the
        # browser into the NEW account — if run mid-pipeline, every screen
        # after it would land on the login page. At the end, it's harmless.
        print("  [REGISTER] Testing account creation...")
        reg_session = await session_service.create_session(
            app_name="qa_pipeline", user_id=user_id,
            state={"site_url": site_url, "phase": "register_test"},
        )
        reg_sid = reg_session.id
        import time as _time
        test_email = f"qatester{int(_time.time())}@calliq.com"
        reg_msg = (
            f"Test account registration on {site_url}.\n"
            f"Use this brand-new test email: {test_email}\n"
            f"Use this password for the new account: {SITE_PASSWORD}\n\n"
            f"Steps:\n"
            f"1. Navigate to {site_url}.\n"
            f"2. Look for a 'Sign up' / 'Register' / 'Create account' link or button on the page "
            f"(try routes like /register, /signup, /sign-up if needed).\n"
            f"3. If a registration form is found: fill in the test email and password (and any "
            f"required name/role fields with sensible test values), then submit.\n"
            f"4. Verify the result: an account created / success message / redirected to a logged-in page.\n"
            f"5. Take a screenshot of the result.\n"
            f"6. Call record_evidence(check_id='account_registration', "
            f"status='PASS' if registration succeeded else 'FAIL', "
            f"note='describe what happened (form found? success message? error?)', "
            f"screenshot_path='<the screenshot path>').\n"
            f"If no registration link or form exists, call record_evidence(check_id='account_registration', "
            f"status='BLOCKED', note='No registration/signup page found', screenshot_path='')."
        )
        reg_events = await run_agent(nav_runner, reg_sid, user_id, reg_msg,
                                     "navigator_register", timeout_seconds=300)
        reg_state = await get_fresh_session_state(session_service, reg_sid, user_id)
        reg_evidence = reg_state.get("test_evidence")
        if not reg_evidence:
            reg_evidence = extract_json_from_events(reg_events)
        if reg_evidence:
            for item in reg_evidence if isinstance(reg_evidence, list) else [reg_evidence]:
                if isinstance(item, dict):
                    print(f"  [REGISTER] {item.get('check_id')}: {item.get('status')} — {item.get('note', '')[:80]}")
        else:
            print("  [REGISTER] Registration step produced no confirmation — continuing anyway.")

        # Login + registration results join the report so the fixing AI sees them
        for name, evidence in (("login", login_evidence), ("register", reg_evidence)):
            if not evidence:
                continue
            verdicts = evidence_to_verdicts(evidence, name)
            if not verdicts:
                continue
            overall = "PASS" if any(v["verdict"] == "PASS" for v in verdicts) else "BLOCKED"
            all_screen_results.append({
                "screen_id": name,
                "route": f"{site_url} ({name} check)",
                "verdicts": verdicts,
                "overall": overall,
            })

    finally:
        stop_browser()

    # ─── STEP 4: REPORT ─────────────────────────────────────────────────
    print(f"\n[4/4] REPORT GENERATOR: Compiling results...")
    report = build_report_agent()
    report_runner = Runner(
        agent=report, app_name="qa_pipeline",
        session_service=session_service, artifact_service=artifact_service,
    )
    all_screen_results_json = json.dumps(all_screen_results, default=str)
    report_msg = (
        f"Write the QA report narrative for site {site_url}.\n"
        f"All screen results (per-check verdicts with observed details): {all_screen_results_json}\n\n"
        f"Your job is ONLY the narrative: a plain-English analysis of the BREAKAGES. "
        f"Do NOT list every check — the pipeline writes those lines itself. "
        f"Write exactly two sections, plain text, no tables, no markdown:\n"
        f"TOP_BREAKAGES:\n"
        f"- one line per failed check: what was tried, exactly what broke (exact "
        f"error text, HTTP status, console error), and the page/route it happened on.\n"
        f"FIX_THIS_FIRST:\n"
        f"- one line per recommendation, most severe first, with a concrete fix "
        f"suggestion (e.g. sanitize input on the search form, add try/catch in X).\n"
        f"If there are zero failures, write: TOP_BREAKAGES: none found.\n\n"
        f"Then call generate_docx_report() with:\n"
        f"- report_text: your analysis text\n"
        f"- all_screen_results_json: the screen results JSON (pass it through unchanged)\n"
        f"- site_url: {site_url}\n"
        f"- screenshots_dir: '{SCREENSHOT_DIR}'\n"
        f"- output_dir: report directory"
    )
    report_session = await session_service.create_session(
        app_name="qa_pipeline", user_id=user_id,
        state={"repo_url": repo_url, "site_url": site_url, "phase": "report"},
    )
    report_sid = report_session.id
    events = await run_agent(report_runner, report_sid, user_id, report_msg, "report_generator")
    report_state = await get_fresh_session_state(session_service, report_sid, user_id)
    final_report = report_state.get("final_report")

    if not final_report:
        final_report = extract_text(events)

    # Deterministic per-check lines (never depends on the LLM)
    per_check_lines, total_checks, passed, failed, blocked = render_per_check_lines(all_screen_results)
    summary_block = [
        f"total_screens_tested: {len(all_screen_results)}",
        f"total_checks_run: {total_checks}",
        f"results: PASS={passed} FAIL={failed} BLOCKED={blocked}",
    ]
    narrative = final_report if isinstance(final_report, str) else json.dumps(final_report, default=str)
    ai_report_text = "\n".join(summary_block) + "\n\n" + "\n".join(per_check_lines) + "\n\n" + narrative.strip()

    # ─── DOCX REPORT ──────────────────────────────────────────
    # Narrative text in the DOCX; per-check verdicts are rendered as tables
    # and screenshot captions inside docx_report.py (deterministic).
    try:
        docx_path = generate_docx_report(
            report_text=narrative,
            all_screen_results_json=all_screen_results_json,
            site_url=site_url,
            screenshots_dir=SCREENSHOT_DIR,
        )
        print(f"  DOCX Report saved: {docx_path}")
    except Exception as e:
        print(f"  [ERROR] DOCX generation failed: {e}")
        docx_path = None

    # ─── PLAIN-TEXT REPORT (for AI consumption) ──────────────
    # Deterministic per-check lines + LLM narrative — complete every run.
    txt_path = None
    try:
        txt_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            f"qa_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        )
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(ai_report_text)
        print(f"  TXT Report saved: {txt_path}")
    except Exception as e:
        print(f"  [ERROR] TXT save failed: {e}")
        txt_path = None

    # ─── OUTPUT ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    if isinstance(final_report, str):
        print(final_report[:2000])
        if len(final_report) > 2000:
            print(f"\n... (truncated, full report in {docx_path})")
    else:
        print(json.dumps(final_report, indent=2, default=str)[:2000])

    # Summary
    total = len(all_screen_results)
    p = sum(1 for r in all_screen_results if r["overall"] == "PASS")
    c = sum(1 for r in all_screen_results if r["overall"] == "PASS_WITH_CAVEATS")
    f = sum(1 for r in all_screen_results if r["overall"] == "FAIL")
    b = total - p - c - f
    total_elapsed = time.monotonic() - pipeline_start
    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {total} screens | PASS: {p} | PASS_WITH_CAVEATS: {c} | FAIL: {f} | BLOCKED: {b}")
    print(f"Total pipeline time: {total_elapsed / 60:.1f} minutes")
    if docx_path:
        print(f"DOCX Report: {docx_path}")
    if txt_path:
        print(f"TXT Report (for AI): {txt_path}")
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description="Run QA pipeline deterministically")
    parser.add_argument("--repo-url", default=None,
                        help="GitHub repository URL (omit for black-box testing with only --site-url)")
    parser.add_argument("--site-url", required=True, help="Deployed site URL")
    parser.add_argument("--test-file", default=None, help="File path for upload testing")
    parser.add_argument("--max-screens", type=int, default=MAX_SCREENS,
                        help=f"Maximum number of screens to test (default: {MAX_SCREENS})")
    args = parser.parse_args()

    asyncio.run(pipeline_main(args.repo_url, args.site_url, args.test_file, args.max_screens))


if __name__ == "__main__":
    main()
