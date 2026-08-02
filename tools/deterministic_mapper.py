"""Deterministic mapper — builds screen map from repo analysis without LLM."""

import json
import os
import re
from typing import Any


def deterministic_mapper(repo_url: str, site_url: str) -> dict:
    """Clone repo and build screen map using Python analysis (no LLM).

    Returns a screen_map dict with screens, navigation_graph, entry_points.
    """
    from .repo_analyzer import clone_repo, grep_routes, list_src
    from .route_parser import parse_route_config
    from .component_reader import read_components

    # Step 1: Clone
    clone_result = clone_repo(repo_url)
    repo_path = clone_result.replace("Repository cloned to: ", "").strip()

    # Step 2: Find route files
    routes_output = grep_routes(repo_path, max_results=30)

    # Step 3: List src structure
    src_output = list_src(repo_path)

    # Step 4: Find page components (Next.js App Router pattern)
    screens = []
    screen_id = 0
    skip_dirs = {"node_modules", ".git", "dist", "build", ".next", "__pycache__", "coverage", "content", "api"}

    # Walk the app directory looking for page.tsx/page.ts files
    # Try multiple possible locations for the Next.js app directory
    app_dir = None
    for candidate in [
        os.path.join(repo_path, "dashboard", "src", "app"),
        os.path.join(repo_path, "src", "app"),
        os.path.join(repo_path, "app"),
    ]:
        if os.path.exists(candidate):
            app_dir = candidate
            break
    if app_dir is None:
        app_dir = repo_path

    def clean_route_path(path: str) -> str:
        """Remove route group dirs like (dashboard) and normalize."""
        if path == ".":
            return "/"
        parts = path.replace("\\", "/").split("/")
        cleaned = [p for p in parts if p and p != "." and not p.startswith("(") and not p.startswith("[")]
        result = "/" + "/".join(cleaned) if cleaned else "/"
        return result

    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        # Skip route group directories themselves (but still walk into them)
        # We process pages found at ANY depth, including inside (dashboard)/, (auth)/, etc.

        if "page.tsx" in files or "page.ts" in files or "page.jsx" in files or "page.js" in files:
            page_file = next((f for f in files if f.startswith("page.")), None)
            if page_file:
                rel_path = os.path.relpath(os.path.join(root, page_file), repo_path)
                # Build route from directory path relative to app_dir
                rel_dir = os.path.relpath(root, app_dir)
                route_path = clean_route_path(rel_dir)

                # Read component to detect forms and navigation
                has_form = False
                has_navigation = False
                nav_targets = []
                description = ""
                component_name = os.path.basename(root).replace("-", " ").title().replace(" ", "")
                if component_name.lower() in ("app", "src", "dashboard", "auth"):
                    component_name = page_file.replace("page.", "").replace(".tsx", "").replace(".ts", "").replace(".jsx", "").replace(".js", "")
                    if not component_name:
                        component_name = "HomePage"
                    else:
                        component_name = component_name.title()

                try:
                    comp_output = read_components(os.path.join(root, page_file))
                    if "form" in comp_output.lower() or "input" in comp_output.lower() or "submit" in comp_output.lower():
                        has_form = True
                    if "nav" in comp_output.lower() or "sidebar" in comp_output.lower() or "menu" in comp_output.lower():
                        has_navigation = True
                    # Extract description from first comment or component name
                    desc_match = re.search(r'//\s*(.+)', comp_output)
                    if desc_match:
                        description = desc_match.group(1).strip()[:100]
                except Exception:
                    pass

                if not description:
                    description = f"{component_name} page at {route_path}"

                screens.append({
                    "screen_id": f"screen_{screen_id}",
                    "component_path": rel_path,
                    "route_path": route_path,
                    "component_name": component_name,
                    "imports": [],
                    "has_form": has_form,
                    "has_navigation": has_navigation,
                    "nav_targets": nav_targets,
                    "description": description,
                })
                screen_id += 1

    # Also check for layout files to detect navigation
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        if "layout.tsx" in files or "layout.ts" in files:
            layout_file = next((f for f in files if f.startswith("layout.")), None)
            if layout_file:
                try:
                    comp_output = read_components(os.path.join(root, layout_file))
                    if "sidebar" in comp_output.lower() or "nav" in comp_output.lower():
                        # Mark all child screens as having navigation
                        rel_dir = os.path.relpath(root, app_dir)
                        for s in screens:
                            if s["route_path"].startswith("/" + rel_dir.replace("\\", "/")):
                                s["has_navigation"] = True
                except Exception:
                    pass

    # Build navigation graph from link patterns in components
    navigation_graph = []
    entry_points = [s["screen_id"] for s in screens[:1]]  # First screen is entry point

    screen_map = {
        "screens": screens,
        "navigation_graph": navigation_graph,
        "entry_points": entry_points,
    }

    return screen_map
