.PHONY: install test coverage schemas schemas-check build clean docs-lint docs-links docs-check

# One scope for both checks. Historical evidence and packaged skills stay untouched.
DOCS_FILES := README.md AGENTS.md CLAUDE.md CONTRIBUTING.md CODE_OF_CONDUCT.md \
	ARCHITECTURE.md SPEC.md SECURITY.md \
	$(filter-out docs/ASSESSMENT_TESTING.md docs/ROADMAP_0.7.md,$(wildcard docs/*.md)) \
	docs/media/README.md $(wildcard docs/protocol/*.md) \
	$(wildcard examples/*/README.md integrations/*/README.md)
LYCHEE ?= lychee

docs-lint:
	npx --yes markdownlint-cli2@0.23.3 --config .markdownlint-cli2.jsonc --no-globs $(DOCS_FILES)

docs-links:
	@test "$$($(LYCHEE) --version)" = "lychee 0.24.2" || { echo "docs-links requires lychee 0.24.2; see CONTRIBUTING.md"; exit 1; }
	$(LYCHEE) --config .lychee.toml $(DOCS_FILES)

docs-check: docs-lint docs-links

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
