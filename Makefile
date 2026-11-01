.PHONY: test-build test-unit test-integration test-all clean help lint fix ci

# Build the test Docker image
test-build:
	docker build -f Dockerfile.test -t ml-api-test .

# Run unit tests only (fast, no Docker Compose)
test-unit: test-build
	docker run --rm \
		-v $(PWD)/test-results:/app/test-results \
		ml-api-test pytest test/unit -v

# Run integration tests with Docker Compose
test-integration:
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from test

# Run all tests (unit + integration)
test-all: test-build
	@echo "Running integration tests..."
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from test
	@echo "Running unit tests..."
	docker run --rm \
		-v $(PWD)/test-results:/app/test-results \
		ml-api-test pytest test/unit -v

# Clean up containers and test artifacts
clean:
	docker-compose -f docker-compose.test.yml down -v
	rm -rf test-results/*

# Display help information
help:
	@echo "Docker-Based Testing Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  test-build        - Build the test Docker image"
	@echo "  test-unit         - Run unit tests only (fast)"
	@echo "  test-integration  - Run integration tests with Docker Compose"
	@echo "  test-all          - Run all tests (unit + integration)"
	@echo "  clean             - Remove containers and test artifacts"
	@echo "  help              - Display this help message"
	@echo ""
	@echo "Examples:"
	@echo "  make test-unit              # Quick unit tests"
	@echo "  make test-integration       # Full integration tests"
	@echo "  make test-all               # Complete test suite"
	@echo "  make clean                  # Clean up after tests"
	@echo "  lint              - Run Ruff lint and format checks"
	@echo "  fix               - Auto-fix lint issues and reformat code"
	@echo "  ci                - Run lint, then all tests"

# Lint and format check (no changes made)
lint:
	uv run ruff check .
	uv run ruff format --check .

# Auto-fix lint issues and reformat
fix:
	uv run ruff check --fix .
	uv run ruff format .

# What CI runs: lint first, then the full Docker test suite
ci: lint test-all