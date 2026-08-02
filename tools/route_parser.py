import re
import os


def parse_route_config(repo_path: str, route_file: str) -> str:
    """Read a route configuration file and extract route-to-component mappings."""
    full_path = os.path.join(repo_path, route_file)
    if not os.path.exists(full_path):
        return f"File not found: {route_file}"

    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        return f"Error reading {route_file}: {e}"

    routes = []

    route_pattern = re.compile(
        r'<Route\s+path=["\']([^"\']+)["\']\s+element=\{?<(\w+)',
        re.IGNORECASE,
    )
    for match in route_pattern.finditer(content):
        routes.append((match.group(1), match.group(2)))

    js_route_pattern = re.compile(
        r'path:\s*["\']([^"\']+)["\'].*?(?:element|component):\s*<?(\w+)',
        re.IGNORECASE,
    )
    for match in js_route_pattern.finditer(content):
        routes.append((match.group(1), match.group(2)))

    if "/pages/" in route_file or "/app/" in route_file or "\\pages\\" in route_file or "\\app\\" in route_file:
        route_path = re.sub(r".*?(?:pages|app)", "", route_file)
        route_path = re.sub(r"\.(tsx?|jsx?)$", "", route_path)
        route_path = re.sub(r"/index$", "/", route_path)
        route_path = route_path.replace("\\index", "\\")
        comp_name = os.path.basename(route_file).split(".")[0]
        if comp_name not in ("index",):
            routes.append((f"/{comp_name.lower()}", comp_name))

    if routes:
        mappings = [f"  {path} -> <{comp} />" for path, comp in routes]
        return f"Routes found in {route_file}:\n" + "\n".join(mappings)

    preview = content[:400].replace("\n", " ")
    return f"No routes found in {route_file}. Content preview:\n{preview}"
