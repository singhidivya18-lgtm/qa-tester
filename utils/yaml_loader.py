import os
import yaml
from typing import Any


def load_standards(standards_dir: str = None) -> dict[str, Any]:
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
    applicable = []
    for filename, rules in standards.items():
        for rule in rules:
            if filename == "forms.yaml" and not has_form:
                continue
            if filename == "navigation.yaml" and not has_navigation:
                continue
            applicable.append(rule)
    return applicable
