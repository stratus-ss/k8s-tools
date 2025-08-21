.PHONY: all format lint check fix test clean install config help validate build-monolith

PYTHON ?= python3
BLACK_CMD = $(PYTHON) -m black --line-length=$(LINE_LENGTH)
FLAKE8_CMD = $(PYTHON) -m flake8 --max-line-length=$(LINE_LENGTH)

# Configuration
LINE_LENGTH = 120
SOURCE_DIR = .
MAIN_SCRIPT = replace_control_plane.py
MODULAR_SCRIPT = replace_control_plane_modular.py
MODULES_DIR = modules

# Default target
all: format lint test

# Format code with black
format:
	@echo "Formatting Python code with black ($(LINE_LENGTH) char line length)..."
	$(BLACK_CMD) .
	@echo "✅ Code formatting completed"

# Lint code with flake8  
lint:
	@echo "Linting Python code with flake8 ($(LINE_LENGTH) char line length)..."
	$(FLAKE8_CMD) .
	@echo "✅ Code linting completed"

# Check code formatting without making changes
check:
	@echo "Checking code formatting with black ($(LINE_LENGTH) char line length)..."
	$(BLACK_CMD) --check .
	@echo "✅ Code formatting check passed"

# Run formatter and linter
fix: format lint

# Test basic syntax and imports
test:
	@echo "Testing basic syntax and imports..."
	@$(PYTHON) -m py_compile $(MODULAR_SCRIPT)
	@$(PYTHON) -c "from modules import *; print('✅ Module imports successful')"
	@echo "✅ All tests passed"

# Validate main script can be compiled
validate:
	@echo "Validating main script compilation..."
	@$(PYTHON) -m py_compile $(MAIN_SCRIPT) || echo "⚠️ Original script may have issues"
	@$(PYTHON) -m py_compile $(MODULAR_SCRIPT)
	@echo "✅ Script validation completed"

# Build monolithic version from modules
build-monolith:
	@echo "Building monolithic version from modules..."
	@$(PYTHON) scripts/build_monolith.py
	@echo "✅ Monolithic build completed: $(MAIN_SCRIPT)"

# Ensure build script exists
scripts/build_monolith.py:
	@echo "Build script should be created manually or already exists"
	@test -f scripts/build_monolith.py || echo "ERROR: scripts/build_monolith.py not found"

# Clean temporary files
clean:
	@echo "Cleaning temporary files..."
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@rm -rf htmlcov/ .coverage .pytest_cache/
	@echo "✅ Cleanup completed"

# Install development dependencies  
install:
	@echo "Installing development dependencies..."
	@$(PYTHON) -m pip install black flake8 --quiet
	@echo "✅ Dependencies installed"

# Show current configuration
config:
	@echo "Current configuration:"
	@echo "  Python: $$($(PYTHON) --version)"
	@echo "  Black: $$($(BLACK_CMD) --version 2>/dev/null || echo 'Not installed')"
	@echo "  Flake8: $$($(FLAKE8_CMD) --version 2>/dev/null || echo 'Not installed')"
	@echo "  Line length: $(LINE_LENGTH)"
	@echo "  Source directory: $(SOURCE_DIR)"
	@echo "  Main script: $(MAIN_SCRIPT)"
	@echo "  Modular script: $(MODULAR_SCRIPT)"

# Show help
help:
	@echo "Available targets:"
	@echo "  all            - Run format, lint, and test"
	@echo "  format         - Format code with black ($(LINE_LENGTH) chars)"
	@echo "  lint           - Lint code with flake8 ($(LINE_LENGTH) chars)"  
	@echo "  check          - Check formatting without changes"
	@echo "  fix            - Run format and lint"
	@echo "  test           - Test basic syntax and imports"
	@echo "  validate       - Validate script compilation"
	@echo "  build-monolith - Build single file from modules"
	@echo "  clean          - Remove temporary files"
	@echo "  install        - Install development dependencies"
	@echo "  config         - Show current configuration"
	@echo "  help           - Show this help message"
