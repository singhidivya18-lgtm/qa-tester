# QA Tester Agent

Deterministic QA pipeline for testing live React deployments against automated test contracts. Clones the app's repository, maps its screens, generates accessibility/UX/error-handling contracts, then uses a browser agent (Playwright MCP over a shared CDP browser) to test each screen and produce an honest DOCX report with screenshots.

## Architecture

The pipeline runs 4 deterministic steps with Python control flow (no LLM orchestration):

1. **Mapper** (`tools/deterministic_mapper.py`) — clones the repo and maps its screens (route, component) without an LLM.
2. **Contract generator** (`prompts/contract.py`) — builds test contracts (checks per screen) from YAML standards in `standards/`.
3. **Navigator + Judge** (`run_pipeline.py`) — for each screen, a navigator agent drives a shared headless browser (CDP port 9222, `tools/browser_server.py`), records per-check evidence, takes screenshots; then a judge agent issues PASS/FAIL/BLOCKED verdicts. Login is done once up front; the shared browser session persists login state across screens.
4. **Report generator** (`prompts/report.py` + `tools/docx_report.py`) — compiles an honest DOCX report (scorecard, per-screen results, screenshots). HONESTY RULES forbid inventing results.

### Reliability features
- **Rate limiting + retry** (`utils/throttle.py`) — spaces LLM calls and retries rate limits, empty responses, and network hiccups.
- **Fresh session per screen** — only the current screen's contract is sent, so context stays small.
- **Evidence via tools** (`tools/evidence_tools.py`) — navigator/judge record results to session state with `record_evidence`/`record_verdict` instead of relying on final JSON output.
- **Screenshot fallback** — if no verdict is recorded but screenshots exist, they are counted as BLOCKED evidence so nothing is silently lost.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
copy .env.example .env   # then fill in OPENROUTER_API_KEY + site credentials
```

## Usage

```bash
python -m react_qa_agent.run_pipeline \
  --repo-url "https://github.com/owner/app" \
  --site-url "http://example.com/login" \
  --max-screens 10        # optional, default 10
```

Screenshots are written to `~/.react_qa_screenshots/`; the DOCX report is written next to the pipeline module.

## Configuration

All settings live in `config.py`, overridable via `.env`:

| Variable | Purpose |
| --- | --- |
| `OPENROUTER_API_KEY` | API key for the LLM (`openrouter/deepseek/deepseek-v4-flash` by default) |
| `SITE_EMAIL` | Login email for the target site |
| `SITE_PASSWORD` | Login password (fallback: `SITE_PASSWORD_FALLBACK`) |
| `TEST_FILE_PATH` | Optional file used for upload-testing checks |
