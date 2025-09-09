# Makefile for test operations
.PHONY: test test-verbose test-coverage install-deps clean

# Default Python interpreter
PYTHON ?= python3

# Install test dependencies
install-deps:
	$(PYTHON) -m pip install -r requirements.txt

# Run all tests quietly
test:
	$(PYTHON) -m pytest --tb=short

# Run all tests with verbose output
test-verbose:
	$(PYTHON) -m pytest -v

# Run tests with coverage report
test-coverage:
	$(PYTHON) -m pytest --cov=../modules --cov-report=html --cov-report=term

# Run specific test file
test-backup-manager:
	$(PYTHON) -m pytest test_backup_manager.py -v

# Run specific test file
test-utilities:
	$(PYTHON) -m pytest test_utilities.py -v

# Clean up test artifacts
clean:
	rm -rf __pycache__ .pytest_cache htmlcov .coverage
	find . -name "*.pyc" -delete

# Help
help:
	@echo "Available targets:"
	@echo "  install-deps     - Install test dependencies"
	@echo "  test            - Run all tests quietly"
	@echo "  test-verbose    - Run all tests with verbose output"
	@echo "  test-coverage   - Run tests with coverage report"
	@echo "  test-backup-manager - Run BackupManager tests only"
	@echo "  test-utilities  - Run utilities tests only"
	@echo "  clean           - Clean up test artifacts"
