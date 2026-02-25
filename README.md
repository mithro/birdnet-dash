# birdnet-dash

Static HTML dashboard that aggregates bird detection data from multiple
[BirdNET-Pi](https://github.com/mcguirepr89/BirdNET-Pi) instances.

Live at **[birds.mithis.com](https://birds.mithis.com)**.

> **Fair warning:** This is a personal vibe-coded project, built quickly with
> Claude Code to scratch my own itch. It is not designed for reuse, has no
> tests, makes plenty of assumptions about my specific network, and may change
> or break without notice. You're welcome to look around, borrow ideas, or
> fork it, but don't expect documentation, support, or stability.

## What it does

- Probes each BirdNET-Pi site across multiple network interfaces (IPv4/IPv6,
  eth0/wlan0) to find the best reachable host
- Scrapes detection stats and recent bird sightings from each site's web UI
- Tracks species history to detect new species and highlight recent discoveries
- Renders a single self-contained HTML page with embedded CSS (no JS)
- Regenerates every 5 minutes via cron

## Architecture

```
cron (every 5 min)
  └─ birdsnet-dash generate
       ├─ healthcheck: probe interfaces, pick best host
       ├─ scrape: fetch stats + detections from BirdNET-Pi HTML
       ├─ generate: render Jinja2 template → site/index.html
       └─ species tracking: update data/species_seen.json
```

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

## Usage

```bash
uv sync
uv run birdsnet-dash generate --output-dir ./site --data-dir ./data
```

## License

[Apache 2.0](LICENSE)
