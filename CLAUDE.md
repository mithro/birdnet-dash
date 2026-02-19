# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BirdNET-Pi aggregator dashboard that scrapes bird detection data from multiple BirdNET-Pi instances and generates a static HTML dashboard. Deployed to birds.mithis.com, regenerated every 5 minutes via cron.

## Common Commands

```bash
# Install dependencies (uses uv package manager)
make setup

# Generate the dashboard (outputs to ./site/)
make generate

# Run directly with options
.venv/bin/birdsnet-dash generate --output-dir ./site

# Lint
uv run ruff check src/
uv run ruff format --check src/

# Deploy to /opt/birdsnet-dash (requires sudo, installs configs for nginx/dnsmasq/cron)
make install
```

## Architecture

**Data flow:** `cli.py` → `healthcheck.py` (probe hosts) → `scrape.py` (fetch HTML, parse stats/detections) → `generate.py` (render Jinja2 template → atomic write to `site/index.html`)

Key modules in `src/birdsnet_dash/`:
- **cli.py** — Entry point. Single `generate` subcommand.
- **config.py** — Hardcoded site list (Welland Front, Welland Back, Monarto) with hostnames/slugs, and network interface prefixes to probe.
- **healthcheck.py** — Probes each site across multiple interface prefixes (ipv4/ipv6, eth0/wlan0) via HTTPS with 3s timeout. `pick_best_host()` selects first reachable interface.
- **scrape.py** — Regex-based HTML parsing of BirdNET-Pi pages. Extracts stats tables and detection rows. `build_species_summary()` aggregates by species.
- **generate.py** — Finds Jinja2 templates (checks both installed and dev layouts), renders `index.html.j2`, writes atomically via temp file + rename.

**Template:** `templates/index.html.j2` — Self-contained HTML with embedded CSS. Responsive flexbox layout showing per-site cards with stats, species summaries, and recent detections.

## Code Style

- Python 3.11+, type hints throughout
- Ruff for linting (rules: E, F, W, I) with 100-char line length
- Build backend: hatchling; package manager: uv
- Docstrings include doctests in scrape.py and healthcheck.py
