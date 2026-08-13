.PHONY: up down build logs test test-backend test-frontend lint check

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

test: test-backend test-frontend

test-backend:
	docker compose run --rm --no-deps backend python -m pytest tests -q

test-frontend:
	npm ci --prefix frontend
	npm test --prefix frontend -- --run

lint:
	npm run build --prefix frontend
	npm run lint --prefix frontend

check:
	docker compose config --quiet
	docker compose build
	$(MAKE) test
	$(MAKE) lint
