VENV := .venv
INSTALL_DIR := /opt/birdsnet-dash

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
	sudo mkdir -p $(INSTALL_DIR)/site
	sudo uv venv --allow-existing $(INSTALL_DIR)
	sudo uv pip install --python $(INSTALL_DIR)/bin/python .
	sudo cp -r templates $(INSTALL_DIR)/
	# Install config files
	sudo cp etc/nginx/birds.mithis.com.conf /etc/nginx/sites-available/
	sudo ln -sf /etc/nginx/sites-available/birds.mithis.com.conf /etc/nginx/sites-enabled/
	sudo cp etc/dnsmasq/birds.conf /etc/dnsmasq.d/internal/
	sudo cp etc/cron.d/birdsnet-dash /etc/cron.d/
	# Generate initial site
	sudo $(INSTALL_DIR)/bin/birdsnet-dash generate --output-dir $(INSTALL_DIR)/site
	# Reload services
	sudo nginx -t && sudo systemctl reload nginx
	sudo systemctl restart dnsmasq@internal
