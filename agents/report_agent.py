from google.adk.agents import Agent
from ..prompts.report import REPORT_PROMPT
from ..config import LLM_MODEL
from ..tools.docx_report import generate_docx_report

report_agent = Agent(
    name="report_generator",
    model=LLM_MODEL,
    description="Compiles all screen results into a final QA report in DOCX format.",
    instruction=REPORT_PROMPT,
    tools=[generate_docx_report],
    output_key="final_report",
    mode="chat",
)
