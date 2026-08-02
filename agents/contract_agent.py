from google.adk.agents import Agent
from ..prompts.contract import CONTRACT_PROMPT
from ..tools.yaml_tools import read_yaml_standards, get_rules_as_json
from ..config import LLM_MODEL

contract_agent = Agent(
    name="contract_generator",
    model=LLM_MODEL,
    description="Reads screen map and standards YAML files to generate test contracts per screen.",
    instruction=CONTRACT_PROMPT,
    tools=[read_yaml_standards, get_rules_as_json],
    output_key="contracts",
    mode="chat",
)
