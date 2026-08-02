from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from ..prompts.navigator import NAVIGATOR_PROMPT
from ..config import LLM_MODEL
from ..tools.playwright_screenshot import take_screenshot
from ..tools.evidence_tools import record_evidence

navigator_agent = Agent(
    name="navigator",
    model=LLM_MODEL,
    description="Navigates the live site using Playwright MCP, executes test actions from contracts.",
    instruction=NAVIGATOR_PROMPT,
    tools=[
        take_screenshot,
        record_evidence,
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=["-y", "@playwright/mcp@latest", "--cdp-endpoint", "http://127.0.0.1:9222", "--image-responses", "omit"],
                )
            ),
            tool_filter=[
                # Core navigation & interaction
                "browser_navigate",
                "browser_snapshot",
                "browser_click",
                "browser_type",
                "browser_network_requests",
                # Dialog/modal handling
                "browser_file_upload",
                "browser_handle_dialog",
                "browser_press_key",
                "browser_navigate_back",
                "browser_wait_for",
            ]
        )
    ],
    output_key="test_evidence",
    mode="chat",
    timeout=1800,
)
