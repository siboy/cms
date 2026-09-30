# ============================================================
# CMS Makefile (CMS kolaborasi: cmsapp + MySQL + Redis + worker)
# Stack Docker mandiri (docker/collab.yml), TIDAK lagi memakai container
# flask. ~/flask hanya dipakai untuk token git (GITTOKEN) dan init-schema
# jalur razan (opsional).
# ============================================================

FLASK_DIR := $(HOME)/flask
GITTOKEN = $(shell python3 $(FLASK_DIR)/razan/get_gittoken.py 2>/dev/null)

COLLAB_DIR ?= $(HOME)/cms-collab
DC = docker compose -f $(COLLAB_DIR)/collab.yml --env-file $(COLLAB_DIR)/.env

# ---- Stack Docker (mysql + redis + app + worker) ----
# Idempoten: build image, terapkan skema, up. Bisa di server maupun PC (default ~/cms-collab).
stack:
	bash scripts/collab_deploy.sh

stack-down:
	$(DC) down

stack-logs:
	$(DC) logs -f --tail=100 app worker

stack-status:
	@$(DC) ps
	@curl -s http://127.0.0.1:8879/health || echo "app tidak menjawab"; echo

stack-bash:
	docker exec -it cms-app bash

# ---- Dev lokal (hot-reload, port 8880) ----
# Memakai MySQL/Redis dari stack ($(COLLAB_DIR): port 127.0.0.1:3307 / 6380); sandi dibaca dari $(COLLAB_DIR)/.env.
# Di PC: buka tunnel dulu (make tunnel) atau jalankan langsung di server.
dev:
	@test -f $(COLLAB_DIR)/.env || { echo "[FATAL] $(COLLAB_DIR)/.env tidak ada - jalankan 'make stack' dulu"; exit 1; }
	@set -a; . $(COLLAB_DIR)/.env; set +a; \
	CMS_DB_HOST=127.0.0.1 CMS_DB_PORT=3307 CMS_DB_USER=cms CMS_DB_PASS=$$MYSQL_PASSWORD \
	CMS_REDIS_URL=redis://:$$REDIS_PASSWORD@127.0.0.1:6380/0 \
	CMS_DATA_DIR=$(CURDIR)/data CMS_EXPORT_DIR=$(CURDIR)/data/exports PYTHONPATH=$(CURDIR) \
	gunicorn -k gevent -w 1 --reload -b 0.0.0.0:8880 --timeout 120 "cmsapp:create_app()"

tunnel:
	ssh -N -L 3307:127.0.0.1:3307 -L 6380:127.0.0.1:6380 dbscraping

# ---- DB Schema ----
# Skema utama diterapkan otomatis oleh 'make stack'. Target di bawah = jalur razan (~/flask), opsional.
init-schema:
	@PYTHONPATH=$(FLASK_DIR) python3 scripts/init_schema.py

drop-schema:
	@echo "=== DROP semua tabel CMS (IRREVERSIBLE) ==="
	@read -p "Ketik 'yes' untuk lanjut: " ans && [ "$$ans" = "yes" ] || exit 1
	@PYTHONPATH=$(FLASK_DIR) python3 scripts/init_schema.py --drop

# ---- Git Commands ----
pull:
	@git pull $(GITTOKEN)
	@git log -6 --pretty=format:"%h | %ad | %s" --date=format:"%Y-%m-%d %H:%M"

push:
	@git push $(GITTOKEN)

cmd:
	git commit -am "$m" --author="agusdd <agusdwidarmawan@gmail.com>"
	@git push $(GITTOKEN)

cal:
	git add .
	git commit -am "$m" --author="agusdd <agusdwidarmawan@gmail.com>"
	@git push $(GITTOKEN)

# ---- VPN Management ----
ovpn:
	@echo "=========================================="
	@echo "  Starting 2 VPN tmux sessions..."
	@echo "=========================================="
	@tmux kill-session -t vpn1 2>/dev/null || true
	@tmux kill-session -t vpn2 2>/dev/null || true
	@sleep 1
	@tmux new-session -d -s vpn1 "sudo openvpn --config $(HOME)/cms/data/agus/katadata-data_agus.darmawan_katadata-prod.ovpn"
	@tmux new-session -d -s vpn2 "sudo openvpn --config $(HOME)/cms/data/agus/KATADATA-DEV.ovpn"
	@echo "[OK] VPN sessions started:"
	@echo "  - vpn1: katadata-prod"
	@echo "  - vpn2: KATADATA-DEV"
	@echo ""
	@echo "Attach dengan: tmux attach -t vpn1"
	@echo "               tmux attach -t vpn2"
	@echo "List sessions: tmux ls"
	@echo "=========================================="

ovpn-stop:
	@echo "Stopping VPN sessions..."
	@tmux kill-session -t vpn1 2>/dev/null || echo "vpn1 not running"
	@tmux kill-session -t vpn2 2>/dev/null || echo "vpn2 not running"
	@echo "[OK] VPN sessions stopped"

ovpn-status:
	@echo "=========================================="
	@echo "  VPN Sessions Status"
	@echo "=========================================="
	@tmux ls 2>/dev/null | grep vpn || echo "No VPN sessions running"
	@echo "=========================================="

# Catch extra args so make doesn't error on them
%:
	@:

.PHONY: push stack stack-down stack-logs stack-status stack-bash dev tunnel init-schema drop-schema pull cmd cal ovpn ovpn-stop ovpn-status
