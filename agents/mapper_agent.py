from google.adk.agents import Agent
from ..tools.repo_analyzer import clone_repo, grep_routes, list_src
from ..tools.route_parser import parse_route_config
from ..tools.component_reader import read_components
from ..prompts.mapper import MAPPER_PROMPT
from ..config import LLM_MODEL

mapper_agent = Agent(
    name="mapper",
    model=LLM_MODEL,
    description="Hybrid mapper: clones repo, analyzes file system, reads source code to build screen map.",
    instruction=MAPPER_PROMPT,
    tools=[clone_repo, grep_routes, list_src, parse_route_config, read_components],
    output_key="screen_map",
    mode="chat",
)
