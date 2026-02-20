import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
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


def load_species_history(data_dir: str) -> dict:
    """Load species_seen.json from data_dir. Returns {} if missing."""
    path = os.path.join(data_dir, "species_seen.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_species_history(data_dir: str, history: dict) -> None:
    """Atomic write species_seen.json to data_dir."""
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "species_seen.json")
    fd, tmp_path = tempfile.mkstemp(dir=data_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(history, f, indent=2)
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise


def detect_new_species(sites: list[dict], history: dict, now: str) -> list[dict]:
    """Compare current species against history. Flag new species.

    On first run (empty history for a site), seeds all species without marking as new.
    On subsequent runs, species not in history are flagged as new.
    Mutates history dict in place. Returns list of new species dicts.
    """
    new_species = []
    for site in sites:
        slug = site["slug"]
        site_name = site["name"]
        if slug not in history:
            # First run for this site — seed all species, don't mark as new
            history[slug] = {}
            for s in site.get("species", []):
                history[slug][s["species"]] = {
                    "scientific_name": s.get("scientific_name", ""),
                    "image_url": s.get("image_url", ""),
                    "first_seen": now,
                }
            continue

        for s in site.get("species", []):
            name = s["species"]
            if name not in history[slug]:
                history[slug][name] = {
                    "scientific_name": s.get("scientific_name", ""),
                    "image_url": s.get("image_url", ""),
                    "first_seen": now,
                }
                new_species.append({
                    "species": name,
                    "scientific_name": s.get("scientific_name", ""),
                    "image_url": s.get("image_url", ""),
                    "site_name": site_name,
                    "site_slug": slug,
                    "first_seen": now,
                })
    return new_species


def build_recent_new_species(history: dict, days: int = 7) -> list[dict]:
    """Scan history for species with first_seen in the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = []
    for slug, species_dict in history.items():
        for name, info in species_dict.items():
            try:
                first_seen = datetime.fromisoformat(info["first_seen"])
            except (KeyError, ValueError):
                continue
            if first_seen >= cutoff:
                recent.append({
                    "species": name,
                    "scientific_name": info.get("scientific_name", ""),
                    "image_url": info.get("image_url", ""),
                    "site_slug": slug,
                    "first_seen": info["first_seen"],
                })
    recent.sort(key=lambda r: r["first_seen"], reverse=True)
    return recent


def generate(output_dir: str, data_dir: str | None = None) -> None:
    """Run health checks and render the dashboard HTML."""
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(output_dir.rstrip("/")), "data")

    template_dir = find_template_dir()
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    template = env.get_template("index.html.j2")

    sites = check_all_sites()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_display = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Species tracking
    history = load_species_history(data_dir)
    new_species = detect_new_species(sites, history, now_iso)
    recent_new_species = build_recent_new_species(history)
    save_species_history(data_dir, history)

    html = template.render(
        sites=sites,
        generated_at=now_display,
        new_species=new_species,
        recent_new_species=recent_new_species,
    )

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
