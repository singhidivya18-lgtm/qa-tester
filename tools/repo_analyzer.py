import re
import os


def clone_repo(repo_url: str) -> str:
    """Clone a git repository and return the local path."""
    from ..utils.git_utils import clone_repo as _clone
    path = _clone(repo_url)
    return f"Repository cloned to: {path}"


def grep_routes(repo_path: str, max_results: int = 20) -> str:
    """Search for React route definitions in the codebase. Returns up to max_results matches."""
    patterns = [
        r"<Route\s",
        r"createBrowserRouter",
        r"routes\s*=|Routes\s*=",
        r"createRoutesFromElements",
        r"gatsby-node",
        r"pages/",
        r"app/",
    ]
    results = []
    skip_dirs = {"node_modules", ".git", "dist", "build", ".next", "__pycache__", "coverage", "content"}

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if len(results) >= max_results:
                break
            if f.endswith((".tsx", ".ts", ".jsx", ".js")):
                path = os.path.join(root, f)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as file:
                        content = file.read()
                    for pat in patterns:
                        if re.search(pat, content):
                            rel = os.path.relpath(path, repo_path)
                            results.append(f"{rel}: matches pattern '{pat}'")
                            break
                except Exception:
                    pass
        if len(results) >= max_results:
            break

    if not results:
        return "No route definitions found"

    total_found = len(results)
    summary = f"Found {total_found} route files (limited to {max_results}):\n" + "\n".join(results)
    return summary


def list_src(repo_path: str, max_entries: int = 40) -> str:
    """List the source directory structure, capped at max_entries lines."""
    src = os.path.join(repo_path, "src")
    if not os.path.exists(src):
        src = repo_path

    entries = []
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", "content", ".next")]
        level = root.replace(src, "").count(os.sep)
        indent = "  " * level
        entries.append(f"{indent}{os.path.basename(root)}/")
        subindent = "  " * (level + 1)
        for f in sorted(files)[:10]:
            entries.append(f"{subindent}{f}")
        if len(files) > 10:
            entries.append(f"{subindent}... and {len(files) - 10} more")
        if len(entries) >= max_entries:
            entries.append(f"... (truncated at {max_entries} entries)")
            break

    return "\n".join(entries)
