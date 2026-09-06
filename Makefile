.PHONY: dev-up stage-up prod-up down-dev down-stage down-prod

COMPOSE_DEV = docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE_STAGE = docker compose --env-file .env.stage -f docker-compose.yml -f docker-compose.stage.yml
COMPOSE_PROD = docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml

dev-up:
	$(COMPOSE_DEV) up --build

stage-up:
	$(COMPOSE_STAGE) up --build -d

prod-up:
	$(COMPOSE_PROD) up --build -d

down-dev:
	$(COMPOSE_DEV) down

down-stage:
	$(COMPOSE_STAGE) down

down-prod:
	$(COMPOSE_PROD) down
