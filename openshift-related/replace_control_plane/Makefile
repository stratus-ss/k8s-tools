.PHONY: all format lint typecheck check fix test test-import clean clean-pyc clean-all install config help validate build-monolith build-modular venv

# Virtual environment configuration
VENV_DIR = venv
VENV_PYTHON = $(VENV_DIR)/bin/python
VENV_PIP = $(VENV_DIR)/bin/pip

# Always use venv python for development commands
BLACK_CMD = $(VENV_PYTHON) -m black --line-length=$(LINE_LENGTH)
FLAKE8_CMD = $(VENV_PYTHON) -m flake8 --max-line-length=$(LINE_LENGTH)
MYPY_CMD = $(VENV_PYTHON) -m mypy --ignore-missing-imports --follow-imports=silent

# Use venv python if it exists, otherwise system python (for other commands)
PYTHON = $(shell if [ -f "$(VENV_PYTHON)" ]; then echo "$(VENV_PYTHON)"; else echo "python3"; fi)

# Configuration
LINE_LENGTH = 120
SOURCE_DIR = .
MAIN_SCRIPT = replace_control_plane.py
MODULAR_SCRIPT = replace_control_plane_modular.py
MODULES_DIR = modules

# Default target
all: format lint typecheck test

# Format code with black
format: venv
	@echo "Formatting Python code with black ($(LINE_LENGTH) char line length)..."
	$(BLACK_CMD) .
	@echo "✅ Code formatting completed"

# Lint code with flake8  
lint: venv
	@echo "Linting Python code with flake8 ($(LINE_LENGTH) char line length)..."
	$(FLAKE8_CMD) .
	@echo "✅ Code linting completed"

# Check code formatting without changes
check: venv
	@echo "Checking code formatting with black ($(LINE_LENGTH) char line length)..."
	$(BLACK_CMD) --check .
	@echo "✅ Code formatting check passed"

# Type check with mypy
typecheck: venv
	@echo "Type checking Python code with mypy..."
	$(MYPY_CMD) .
	@echo "✅ Type checking completed"

# Run formatter, linter, and type checker
fix: format lint typecheck

# Test with virtual environment setup and dependency installation
test: venv
	@echo "✅ Running tests with virtual environment..."
	@echo "📦 Installing test dependencies..."
	$(VENV_PYTHON) -m pip install -q -e .[test] > /dev/null 2>&1
	@echo "🧪 Running pytest..."
	$(VENV_PYTHON) -m pytest tests/ --tb=short
	@echo "✅ All tests completed"

# Test basic syntax and imports
test-import:
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

# Validate modular structure and build
build-modular:
	@echo "Validating modular structure and dependencies..."
	@echo "  Compiling main modular script..."
	@$(PYTHON) -m py_compile $(MODULAR_SCRIPT)
	@echo "  Compiling all module files..."
	@$(PYTHON) -m py_compile $(MODULES_DIR)/*.py
	@echo "  Testing module imports..."
	@$(PYTHON) -c "from modules import *; print('    ✅ All modules imported successfully')"
	@echo "  Testing individual module components..."
	@$(PYTHON) -c "from modules.orchestrator import process_node_operation; print('    ✅ Orchestrator module OK')"
	@$(PYTHON) -c "from modules.resource_manager import ResourceManager; print('    ✅ Resource manager module OK')"
	@$(PYTHON) -c "from modules.configuration_manager import create_new_node_configs; print('    ✅ Configuration manager module OK')"
	@$(PYTHON) -c "from modules.etcd_manager import handle_etcd_operations; print('    ✅ ETCD manager module OK')"
	@echo "  Testing main script entry point..."
	@$(PYTHON) -c "import replace_control_plane_modular; print('    ✅ Main script imports successfully')"
	@echo "✅ Modular build validation completed successfully!"

# Ensure build script exists
scripts/build_monolith.py:
	@echo "Build script should be created manually or already exists"
	@test -f scripts/build_monolith.py || echo "ERROR: scripts/build_monolith.py not found"

# Clean temporary files (preserves virtual environment)
clean:
	@echo "Cleaning temporary files..."
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@rm -rf htmlcov/ .coverage .pytest_cache/
	@echo "✅ Cleanup completed (virtual environment preserved)"

# Clean Python compiled files only
clean-pyc:
	@echo "Cleaning Python compiled files..."
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Python compiled files cleaned"

# Clean everything including virtual environment
clean-all:
	@echo "Cleaning all temporary files and virtual environment..."
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@rm -rf htmlcov/ .coverage .pytest_cache/
	@rm -rf $(VENV_DIR)
	@echo "✅ Complete cleanup finished (including virtual environment)"

# Create virtual environment (idempotent - only creates if doesn't exist)
venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv $(VENV_DIR); \
		echo "Installing development dependencies..."; \
		$(VENV_PIP) install --upgrade pip; \
		$(VENV_PIP) install black flake8 mypy PyYAML; \
		echo "✅ Virtual environment created and dependencies installed"; \
	else \
		echo "✅ Virtual environment already exists"; \
	fi

# Install development dependencies  
install: venv
	@echo "✅ Dependencies installed (using virtual environment)"

# Show current configuration
config:
	@echo "Current configuration:"
	@echo "  Python: $$($(PYTHON) --version)"
	@echo "  Virtual environment: $$(if [ -d "$(VENV_DIR)" ]; then echo 'Active ($(VENV_DIR))'; else echo 'Not created'; fi)"
	@echo "  Black: $$($(VENV_PYTHON) -m black --version 2>/dev/null || echo 'Not installed (run make fix/format/lint to auto-install)')"
	@echo "  Flake8: $$($(VENV_PYTHON) -m flake8 --version 2>/dev/null | head -1 || echo 'Not installed (run make fix/format/lint to auto-install)')"
	@echo "  Mypy: $$($(VENV_PYTHON) -m mypy --version 2>/dev/null || echo 'Not installed (run make fix/typecheck to auto-install)')"
	@echo "  Line length: $(LINE_LENGTH)"
	@echo "  Source directory: $(SOURCE_DIR)"
	@echo "  Main script: $(MAIN_SCRIPT)"
	@echo "  Modular script: $(MODULAR_SCRIPT)"

# Show help
help:
	@echo "Available targets:"
	@echo "  all            - Run format, lint, typecheck, and test"
	@echo "  format         - Format code with black ($(LINE_LENGTH) chars) - auto-creates venv"
	@echo "  lint           - Lint code with flake8 ($(LINE_LENGTH) chars) - auto-creates venv"  
	@echo "  typecheck      - Type check code with mypy - auto-creates venv"
	@echo "  check          - Check formatting without changes - auto-creates venv"
	@echo "  fix            - Run format, lint, and typecheck - auto-creates venv"
	@echo "  test           - Run pytest with venv setup and dependency installation"
	@echo "  test-import    - Test basic syntax and imports"
	@echo "  validate       - Validate script compilation"
	@echo "  build-monolith - Build single file from modules"
	@echo "  build-modular  - Validate modular structure and dependencies"
	@echo "  venv           - Create virtual environment with dev dependencies"
	@echo "  clean          - Remove temporary files (preserves venv)"
	@echo "  clean-pyc      - Remove only Python compiled files"
	@echo "  clean-all      - Remove everything including virtual environment"
	@echo "  install        - Install development dependencies (creates venv)"
	@echo "  config         - Show current configuration"
	@echo "  help           - Show this help message"
