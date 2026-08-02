"""Deterministic contract generator — builds test contracts from YAML standards without LLM."""

import json
import os
import yaml
from typing import Any


def deterministic_contract_generator(screen_map: dict) -> list:
    """Generate test contracts from screen_map and YAML standards using Python (no LLM).

    Returns a list of ScreenContract dicts.
    """
    standards_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "standards")

    # Load all YAML standards
    standards = {}
    for filename in os.listdir(standards_dir):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            filepath = os.path.join(standards_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "rules" in data:
                    standards[filename] = data["rules"]

    screens = screen_map.get("screens", [])
    contracts = []

    for screen in screens:
        screen_id = screen.get("screen_id", "unknown")
        route = screen.get("route_path", "/")
        component = screen.get("component_name", "Unknown")
        has_form = screen.get("has_form", False)
        has_navigation = screen.get("has_navigation", False)
        description = screen.get("description", "")

        checks = []

        for filename, rules in standards.items():
            # Filter rules by screen properties
            if filename == "forms.yaml" and not has_form:
                continue
            if filename == "navigation.yaml" and not has_navigation:
                continue

            for rule in rules:
                rule_id = rule.get("id", "unknown")
                rule_name = rule.get("name", "unknown")
                severity = rule.get("severity", "medium")
                rule_desc = rule.get("description", "")
                expected = rule.get("expected", "")
                test_action = rule.get("test_action", "")
                expected_result = rule.get("expected_result", "")

                # Make test_action and expected_result specific to this screen
                test_action_specific = test_action.replace("the page", f"{route} ({component})")
                test_action_specific = test_action_specific.replace("the screen", f"{route} ({component})")
                expected_result_specific = expected_result.replace("the page", f"{route} ({component})")
                expected_result_specific = expected_result_specific.replace("the screen", f"{route} ({component})")

                checks.append({
                    "check_id": f"{screen_id}_{rule_name}",
                    "standard_file": filename,
                    "rule_name": rule_name,
                    "severity": severity,
                    "description": rule_desc,
                    "expected_behavior": expected,
                    "test_action": test_action_specific,
                    "expected_result": expected_result_specific,
                })

        # Ensure minimum checks (page_has_title, heading_hierarchy, responsive_layout, no_console_errors)
        required_checks = [
            ("page_has_title", "accessibility", "critical", "Page must have a descriptive title"),
            ("heading_hierarchy", "accessibility", "medium", "Headings must follow h1 > h2 > h3 order"),
            ("responsive_layout", "ux_patterns", "medium", "Page layout must adapt to different viewport sizes"),
            ("no_console_errors", "performance", "high", "Page must load without JavaScript console errors"),
        ]
        existing_names = {c["rule_name"] for c in checks}
        for rname, rfile, rseverity, rdesc in required_checks:
            if rname not in existing_names:
                checks.append({
                    "check_id": f"{screen_id}_{rname}",
                    "standard_file": f"{rfile}.yaml",
                    "rule_name": rname,
                    "severity": rseverity,
                    "description": rdesc,
                    "expected_behavior": rdesc,
                    "test_action": f"Navigate to {route} and verify {rname}",
                    "expected_result": f"{rdesc} on {route} ({component})",
                })

        # Sort by severity (critical first)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        checks.sort(key=lambda c: severity_order.get(c["severity"], 99))

        contracts.append({
            "screen_id": screen_id,
            "route": route,
            "component": component,
            "checks": checks,
        })

    return contracts
