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
    Mutates history dict in place. Returns list of new species dicts,
    grouped by species name (one entry per species with a list of sites).
    """
    # First pass: update history and collect raw new sightings
    raw_new: list[dict] = []
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
                raw_new.append({
                    "species": name,
                    "scientific_name": s.get("scientific_name", ""),
                    "image_url": s.get("image_url", ""),
                    "site_name": site_name,
                    "site_slug": slug,
                })

    # Second pass: group by species name
    grouped: dict[str, dict] = {}
    for entry in raw_new:
        name = entry["species"]
        if name not in grouped:
            grouped[name] = {
                "species": name,
                "scientific_name": entry["scientific_name"],
                "image_url": entry["image_url"],
                "site_names": [],
            }
        grouped[name]["site_names"].append(entry["site_name"])
        if not grouped[name]["image_url"] and entry["image_url"]:
            grouped[name]["image_url"] = entry["image_url"]

    return list(grouped.values())


def build_recent_new_species(history: dict, days: int = 7) -> list[dict]:
    """Scan history for species with first_seen in the last N days.

    Groups by species name so a bird detected at multiple sites produces
    one entry with a list of sites, sorted by earliest first_seen.

    >>> build_recent_new_species({
    ...     "site-a": {"Dove": {"first_seen": "2099-01-01T00:00:00+00:00", "scientific_name": "D. dove", "image_url": ""}},
    ...     "site-b": {"Dove": {"first_seen": "2099-01-02T00:00:00+00:00", "scientific_name": "D. dove", "image_url": ""}},
    ...     "site-c": {"Owl": {"first_seen": "2099-01-03T00:00:00+00:00", "scientific_name": "O. owl", "image_url": ""}},
    ... }, days=50000)
    [{'species': 'Owl', 'scientific_name': 'O. owl', 'image_url': '', 'sites': [{'slug': 'site-c', 'first_seen': '2099-01-03T00:00:00+00:00'}], 'first_seen': '2099-01-03T00:00:00+00:00'}, {'species': 'Dove', 'scientific_name': 'D. dove', 'image_url': '', 'sites': [{'slug': 'site-a', 'first_seen': '2099-01-01T00:00:00+00:00'}, {'slug': 'site-b', 'first_seen': '2099-01-02T00:00:00+00:00'}], 'first_seen': '2099-01-01T00:00:00+00:00'}]
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Collect all recent sightings grouped by species name
    grouped: dict[str, dict] = {}
    for slug, species_dict in history.items():
        for name, info in species_dict.items():
            try:
                first_seen = datetime.fromisoformat(info["first_seen"])
            except (KeyError, ValueError):
                continue
            if first_seen < cutoff:
                continue
            if name not in grouped:
                grouped[name] = {
                    "species": name,
                    "scientific_name": info.get("scientific_name", ""),
                    "image_url": info.get("image_url", ""),
                    "sites": [],
                    "first_seen": info["first_seen"],
                }
            grouped[name]["sites"].append({
                "slug": slug,
                "first_seen": info["first_seen"],
            })
            # Use the image from whichever site has one
            if not grouped[name]["image_url"] and info.get("image_url"):
                grouped[name]["image_url"] = info["image_url"]
            # Track the earliest first_seen across all sites
            if info["first_seen"] < grouped[name]["first_seen"]:
                grouped[name]["first_seen"] = info["first_seen"]

    # Sort sites within each species by first_seen
    for entry in grouped.values():
        entry["sites"].sort(key=lambda s: s["first_seen"])

    # Sort species by most recent first_seen (newest discoveries first)
    result = sorted(grouped.values(), key=lambda r: r["first_seen"], reverse=True)
    return result


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
