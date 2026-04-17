# ============================================================
# CMS Makefile
# Engine terpisah dari flask/sekda. Dependensi: /home/databoks/flask
# ============================================================

USER := $(shell whoami)
FLASK_ENV := /home/databoks/flask/.env
include $(FLASK_ENV)

GITTOKEN = $(shell python3 /home/databoks/flask/razan/get_gittoken.py 2>/dev/null)

COMPOSE_FILE = docker/cms.yml
PROJECT_NAME = cms
DC = docker compose --env-file $(FLASK_ENV) -f $(COMPOSE_FILE) -p $(PROJECT_NAME)

# ---- Preflight ----
check:
	@if [ ! -d /home/databoks/flask/razan ]; then \
		echo "[FATAL] /home/databoks/flask/razan tidak ada. CMS butuh flask sebagai core."; exit 1; \
	fi
	@if [ ! -f $(FLASK_ENV) ]; then \
		echo "[FATAL] $(FLASK_ENV) tidak ada."; exit 1; \
	fi
	@echo "[OK] Flask core tersedia: /home/databoks/flask/razan"

# ---- Docker Commands ----
up: check
	$(DC) up -d
	@echo ""
	@echo "=========================================="
	@echo "  Menunggu CMS ready..."
	@echo "=========================================="
	@MAX=90; i=0; \
	while [ $$i -lt $$MAX ]; do \
		STATUS=$$(docker inspect --format='{{.State.Health.Status}}' cms 2>/dev/null || echo "starting"); \
		if [ "$$STATUS" = "healthy" ]; then \
			echo ""; \
			echo "  CMS UP & RUNNING"; \
			echo "  http://localhost:8879"; \
			echo "  (startup: $${i}s)"; \
			echo "=========================================="; \
			break; \
		fi; \
		printf "\r  [%2ds] status: %-12s" $$i "$$STATUS"; \
		sleep 1; \
		i=$$((i + 1)); \
	done; \
	if [ $$i -ge $$MAX ]; then \
		echo ""; \
		echo "  TIMEOUT setelah $${MAX}s - cek logs:"; \
		echo "  make logs"; \
		echo "=========================================="; \
		exit 1; \
	fi
	@$(DC) logs -f --tail=50

down:
	$(DC) down
	@docker rm -f cms 2>/dev/null || true

rr:
	$(DC) down
	@docker rm -f cms 2>/dev/null || true
	@$(MAKE) up

logs:
	$(DC) logs -f --tail=100

bash:
	docker exec -it cms bash

build:
	$(DC) build --no-cache

# ---- Local Development ----
dev: check
	PYTHONPATH=/home/databoks/flask flask --app app run -h 0.0.0.0 -p 8879 --with-threads --reload

# ---- Status ----
status:
	@echo "=========================================="
	@echo "  CMS Status"
	@echo "=========================================="
	@STATUS=$$(docker inspect --format='{{.State.Health.Status}}' cms 2>/dev/null || echo "not running"); \
	UPTIME=$$(docker inspect --format='{{.State.StartedAt}}' cms 2>/dev/null || echo "-"); \
	echo "  Container : cms"; \
	echo "  Health    : $$STATUS"; \
	echo "  Started   : $$UPTIME"; \
	echo "  Port      : 8879"; \
	echo "  URL       : http://localhost:8879"; \
	echo "  Flask core: /home/databoks/flask (bind-mount ro)"; \
	echo "=========================================="
	@$(DC) ps

# ---- DB Schema ----
init-schema:
	@echo "=== Init CMS schema (dsc/databoks) ==="
	@PYTHONPATH=/home/databoks/flask python3 scripts/init_schema.py

init-schema-docker:
	@docker exec cms python3 -u /home/databoks/cms/scripts/init_schema.py

drop-schema:
	@echo "=== DROP CMS tables (IRREVERSIBLE) ==="
	@read -p "Ketik 'yes' untuk lanjut: " ans && [ "$$ans" = "yes" ] || exit 1
	@PYTHONPATH=/home/databoks/flask python3 scripts/init_schema.py --drop

# ---- Git Commands ----
pull:
	git pull $(GITTOKEN)
	@git log -6 --pretty=format:"%h | %ad | %s" --date=format:"%Y-%m-%d %H:%M"

cmd:
	git commit -am "$m" --author="agusdd <agusdwidarmawan@gmail.com>"
	git push $(GITTOKEN)

cal:
	git add .
	git commit -am "$m" --author="agusdd <agusdwidarmawan@gmail.com>"
	git push $(GITTOKEN)

# Catch extra args so make doesn't error on them
%:
	@:

.PHONY: check up down rr logs bash build dev status init-schema init-schema-docker drop-schema pull cmd cal
