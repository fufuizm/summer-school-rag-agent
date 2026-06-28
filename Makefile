.PHONY: venv install install-dev test api web docker-up docker-down

PYTHON ?= $(CURDIR)/.venv/bin/python

venv:
	python3.11 -m venv .venv

install: venv
	$(PYTHON) -m pip install -r requirements.txt

install-dev: venv
	$(PYTHON) -m pip install -r requirements-dev.txt

test:
	SUMMER_RAG_FORCE_FALLBACK=1 $(PYTHON) -m pytest -v

api:
	cd backend && SUMMER_RAG_FORCE_FALLBACK=1 $(PYTHON) -m uvicorn main:app --reload --port 8000

web:
	cd frontend && $(PYTHON) -m http.server 3000

docker-up:
	docker compose up --build

docker-down:
	docker compose down
