from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import httpx

from birdsnet_dash.config import INTERFACES, SITES
from birdsnet_dash.scrape import (
    build_species_summary,
    fetch_detections,
    fetch_species_list,
    fetch_stats,
)


def check_host(hostname: str) -> bool:
    """Probe a BirdNET-Pi host by hostname. Returns True if reachable."""
    try:
        resp = httpx.get(f"https://{hostname}/", timeout=3, verify=False)
        return resp.status_code < 500
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return False


def longest_common_suffix(hostnames: list[str]) -> str:
    """Find the longest common DNS suffix of a list of hostnames.

    >>> longest_common_suffix([])
    ''
    >>> longest_common_suffix(["ipv4.wlan0.foo.com"])
    'ipv4.wlan0.foo.com'
    >>> longest_common_suffix(["ipv4.wlan0.foo.com", "ipv6.wlan0.foo.com"])
    'wlan0.foo.com'
    >>> longest_common_suffix(["ipv4.eth0.foo.com", "ipv4.wlan0.foo.com"])
    'foo.com'
    >>> longest_common_suffix(["ipv4.eth0.a.com", "ipv6.eth0.a.com", "ipv4.wlan0.a.com", "ipv6.wlan0.a.com"])
    'a.com'
    >>> longest_common_suffix(["a.example.com", "b.other.com"])
    'com'
    >>> longest_common_suffix(["foo.com", "bar.net"])
    ''
    """
    if not hostnames:
        return ""
    if len(hostnames) == 1:
        return hostnames[0]
    split = [h.split(".") for h in hostnames]
    reversed_labels = [list(reversed(labels)) for labels in split]
    common = []
    for labels in zip(*reversed_labels):
        if len(set(labels)) == 1:
            common.append(labels[0])
        else:
            break
    return ".".join(reversed(common))


def pick_best_host(site: dict) -> str | None:
    """Pick the best hostname from reachable interfaces.

    Uses the longest common DNS suffix of all reachable interface hostnames.

    >>> pick_best_host({"interfaces": {
    ...     "ipv4.eth0": {"hostname": "ipv4.eth0.h.com", "up": True},
    ...     "ipv6.eth0": {"hostname": "ipv6.eth0.h.com", "up": True},
    ...     "ipv4.wlan0": {"hostname": "ipv4.wlan0.h.com", "up": True},
    ...     "ipv6.wlan0": {"hostname": "ipv6.wlan0.h.com", "up": True},
    ... }})
    'h.com'
    >>> pick_best_host({"interfaces": {
    ...     "ipv4.eth0": {"hostname": "ipv4.eth0.h.com", "up": False},
    ...     "ipv6.eth0": {"hostname": "ipv6.eth0.h.com", "up": False},
    ...     "ipv4.wlan0": {"hostname": "ipv4.wlan0.h.com", "up": True},
    ...     "ipv6.wlan0": {"hostname": "ipv6.wlan0.h.com", "up": True},
    ... }})
    'wlan0.h.com'
    >>> pick_best_host({"interfaces": {
    ...     "ipv4.eth0": {"hostname": "ipv4.eth0.h.com", "up": False},
    ...     "ipv6.eth0": {"hostname": "ipv6.eth0.h.com", "up": False},
    ...     "ipv4.wlan0": {"hostname": "ipv4.wlan0.h.com", "up": True},
    ...     "ipv6.wlan0": {"hostname": "ipv6.wlan0.h.com", "up": False},
    ... }})
    'ipv4.wlan0.h.com'
    >>> pick_best_host({"interfaces": {
    ...     "ipv4.eth0": {"hostname": "ipv4.eth0.h.com", "up": False},
    ...     "ipv6.eth0": {"hostname": "ipv6.eth0.h.com", "up": False},
    ...     "ipv4.wlan0": {"hostname": "ipv4.wlan0.h.com", "up": False},
    ...     "ipv6.wlan0": {"hostname": "ipv6.wlan0.h.com", "up": False},
    ... }}) is None
    True
    """
    up_hostnames = [
        iface["hostname"]
        for iface in site["interfaces"].values()
        if iface["up"]
    ]
    return longest_common_suffix(up_hostnames) or None


def _check_site(site: dict) -> dict:
    """Check one site: probe interfaces, scrape bird data if reachable."""
    host = site["host"]

    # Probe all interfaces concurrently
    interfaces = {}
    with ThreadPoolExecutor(max_workers=len(INTERFACES)) as pool:
        futures = {}
        for iface in INTERFACES:
            fqdn = f"{iface}.{host}"
            futures[pool.submit(check_host, fqdn)] = (iface, fqdn)
        for future in as_completed(futures):
            iface, fqdn = futures[future]
            interfaces[iface] = {"hostname": fqdn, "up": future.result()}

    result = {**site, "interfaces": interfaces}
    best_host = pick_best_host(result)
    result["best_host"] = best_host

    if not best_host:
        result["stats"] = None
        result["detections"] = []
        result["species"] = []
        result["yesterday_species"] = []
        return result

    # Fetch stats, species list, detections, and yesterday list concurrently
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_stats = pool.submit(fetch_stats, best_host)
        f_species = pool.submit(fetch_species_list, best_host)
        f_detect = pool.submit(fetch_detections, best_host, 20)
        f_yester = pool.submit(fetch_species_list, best_host, yesterday)

    result["stats"] = f_stats.result()
    species_names = f_species.result()
    detections = f_detect.result()
    result["detections"] = detections
    yesterday_names = f_yester.result()

    # Build species summaries (metadata fetches parallelised internally)
    result["species"] = build_species_summary(
        species_names, detections, hostname=best_host
    )
    result["yesterday_species"] = build_species_summary(
        yesterday_names, [], hostname=best_host
    )
    return result


def check_all_sites() -> list[dict]:
    """Check all interfaces for each site, then scrape bird data from reachable ones."""
    with ThreadPoolExecutor(max_workers=len(SITES)) as pool:
        futures = {pool.submit(_check_site, site): site["slug"] for site in SITES}
        results_by_slug = {}
        for future in as_completed(futures):
            slug = futures[future]
            results_by_slug[slug] = future.result()
    # Preserve original site order
    return [results_by_slug[site["slug"]] for site in SITES]
