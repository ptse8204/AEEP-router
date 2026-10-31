include Makefile

docs-lint:
	/usr/local/bin/node /Users/edwintse/.npm/_npx/3158f213c58abe1a/node_modules/markdownlint-cli2/markdownlint-cli2-bin.mjs --config .markdownlint-cli2.jsonc --no-globs $(DOCS_FILES)
