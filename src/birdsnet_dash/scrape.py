import re

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


def fetch_detections(hostname: str, limit: int = 10) -> list[dict]:
    """Fetch recent detections from a BirdNET-Pi instance.

    Returns list of dicts with keys: species, scientific_name, time, confidence.
    """
    try:
        resp = httpx.get(
            f"https://{hostname}/todays_detections.php?ajax_detections=true&display_limit={limit}",
            timeout=5,
            verify=False,
        )
        if resp.status_code >= 400:
            return []
        return parse_detections_html(resp.text)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return []


def parse_detections_html(html: str) -> list[dict]:
    """Parse detection entries from BirdNET-Pi ajax_detections HTML.

    >>> parse_detections_html('<tr class="relative" id="1"><td class="relative"><div class="centered_image_container">14:53:59<br><b><a class="a2" href="x">Spotted Dove</a></b><br><i>Streptopelia chinensis</i><br><b>Confidence:</b> 75%<br></div></td>')
    [{'species': 'Spotted Dove', 'scientific_name': 'Streptopelia chinensis', 'time': '14:53:59', 'confidence': 75}]
    """
    detections = []
    # Each detection is in a <tr class="relative"> block
    rows = re.split(r'<tr class="relative"', html)
    for row in rows[1:]:  # skip before first match
        species_match = re.search(r'class="a2"[^>]*>([^<]+)</a>', row)
        sci_match = re.search(r"<i>([^<]+)</i>", row)
        time_match = re.search(r"(\d{2}:\d{2}:\d{2})<br>", row)
        conf_match = re.search(r"Confidence:</b>\s*(\d+)%", row)

        if species_match:
            detections.append({
                "species": species_match.group(1),
                "scientific_name": sci_match.group(1) if sci_match else "",
                "time": time_match.group(1) if time_match else "",
                "confidence": int(conf_match.group(1)) if conf_match else 0,
            })
    return detections


def build_species_summary(detections: list[dict]) -> list[dict]:
    """Aggregate detections into a species summary sorted by count descending.

    >>> build_species_summary([
    ...     {"species": "Spotted Dove", "confidence": 75},
    ...     {"species": "Spotted Dove", "confidence": 92},
    ...     {"species": "Magpie-lark", "confidence": 80},
    ... ])
    [{'species': 'Spotted Dove', 'count': 2, 'max_confidence': 92}, {'species': 'Magpie-lark', 'count': 1, 'max_confidence': 80}]
    """
    species = {}
    for d in detections:
        name = d["species"]
        if name not in species:
            species[name] = {"species": name, "count": 0, "max_confidence": 0}
        species[name]["count"] += 1
        species[name]["max_confidence"] = max(species[name]["max_confidence"], d["confidence"])
    return sorted(species.values(), key=lambda s: s["count"], reverse=True)
