# Prativimb. Run `make help` for the list of targets.
PY ?= .venv/bin/python
NPM ?= npm

.PHONY: help setup data twin train report all test api web build-web serve screenshots docs check demo docker-up clean

help:
	@echo "setup        create .venv (Python 3.11), install Python and dashboard dependencies"
	@echo "all          regenerate synthetic data, calibrate twins, train models, write reports (about 5 min)"
	@echo "data         regenerate synthetic data only (about 20 s)"
	@echo "train        twins, glucose and cardio models, report (needs data)"
	@echo "test         run the pytest suite"
	@echo "api          start the API on :8000 (replay clock running at 10x)"
	@echo "web          start the dashboard dev server on :5173 (needs api)"
	@echo "serve        build the dashboard and serve everything from the API on :8000"
	@echo "screenshots  capture every screen into docs/screenshots (needs api and web)"
	@echo "docs         architecture diagram and slides (PPTX and PDF) from the latest metrics"
	@echo "check        fail if any em dash, en dash or emoji is in the repository"
	@echo "docker-up    one command start with Docker Compose (dashboard on :8080)"

setup:
	@command -v uv >/dev/null 2>&1 && uv venv .venv --python 3.11 --allow-existing || python3.11 -m venv .venv
	@command -v uv >/dev/null 2>&1 && uv pip install --python $(PY) -e ".[dev,docs]" || $(PY) -m pip install -e ".[dev,docs]"
	cd frontend && $(NPM) ci
	$(PY) -m playwright install chromium

all:
	$(PY) -m prativimb.pipeline all

data:
	$(PY) -m prativimb.pipeline data

train:
	$(PY) -m prativimb.pipeline train

report:
	$(PY) -m prativimb.pipeline report

test:
	$(PY) -m pytest

api:
	$(PY) -m uvicorn prativimb.api.main:app --host 127.0.0.1 --port 8000

web:
	cd frontend && $(NPM) run dev

build-web:
	cd frontend && $(NPM) run build

serve: build-web
	$(PY) -m uvicorn prativimb.api.main:app --host 127.0.0.1 --port 8000

screenshots:
	$(PY) scripts/screenshots.py

docs:
	$(PY) scripts/make_architecture.py
	$(PY) scripts/make_slides.py

check:
	$(PY) scripts/check_style.py

demo: all build-web
	PRATIVIMB_SPEED=10 $(PY) -m uvicorn prativimb.api.main:app --host 127.0.0.1 --port 8000

docker-up:
	docker compose up --build

clean:
	rm -rf data artifacts frontend/dist
