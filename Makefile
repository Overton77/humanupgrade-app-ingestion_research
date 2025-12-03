UV := uv
SRC := src
PKG := research_agent

.PHONY: install codegen codegen-clean dev lint format typecheck test check run clean

# Install runtime dependencies only
install:
	$(UV) sync 

# Run Ariadne codegen using the config in pyproject.toml
codegen:
	uv run ariadne-codegen

# Remove the generated client if you want a clean regen
codegen-clean:
	rm -rf src/graphql_client

# Install runtime + dev dependencies (pytest, ruff, black, mypy, etc.)
dev:
	$(UV) sync --group dev

# Run the linter (Ruff)
lint:
	$(UV) run ruff check $(SRC)

# Auto-fix with Ruff, then format with Black
format:
	$(UV) run ruff check $(SRC) --fix
	$(UV) run black $(SRC)

# Static type checking (mypy + Pydantic plugin)
typecheck:
	$(UV) run mypy $(SRC)

# Run tests (if/when you add tests/)
test:
	$(UV) run pytest

# Everything that should pass before you commit
check: lint typecheck test

# Run your package as a module (adjust if you add a CLI entrypoint)
run:
	$(UV) run python -m $(PKG)

# Clean typical Python/pytest/mypy caches
clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache dist build
	find . -name "__pycache__" -type d -exec rm -rf {} +
