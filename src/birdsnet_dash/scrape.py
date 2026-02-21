import re
from datetime import date

import httpx


def fetch_stats(hostname: str) -> dict | None:
    """Fetch today's summary stats from a BirdNET-Pi instance.

    Returns dict with keys: total, today, last_hour, species_total, species_today.
    Returns None if unreachable.

    >>> parse_stats_html('<table><tr><th>Total</th><th>Today</th><th>Last Hour</th><th>Species Total</th><th>Species Today</th></tr><tr><td>11536</td><td><form><button>599</button></form></td><td>26</td><td><form><button>24</button></form></td><td><form><button>10</button></form></td></tr></table>')
    {'total': 11536, 'today': 599, 'last_hour': 26, 'species_total': 24, 'species_today': 10}
    """
    try:
        resp = httpx.get(
            f"https://{hostname}/todays_detections.php?today_stats=true",
            timeout=5,
            verify=False,
        )
        if resp.status_code >= 400:
            return None
        return parse_stats_html(resp.text)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return None


def parse_stats_html(html: str) -> dict | None:
    """Parse the stats HTML table from BirdNET-Pi.

    >>> parse_stats_html('<table><tr><th>Total</th></tr><tr><td>100</td><td><form><button>50</button></form></td><td>5</td><td><form><button>20</button></form></td><td><form><button>8</button></form></td></tr></table>')
    {'total': 100, 'today': 50, 'last_hour': 5, 'species_total': 20, 'species_today': 8}
    >>> parse_stats_html('garbage') is None
    True
    """
    # Extract all numbers from <td> and <button> elements in the stats row
    # The order is: Total, Today (in button), Last Hour, Species Total (in button), Species Today (in button)
    tds = re.findall(r"<td[^>]*>(.*?)</td>", html, re.DOTALL)
    if len(tds) < 5:
        return None

    values = []
    for td in tds[:5]:
        # Look for number in a <button> first, then plain text
        btn = re.search(r"<button[^>]*>(\d+)</button>", td)
        if btn:
            values.append(int(btn.group(1)))
        else:
            num = re.search(r"(\d+)", td)
            if num:
                values.append(int(num.group(1)))

    if len(values) < 5:
        return None

    return {
        "total": values[0],
        "today": values[1],
        "last_hour": values[2],
        "species_total": values[3],
        "species_today": values[4],
    }


def fetch_species_list(hostname: str, for_date: str | None = None) -> list[str]:
    """Fetch list of species detected on a given date from Caddy directory listing.

    BirdNET-Pi stores detections in /By_Date/{date}/{species}/ directories.
    Caddy's file server lists these as folder links, giving us a complete
    species list without needing to download all detection records.

    If for_date is None, uses today's date.

    >>> parse_species_dirs('<a href="./Spotted_Dove/">Spotted_Dove</a><a href="./Barn_Owl/">Barn_Owl</a>')
    ['Barn Owl', 'Spotted Dove']
    >>> parse_species_dirs('<a href="../">..</a>')
    []
    """
    if for_date is None:
        for_date = date.today().isoformat()
    try:
        resp = httpx.get(
            f"https://{hostname}/By_Date/{for_date}/",
            timeout=5,
            verify=False,
        )
        if resp.status_code >= 400:
            return []
        return parse_species_dirs(resp.text)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return []


def parse_species_dirs(html: str) -> list[str]:
    """Parse species folder names from Caddy directory listing HTML.

    >>> parse_species_dirs('<a href="./Spotted_Dove/">x</a><a href="./Barn_Owl/">y</a>')
    ['Barn Owl', 'Spotted Dove']
    >>> parse_species_dirs('<a href="../">..</a><a href="./Willie-wagtail/">w</a>')
    ['Willie-wagtail']
    >>> parse_species_dirs('no folders here')
    []
    """
    # Caddy lists folders as ./Folder_Name/ links
    folders = re.findall(r'href="\./([^/"]+)/"', html)
    species = [f.replace("_", " ") for f in folders]
    return sorted(species)


def fetch_detections(hostname: str, limit: int = 20) -> list[dict]:
    """Fetch recent detections from a BirdNET-Pi instance.

    Uses hard_limit parameter which returns the N most recent detections
    with a simple SQL LIMIT (no offset). The display_limit parameter uses
    offset-based pagination that only returns a 40-row window.

    Returns list of dicts with keys: species, scientific_name, time, confidence, image_url.
    """
    try:
        resp = httpx.get(
            f"https://{hostname}/todays_detections.php?ajax_detections=true&hard_limit={limit}",
            timeout=10,
            verify=False,
        )
        if resp.status_code >= 400:
            return []
        return parse_detections_html(resp.text)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return []


def parse_detections_html(html: str) -> list[dict]:
    """Parse detection entries from BirdNET-Pi ajax_detections HTML.

    Handles both HTML formats returned by BirdNET-Pi:
    - hard_limit format: species in <button class="a2">, time in separate <td>
    - display_limit format: species in <a class="a2">, time inline

    >>> parse_detections_html('<tr class="relative" id="1"><td class="relative"><div class="centered_image_container">14:53:59<br><b><a class="a2" href="x">Spotted Dove</a></b><br><i>Streptopelia chinensis</i><br><b>Confidence:</b> 75%<br></div></td>')
    [{'species': 'Spotted Dove', 'scientific_name': 'Streptopelia chinensis', 'time': '14:53:59', 'confidence': 75, 'image_url': '', 'wikipedia_url': '', 'filename': ''}]
    >>> parse_detections_html('<tr class="relative" id="1"><td>10:00:00<br></td><td id="recent_detection_middle_td"><div><div><img style="float:left" src="https://example.com/bird.jpg" id="birdimage" class="img1"></div><div><form><button class="a2" type="submit" name="species" value="Magpie">Magpie</button><br><i>\\nGymnorhina tibicen\\t<br></i></form></div></div></td><td><b>Confidence:</b>88%<br></td><td><a href="index.php?filename=Magpie-88-2026-02-21-birdnet-10:00:00.mp3">x</a><a href="https://wikipedia.org/wiki/Gymnorhina_tibicen">w</a></td>')
    [{'species': 'Magpie', 'scientific_name': 'Gymnorhina tibicen', 'time': '10:00:00', 'confidence': 88, 'image_url': 'https://example.com/bird.jpg', 'wikipedia_url': 'https://wikipedia.org/wiki/Gymnorhina_tibicen', 'filename': 'Magpie-88-2026-02-21-birdnet-10:00:00.mp3'}]
    """
    detections = []
    # Each detection is in a <tr class="relative"> block
    rows = re.split(r'<tr class="relative"', html)
    for row in rows[1:]:  # skip before first match
        # Species: match both <a class="a2">Name</a> and <button class="a2">Name</button>
        species_match = re.search(r'class="a2"[^>]*>([^<]+)</', row)
        # Scientific name: <i> may contain <br> and other tags; capture text before first <
        sci_match = re.search(r"<i>\s*([^<]+)", row)
        time_match = re.search(r"(\d{2}:\d{2}:\d{2})", row)
        conf_match = re.search(r"Confidence:</b>\s*(\d+)%", row)
        img_match = re.search(r'src="([^"]+)"[^>]*class="img1"', row)
        wiki_match = re.search(r'href="(https://wikipedia\.org/wiki/[^"]+)"', row)
        file_match = re.search(r'href="index\.php\?filename=([^"]+)"', row)

        if species_match:
            detections.append({
                "species": species_match.group(1),
                "scientific_name": sci_match.group(1).strip() if sci_match else "",
                "time": time_match.group(1) if time_match else "",
                "confidence": int(conf_match.group(1)) if conf_match else 0,
                "image_url": img_match.group(1) if img_match else "",
                "wikipedia_url": wiki_match.group(1) if wiki_match else "",
                "filename": file_match.group(1) if file_match else "",
            })
    return detections


def fetch_species_metadata(hostname: str, species_name: str) -> dict:
    """Fetch metadata for a single species by searching for one recent detection.

    Returns dict with keys: scientific_name, image_url, wikipedia_url.
    """
    try:
        resp = httpx.get(
            f"https://{hostname}/todays_detections.php",
            params={
                "ajax_detections": "true",
                "hard_limit": "1",
                "searchterm": species_name,
            },
            timeout=5,
            verify=False,
        )
        if resp.status_code >= 400:
            return {"scientific_name": "", "image_url": "", "wikipedia_url": ""}
        detections = parse_detections_html(resp.text)
        if detections:
            d = detections[0]
            return {
                "scientific_name": d.get("scientific_name", ""),
                "image_url": d.get("image_url", ""),
                "wikipedia_url": d.get("wikipedia_url", ""),
            }
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        pass
    return {"scientific_name": "", "image_url": "", "wikipedia_url": ""}


def build_species_summary(
    species_names: list[str],
    detections: list[dict],
    hostname: str | None = None,
) -> list[dict]:
    """Build species summary from directory listing and recent detections.

    species_names provides the complete list of species detected today
    (from the Caddy directory listing). detections provides metadata
    (scientific name, image, confidence) for species with recent activity.

    If hostname is provided, fetches metadata (image, scientific name,
    wikipedia URL) for any species not covered by the recent detections.

    >>> build_species_summary(
    ...     ["Barn Owl", "Spotted Dove"],
    ...     [
    ...         {"species": "Spotted Dove", "scientific_name": "Streptopelia chinensis", "confidence": 75, "image_url": "https://example.com/dove.jpg", "wikipedia_url": "https://wikipedia.org/wiki/Streptopelia_chinensis", "filename": ""},
    ...         {"species": "Spotted Dove", "scientific_name": "Streptopelia chinensis", "confidence": 92, "image_url": "", "wikipedia_url": "", "filename": ""},
    ...     ],
    ... )
    [{'species': 'Spotted Dove', 'scientific_name': 'Streptopelia chinensis', 'image_url': 'https://example.com/dove.jpg', 'wikipedia_url': 'https://wikipedia.org/wiki/Streptopelia_chinensis', 'recent_count': 2, 'max_confidence': 92}, {'species': 'Barn Owl', 'scientific_name': '', 'image_url': '', 'wikipedia_url': '', 'recent_count': 0, 'max_confidence': 0}]
    """
    # Index detection data by species
    det_data: dict[str, dict] = {}
    for d in detections:
        name = d["species"]
        if name not in det_data:
            det_data[name] = {
                "scientific_name": d.get("scientific_name", ""),
                "image_url": d.get("image_url", ""),
                "wikipedia_url": d.get("wikipedia_url", ""),
                "recent_count": 0,
                "max_confidence": 0,
            }
        det_data[name]["recent_count"] += 1
        det_data[name]["max_confidence"] = max(
            det_data[name]["max_confidence"], d.get("confidence", 0)
        )
        if not det_data[name]["image_url"] and d.get("image_url"):
            det_data[name]["image_url"] = d["image_url"]
        if not det_data[name]["wikipedia_url"] and d.get("wikipedia_url"):
            det_data[name]["wikipedia_url"] = d["wikipedia_url"]

    # For species without metadata, fetch one detection to get image/sci_name/wiki
    if hostname:
        for name in species_names:
            if name not in det_data or not det_data[name]["image_url"]:
                meta = fetch_species_metadata(hostname, name)
                if name not in det_data:
                    det_data[name] = {
                        "recent_count": 0,
                        "max_confidence": 0,
                        **meta,
                    }
                else:
                    for key in ("scientific_name", "image_url", "wikipedia_url"):
                        if not det_data[name][key] and meta[key]:
                            det_data[name][key] = meta[key]

    # Build result: all species from directory, enriched with detection data
    all_species = set(species_names) | set(det_data.keys())
    result = []
    for name in all_species:
        info = det_data.get(name, {})
        result.append({
            "species": name,
            "scientific_name": info.get("scientific_name", ""),
            "image_url": info.get("image_url", ""),
            "wikipedia_url": info.get("wikipedia_url", ""),
            "recent_count": info.get("recent_count", 0),
            "max_confidence": info.get("max_confidence", 0),
        })

    # Sort: species with recent detections first (by count desc), then alphabetically
    result.sort(key=lambda s: (-s["recent_count"], s["species"]))
    return result
