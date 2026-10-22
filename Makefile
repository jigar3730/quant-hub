.PHONY: dev-up stage-up prod-up down-dev down-stage down-prod test lint

# Delegate to run_env.sh so the compose project name (quant-hub-<env>) is
# always set; bare `docker compose` here would target project `quant-hub`.
dev-up:
	./scripts/run_env.sh dev up --build -d

stage-up:
	./scripts/run_env.sh stage up --build -d

prod-up:
	./scripts/run_env.sh prod up --build -d

down-dev:
	./scripts/run_env.sh dev down

down-stage:
	./scripts/run_env.sh stage down

down-prod:
	./scripts/run_env.sh prod down

test:
	docker exec quant-hub-dev pytest -q

lint:
	docker exec quant-hub-frontend-dev npx tsc -b
	docker exec quant-hub-frontend-dev npm run lint
