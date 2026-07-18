## Health Stack

- typecheck: tsc --noEmit
- typecheck-python: mypy python/
- lint: eslint .
- test: vitest run
- test-python: cd python && pytest -x --tb=short
- test-e2e: npx playwright test
