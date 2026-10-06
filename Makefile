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
# (dulu `rx7` alias target ini; sejak 2026-10-06 rx7 = start/restart panel super-admin, lihat bawah)
stack:
	bash scripts/collab_deploy.sh

# restart cepat app+worker (:8879) tanpa build/skema; mysql & redis TIDAK disentuh.
# ganti kode perlu image baru -> tetap 'make stack'.
stack-restart rr:
	$(DC) restart app worker
	@sleep 2; curl -s http://127.0.0.1:8879/health || echo "app belum menjawab (cek: make stack-logs)"; echo

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

# ---- Control panel super-admin multi-tenant (cmspanel, 127.0.0.1:8895) ----
# PANEL_BIND: default loopback; dari PC pakai `make panel-tunnel`, atau nyalakan dgn IP VPN:
#   make rx7 PANEL_BIND=10.100.10.29   (JANGAN 0.0.0.0 — panel memegang kendali docker)
PANEL_BIND ?= 127.0.0.1
# Password dibuat otomatis sekali di ~/.cms_panel_pass (chmod 600). Akses dari PC: make panel-tunnel.
panel:
	@test -f $(HOME)/.cms_panel_pass || { umask 077; openssl rand -hex 16 > $(HOME)/.cms_panel_pass; echo "[OK] password panel baru: $(HOME)/.cms_panel_pass"; }
	@echo "Panel: http://127.0.0.1:8895  (password: cat ~/.cms_panel_pass)"
	@PANEL_PASSWORD=$$(cat $(HOME)/.cms_panel_pass) PYTHONPATH=$(CURDIR) python3 -m cmspanel.panel

# PANEL_HOST = alias/IP ssh mesin tempat panel jalan (mis. databoks MiniPC); default dbscraping
PANEL_HOST ?= dbscraping
panel-tunnel:
	ssh -N -L 8895:127.0.0.1:8895 $(PANEL_HOST)

# daftarkan stack lama :8879 sbg tenant pertama di panel (tanpa mengubah stacknya)
panel-adopt:
	bash scripts/adopt-legacy-tenant.sh utama

# rx7 = nyalakan panel super-admin di background (belum jalan -> start; sudah jalan -> restart otomatis).
rx7:
	@test -f $(HOME)/.cms_panel_pass || { umask 077; openssl rand -hex 16 > $(HOME)/.cms_panel_pass; echo "[OK] password panel baru dibuat: ~/.cms_panel_pass"; }
	@PYTHONPATH=$(CURDIR) python3 -m cmspanel.panel --kill; sleep 1
	@PANEL_PASSWORD=$$(cat $(HOME)/.cms_panel_pass) PYTHONPATH=$(CURDIR) PANEL_BIND=$(PANEL_BIND) \
	nohup python3 -m cmspanel.panel > $(HOME)/.cms_panel.log 2>&1 & \
	sleep 2; \
	if curl -sf -o /dev/null http://$(PANEL_BIND):8895/login; then \
	  echo "[OK] panel jalan: http://$(PANEL_BIND):8895  (password: cat ~/.cms_panel_pass | log: ~/.cms_panel.log)"; \
	else echo "[FATAL] panel gagal start:"; tail -5 $(HOME)/.cms_panel.log; exit 1; fi

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

# ---- Claude CLI di container (lintas repo: flask, cms, sekda, newflask, diskusidata) ----
# File dibuat dgn uid/gid host (bukan root). Login tersimpan di volume claude-home.
CLAUDEDOCKER ?= cms-claude
# Env terminal diteruskan ke container: TERM asli host + locale UTF-8 (tanpa ini karakter aneh/escape bocor saat scroll)
TTYENV = -e TERM=$${TERM:-xterm-256color} -e COLORTERM=truecolor -e LANG=C.UTF-8 -e LC_ALL=C.UTF-8
CLAUDE_DC = HOST_HOME=$(HOME) HOST_UID=$(shell id -u) HOST_GID=$(shell id -g) docker compose -f docker/claude.yml -p cms-claude

cbuild:
	$(CLAUDE_DC) build cms-claude

cup:
	$(CLAUDE_DC) up -d cms-claude

cdown:
	$(CLAUDE_DC) stop cms-claude

clog:
	docker logs -f --tail=100 $(CLAUDEDOCKER)

csh:
	docker exec -it -w $(HOME)/$(d) -u $(shell id -u):$(shell id -g) -e HOME=$(HOME) $(TTYENV) $(CLAUDEDOCKER) bash -l

# clogin: jalankan Claude di container. Folder kerja = repo yg dipilih (memori Claude per folder!):
#   make clogin            → ~/cms        make clogin d=flask|sekda|newflask|diskusidata
d ?= cms
clogin:
	docker exec -it -w $(HOME)/$(d) -u $(shell id -u):$(shell id -g) -e HOME=$(HOME) -e CLAUDE_CONFIG_DIR=/claude-home/.claude $(TTYENV) $(CLAUDEDOCKER) claude --dangerously-skip-permissions

# Pintasan per repo: make csekda · cflask · cnewflask · cdiskusidata · ccms
csekda:
	@$(MAKE) --no-print-directory clogin d=sekda
cflask:
	@$(MAKE) --no-print-directory clogin d=flask
cnewflask:
	@$(MAKE) --no-print-directory clogin d=newflask
cdiskusidata:
	@$(MAKE) --no-print-directory clogin d=diskusidata
ccms:
	@$(MAKE) --no-print-directory clogin d=cms

# Catch extra args so make doesn't error on them
%:
	@:

.PHONY: push stack stack-restart rr rx7 stack-down stack-logs stack-status stack-bash dev tunnel init-schema drop-schema pull cmd cal ovpn ovpn-stop ovpn-status cbuild cup cdown clog csh clogin csekda cflask cnewflask cdiskusidata ccms
