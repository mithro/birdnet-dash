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
# /etc paths (relative to /etc) that install-config owns and commits.
ETC_PATHS := nginx/sites-available/birds.mithis.com.conf \
	nginx/sites-enabled/birds.mithis.com.conf cron.d/birdsnet-dash

$(VENV)/.stamp: pyproject.toml
	uv sync
	touch $@

.PHONY: setup
setup: $(VENV)/.stamp

.PHONY: generate
generate: $(VENV)/.stamp
	$(VENV)/bin/birdsnet-dash generate

# Two halves, so a code change doesn't touch system config:
#   make install-app     code/template change: venv + package + templates/static,
#                        then one generate run. Touches only $(INSTALL_DIR);
#                        the cron job picks up the new code on its next tick.
#   make install-config  nginx site + cron job into /etc, reload nginx,
#                        etckeeper commit. Only needed when etc/ changes.
#   make install         both (first install, or to resync everything).

.PHONY: install
install: install-app install-config  ## Full install: app + system config

.PHONY: install-app
install-app:  ## Install/upgrade the app in /opt/birdsnet-dash (no /etc changes)
	sudo mkdir -p $(INSTALL_DIR)/site $(INSTALL_DIR)/data
	# --allow-existing: site/, data/, templates/, static/ share the prefix.
	# Re-running is what recovers from an orphaned venv (python upgrade).
	sudo $(UV) venv --allow-existing --python $(PYTHON) $(INSTALL_DIR)
	sudo $(UV) pip install --python $(INSTALL_DIR)/bin/python .
	sudo cp -r templates $(INSTALL_DIR)/
	sudo cp -r static $(INSTALL_DIR)/
	# Generate the site now (also proves the venv's interpreter works)
	sudo $(INSTALL_DIR)/bin/birdsnet-dash generate --output-dir $(INSTALL_DIR)/site

.PHONY: install-config
install-config:  ## Install nginx + cron config into /etc and reload nginx
	sudo cp etc/nginx/birds.mithis.com.conf /etc/nginx/sites-available/
	sudo ln -sf /etc/nginx/sites-available/birds.mithis.com.conf /etc/nginx/sites-enabled/
	sudo cp etc/cron.d/birdsnet-dash /etc/cron.d/
	sudo nginx -t
	sudo systemctl reload nginx
	# /etc is etckeeper-managed: commit only our paths (`-- paths`), never
	# sweep in unrelated pending /etc changes as `etckeeper commit` would.
	sudo etckeeper vcs add -A -- $(ETC_PATHS)
	sudo etckeeper vcs diff --cached --quiet -- $(ETC_PATHS) || \
		sudo etckeeper vcs commit --no-verify -m "birdsnet-dash: make install-config" \
		-- $(ETC_PATHS)
