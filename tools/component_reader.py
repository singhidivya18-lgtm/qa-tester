import re
import os


def read_components(repo_path: str, component_path: str) -> str:
    """Read a React component and extract key information."""
    full_path = os.path.join(repo_path, component_path)
    if not os.path.exists(full_path):
        return f"File not found: {component_path}"

    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        return f"Error reading {component_path}: {e}"

    imports = re.findall(r'import\s+.*?from\s+["\']([^"\']+)["\']', content)

    nav_patterns = [r"useNavigate", r"<Link\s", r"navigate\(", r"history\.push", r"useHistory"]
    has_nav = any(re.search(p, content) for p in nav_patterns)

    form_patterns = [r"<form", r"onSubmit", r"handleSubmit", r"useForm"]
    has_form = any(re.search(p, content, re.IGNORECASE) for p in form_patterns)

    link_targets = re.findall(r'(?:to|href)=["\']([^"\']+)["\']', content)
    link_targets = [t for t in link_targets if t.startswith("/") and t != "/"]

    state_patterns = [r"useState", r"useReducer", r"useContext", r"useSelector", r"useStore"]
    state_used = [p for p in state_patterns if re.search(p, content)]

    name_match = re.search(r'(?:export\s+(?:default\s+)?)?(?:function|const)\s+(\w+)', content)
    comp_name = name_match.group(1) if name_match else os.path.basename(component_path).split(".")[0]

    lines = [
        f"Component: {comp_name}",
        f"File: {component_path}",
        f"Has forms: {has_form}",
        f"Has navigation: {has_nav}",
        f"Link targets: {link_targets}",
        f"State management: {state_used}",
        f"External imports: {[i for i in imports if not i.startswith('.') and not i.startswith('/')]}",
    ]
    return "\n".join(lines)
