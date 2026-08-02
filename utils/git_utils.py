import subprocess
import shutil
import os
import stat
import time


def _rmtree_retry(path, retries=3, delay=1.0):
    for attempt in range(retries):
        try:
            shutil.rmtree(path, onerror=lambda f, p, e: os.chmod(p, stat.S_IWRITE) or f(p))
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


def clone_repo(repo_url: str, dest: str = None) -> str:
    if dest is None:
        dest = os.path.join(os.path.expanduser("~"), ".react_qa_repos", repo_url.split("/")[-1].replace(".git", ""))

    if os.path.exists(dest):
        _rmtree_retry(dest)

    os.makedirs(os.path.dirname(dest), exist_ok=True)

    result = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, dest],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        # Check if it's a checkout failure (clone succeeded but checkout failed)
        if "warning: Clone succeeded, but checkout failed" in result.stderr:
            # Try to restore the working tree, ignoring errors
            try:
                subprocess.run(
                    ["git", "restore", "--source=HEAD", ":/"],
                    cwd=dest,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                pass
            # Return the path even if checkout partially failed
            # The repo content is still available via git commands
            return dest
        else:
            raise RuntimeError(f"git clone failed: {result.stderr}")

    return dest


def get_repo_files(repo_path: str, extensions: tuple = (".tsx", ".ts", ".jsx", ".js")) -> list[str]:
    skip_dirs = {"node_modules", ".git", "dist", "build", ".next", "__pycache__", "coverage"}
    files = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in filenames:
            if f.endswith(extensions):
                files.append(os.path.join(root, f))
    return files
