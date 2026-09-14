.PHONY: run test coverage lint

run:
	.venv/bin/python -m app

test:
	.venv/bin/python -m pytest -q

coverage:
	.venv/bin/python -m pytest --cov=app --cov-report=term-missing

lint:
	.venv/bin/ruff check .
