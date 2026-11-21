"""Check every species card link on a generated dashboard names a real species.

Usage: uv run python scripts/check_species_links.py <index.html>

Exits non-zero if any card links to a name the BirdNET-Pi does not know
(e.g. an apostrophe-less folder name, which shows a 0-occurrence page).
"""

import html
import re
import sys
import urllib.parse

from birdsnet_dash.scrape import fetch_species_names

page = open(sys.argv[1]).read()
LINK_RE = r'href="https://([^/"]+)/views\.php\?view=Species\+Stats&(?:amp;)?species=([^"]+)"'
links = re.findall(LINK_RE, page)
known = {}
bad = []
for host, quoted in links:
    name = urllib.parse.unquote(html.unescape(quoted))
    if host not in known:
        known[host] = set(fetch_species_names(host))
        print(f"{host}: {len(known[host])} known species")
    if name not in known[host]:
        bad.append((host, name))
print(f"{len(links)} links checked, {len(bad)} bad")
for host, name in bad:
    print(f"  BAD {host}: {name!r}")
sys.exit(1 if bad or not links else 0)
