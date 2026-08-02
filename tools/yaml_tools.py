import os
import yaml
from typing import Any


def load_standards(standards_dir: str = None) -> dict[str, Any]:
    """Load all YAML standard files from the standards directory."""
    if standards_dir is None:
        standards_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "standards")

    standards = {}
    for filename in os.listdir(standards_dir):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            filepath = os.path.join(standards_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "rules" in data:
                    standards[filename] = data["rules"]
    return standards


def get_rules_for_screen(standards: dict, has_form: bool, has_navigation: bool) -> list[dict]:
    """Filter rules applicable to a specific screen based on its features."""
    applicable = []
    for filename, rules in standards.items():
        for rule in rules:
            if filename == "forms.yaml" and not has_form:
                continue
            if filename == "navigation.yaml" and not has_navigation:
                continue
            applicable.append(rule)
    return applicable


def read_yaml_standards() -> str:
    """Read all YAML standard files and return them as formatted text for the LLM."""
    try:
        standards = load_standards()
        if not standards:
            return "No YAML standard files found in standards/ directory."

        output_parts = []
        for filename, rules in standards.items():
            output_parts.append(f"\n=== {filename} ===")
            for i, rule in enumerate(rules, 1):
                rule_id = rule.get("id", f"rule_{i}")
                category = rule.get("name", "unknown")
                description = rule.get("description", "No description")
                severity = rule.get("severity", "medium")
                output_parts.append(f"[{rule_id}] ({category}/{severity}) {description}")

        return "\n".join(output_parts)
    except Exception as e:
        return f"Error reading YAML standards: {e}"


def get_rules_as_json() -> str:
    """Read all YAML standard files and return them as JSON for the LLM."""
    try:
        standards = load_standards()
        import json
        return json.dumps(standards, indent=2)
    except Exception as e:
        return f"Error reading YAML standards: {e}"
