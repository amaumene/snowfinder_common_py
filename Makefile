.PHONY: deps test clean

deps:
	rm -rf venv
	uv venv venv
	uv pip install --python venv/bin/python --upgrade -e ".[dev]"

test:
	./venv/bin/python -m pytest tests/

clean:
	rm -rf venv
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
