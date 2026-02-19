import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from birdsnet_dash.healthcheck import check_all_sites

# Look for templates in several locations.
# _PACKAGE_DIR is e.g. /opt/birdsnet-dash/lib/python3.13/site-packages/birdsnet_dash
# Walk up to find the venv/install root (directory containing "lib/")
_PACKAGE_DIR = Path(__file__).resolve().parent
_INSTALL_ROOT = _PACKAGE_DIR
for _parent in _PACKAGE_DIR.parents:
    if (_parent / "lib").is_dir() and _parent != Path("/"):
        _INSTALL_ROOT = _parent
        break

_TEMPLATE_SEARCH_PATHS = [
    _INSTALL_ROOT / "templates",               # installed layout (/opt/birdsnet-dash/templates)
    _PACKAGE_DIR.parent.parent / "templates",  # development layout (repo root)
]


def find_template_dir() -> Path:
    for path in _TEMPLATE_SEARCH_PATHS:
        if (path / "index.html.j2").exists():
            return path
    raise FileNotFoundError(
        f"Could not find templates/index.html.j2 in any of: {_TEMPLATE_SEARCH_PATHS}"
    )


def generate(output_dir: str) -> None:
    """Run health checks and render the dashboard HTML."""
    template_dir = find_template_dir()
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    template = env.get_template("index.html.j2")

    sites = check_all_sites()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    html = template.render(sites=sites, generated_at=now)

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "index.html")

    # Atomic write: write to temp file then rename
    fd, tmp_path = tempfile.mkstemp(dir=output_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(html)
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, output_path)
    except BaseException:
        os.unlink(tmp_path)
        raise
