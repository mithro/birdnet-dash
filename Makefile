VENV := .venv
INSTALL_DIR := /opt/birdsnet-dash
# Full path: `uv` lives in /usr/local/bin, which is not on root's PATH under sudo.
UV := $(shell command -v uv)
# Pin to the system default python so a `python3.N` removal by
# unattended-upgrades doesn't orphan the venv (it did on 2026-08-28).
PYTHON := /usr/bin/python3
# DNS for birds.mithis.com is NOT installed from here: since 2026-09-20 it is
# a signed pdns zone on ten64 (etckeeper 8a77ce12), managed with the rest of
# the site DNS in ~/local/net/.

$(VENV)/.stamp: pyproject.toml
	uv sync
	touch $@

.PHONY: setup
setup: $(VENV)/.stamp

.PHONY: generate
generate: $(VENV)/.stamp
	$(VENV)/bin/birdsnet-dash generate

.PHONY: install
install:  ## Install to /opt/birdsnet-dash with uv venv + config files
	sudo mkdir -p $(INSTALL_DIR)/site $(INSTALL_DIR)/data
	# --allow-existing: site/, data/, templates/, static/ share the prefix.
	# Re-running is what recovers from an orphaned venv (python upgrade).
	sudo $(UV) venv --allow-existing --python $(PYTHON) $(INSTALL_DIR)
	sudo $(UV) pip install --python $(INSTALL_DIR)/bin/python .
	sudo cp -r templates $(INSTALL_DIR)/
	sudo cp -r static $(INSTALL_DIR)/
	# Install config files
	sudo cp etc/nginx/birds.mithis.com.conf /etc/nginx/sites-available/
	sudo ln -sf /etc/nginx/sites-available/birds.mithis.com.conf /etc/nginx/sites-enabled/
	sudo cp etc/cron.d/birdsnet-dash /etc/cron.d/
	# Generate initial site (also proves the venv's interpreter works)
	sudo $(INSTALL_DIR)/bin/birdsnet-dash generate --output-dir $(INSTALL_DIR)/site
	# Reload services
	sudo nginx -t && sudo systemctl reload nginx
	# /etc is etckeeper-managed: never leave it dirty
	sudo etckeeper commit "birdsnet-dash: make install" || true
