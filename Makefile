.PHONY: install test coverage schemas schemas-check build clean

install:
	python -m pip install -e '.[dev,http-server]'

test:
	pytest

coverage:
	coverage erase
	coverage run -m pytest
	coverage report -m

schemas:
	PYTHONPATH=src python scripts/generate_schemas.py

schemas-check:
	PYTHONPATH=src python scripts/generate_schemas.py --check

build: schemas-check
	python -m build

clean:
	rm -rf build dist .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
