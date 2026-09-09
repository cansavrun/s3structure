.PHONY: init up seed down logs test lint build demo-local
DOCKER ?= docker
init:
	python3 scripts/init_env.py
up: init
	$(DOCKER) compose up --build -d --wait
seed:
	$(DOCKER) compose run --rm seed
down:
	$(DOCKER) compose down
logs:
	$(DOCKER) compose logs -f api web
test:
	cd backend && uv run --frozen pytest --cov=app --cov-report=term-missing
	cd frontend && npm test
lint:
	cd backend && uv run --frozen ruff check . && uv run --frozen ruff format --check .
	cd frontend && npm run lint
build:
	$(DOCKER) compose build api web
demo-local:
	python3 scripts/local_demo.py
