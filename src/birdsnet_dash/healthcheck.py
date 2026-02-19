import httpx

from birdsnet_dash.config import INTERFACES, SITES


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


def pick_iframe_host(site: dict) -> str | None:
    """Pick the best hostname for the iframe.

    Uses the longest common DNS suffix of all reachable interface hostnames.

    >>> pick_iframe_host({"interfaces": {
    ...     "ipv4.eth0": {"hostname": "ipv4.eth0.h.com", "up": True},
    ...     "ipv6.eth0": {"hostname": "ipv6.eth0.h.com", "up": True},
    ...     "ipv4.wlan0": {"hostname": "ipv4.wlan0.h.com", "up": True},
    ...     "ipv6.wlan0": {"hostname": "ipv6.wlan0.h.com", "up": True},
    ... }})
    'h.com'
    >>> pick_iframe_host({"interfaces": {
    ...     "ipv4.eth0": {"hostname": "ipv4.eth0.h.com", "up": False},
    ...     "ipv6.eth0": {"hostname": "ipv6.eth0.h.com", "up": False},
    ...     "ipv4.wlan0": {"hostname": "ipv4.wlan0.h.com", "up": True},
    ...     "ipv6.wlan0": {"hostname": "ipv6.wlan0.h.com", "up": True},
    ... }})
    'wlan0.h.com'
    >>> pick_iframe_host({"interfaces": {
    ...     "ipv4.eth0": {"hostname": "ipv4.eth0.h.com", "up": False},
    ...     "ipv6.eth0": {"hostname": "ipv6.eth0.h.com", "up": False},
    ...     "ipv4.wlan0": {"hostname": "ipv4.wlan0.h.com", "up": True},
    ...     "ipv6.wlan0": {"hostname": "ipv6.wlan0.h.com", "up": False},
    ... }})
    'ipv4.wlan0.h.com'
    >>> pick_iframe_host({"interfaces": {
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


def check_all_sites() -> list[dict]:
    """Check all interfaces for each site. Returns sites with health status per interface."""
    results = []
    for site in SITES:
        host = site["host"]
        interfaces = {}
        for iface in INTERFACES:
            fqdn = f"{iface}.{host}"
            interfaces[iface] = {"hostname": fqdn, "up": check_host(fqdn)}
        result = {**site, "interfaces": interfaces}
        result["iframe_host"] = pick_iframe_host(result)
        results.append(result)
    return results
