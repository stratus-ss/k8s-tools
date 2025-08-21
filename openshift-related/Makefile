# Makefile for OpenShift Control Plane Replacement Tool
# Provides code formatting and linting with 120-character line length
# make file created by Cursor.ai
# Configuration
PYTHON := python3
LINE_LENGTH := 120
SRC_DIR := replace_control_plane
MAIN_SCRIPT := $(SRC_DIR)/replace_control_plane.py

# Help target (default)
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  format     - Format code with black (120 char line length)"
	@echo "  lint       - Lint code with flake8 (120 char line length)"  
	@echo "  check      - Check formatting without making changes"
	@echo "  fix        - Format code and fix common issues"
	@echo "  test       - Run basic syntax and import tests"
	@echo "  clean      - Remove Python cache files"
	@echo "  install    - Install development dependencies"
	@echo "  all        - Run format, lint, and test"
	@echo ""
	@echo "Configuration:"
	@echo "  Line length: $(LINE_LENGTH) characters"
	@echo "  Source directory: $(SRC_DIR)"

# Format code with black
.PHONY: format
format:
	@echo "Formatting Python code with black ($(LINE_LENGTH) char line length)..."
	$(PYTHON) -m black --line-length=$(LINE_LENGTH) $(SRC_DIR)/
	@echo "✅ Code formatting completed"

# Check formatting without making changes
.PHONY: check
check:
	@echo "Checking code formatting with black ($(LINE_LENGTH) char line length)..."
	$(PYTHON) -m black --check --line-length=$(LINE_LENGTH) $(SRC_DIR)/
	@echo "✅ Code formatting check completed"

# Lint with flake8
.PHONY: lint  
lint:
	@echo "Linting Python code with flake8 ($(LINE_LENGTH) char line length)..."
	$(PYTHON) -m flake8 --max-line-length=$(LINE_LENGTH) \
		--ignore=E203,W503,E501 \
		--exclude=__pycache__,.venv,venv,.git \
		$(SRC_DIR)/
	@echo "✅ Code linting completed"

# Format and lint together
.PHONY: fix
fix: format lint
	@echo "✅ Code formatting and linting completed"

# Basic tests
.PHONY: test
test:
	@echo "Running syntax check..."
	$(PYTHON) -m py_compile $(MAIN_SCRIPT)
	@echo "✅ Syntax check passed"
	@echo "Testing imports..."
	$(PYTHON) -c "import sys; sys.path.insert(0, '$(SRC_DIR)'); import replace_control_plane; print('✅ Import test passed')"
	@echo "Testing help output..."
	$(PYTHON) $(MAIN_SCRIPT) --help > /dev/null && echo "✅ Help output test passed"

# Install development dependencies
.PHONY: install
install:
	@echo "Installing development dependencies..."
	$(PYTHON) -m pip install black flake8 pyyaml
	@echo "✅ Development dependencies installed"

# Clean up cache files
.PHONY: clean
clean:
	@echo "Cleaning up Python cache files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleanup completed"

# Run all quality checks
.PHONY: all
all: format lint test
	@echo "✅ All code quality checks completed successfully"

# Show current configuration
.PHONY: config
config:
	@echo "Current configuration:"
	@echo "  Python: $(shell $(PYTHON) --version)"
	@echo "  Black: $(shell $(PYTHON) -m black --version 2>/dev/null || echo 'Not installed')"
	@echo "  Flake8: $(shell $(PYTHON) -m flake8 --version 2>/dev/null || echo 'Not installed')"
	@echo "  Line length: $(LINE_LENGTH)"
	@echo "  Source directory: $(SRC_DIR)"
	@echo "  Main script: $(MAIN_SCRIPT)"

# Quick script validation
.PHONY: validate
validate:
	@echo "Validating $(MAIN_SCRIPT)..."
	$(PYTHON) -m py_compile $(MAIN_SCRIPT)
	@echo "✅ Script validation passed"
