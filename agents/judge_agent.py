from google.adk.agents import Agent
from ..prompts.judge import JUDGE_PROMPT
from ..config import LLM_MODEL

judge_agent = Agent(
    name="judge",
    model=LLM_MODEL,
    description="Compares expected contract vs actual evidence, determines PASS/FAIL/BLOCKED.",
    instruction=JUDGE_PROMPT,
    output_key="judge_verdicts",
    mode="chat",
)
