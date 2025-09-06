# BackupManager Pytest Tests

## Overview

**NOTE:** Tests currently written by Cursor.ai. I intend to go back and review these


Comprehensive pytest test suite for the `BackupManager` class that handles backup and file operations for OpenShift control plane replacement.

## Features

- **100% method coverage** - Tests all public methods of BackupManager
- **Realistic test data** - Uses actual OpenShift cluster data as fixtures
- **Comprehensive mocking** - Properly mocks external dependencies
- **Edge case testing** - Tests success and failure scenarios
- **Static fixtures** - Real BMH, Machine, and Secret data from live cluster

## Test Structure

### Test Classes

1. **TestBackupManagerInit** - Initialization and constructor testing
2. **TestSetupBackupDirectory** - Backup directory creation and cluster name detection
3. **TestFileOperations** - File copying and metadata sanitization
4. **TestDataExtraction** - BMH and Machine data extraction and cleaning
5. **TestBackupOperations** - Resource backup operations (BMH, Machine, Secrets)
6. **TestTemplateBMHBackup** - Template selection logic for different operation types
7. **TestFileCopyOperations** - File copy operations for node replacement
8. **TestNMStateExtraction** - NMState configuration extraction

### Key Test Features

- **Real data fixtures** from live OpenShift cluster using kubeconfig `/home/stratus/temp/kubeconfig`
- **Comprehensive mocking** of file operations, oc commands, and external dependencies
- **Edge case coverage** including failures, missing data, and error conditions
- **Parameterized testing** for different operation modes (replacement vs expansion)

## Running Tests

### Install Dependencies
```bash
pip3 install -r requirements-test.txt
```

### Run All Tests
```bash
python3 -m pytest test_backup_manager.py -v
```

### Run Specific Test Classes
```bash
# Test initialization
python3 -m pytest test_backup_manager.py::TestBackupManagerInit -v

# Test backup operations
python3 -m pytest test_backup_manager.py::TestBackupOperations -v

# Test template selection
python3 -m pytest test_backup_manager.py::TestTemplateBMHBackup -v
```

### Run with Coverage
```bash
python3 -m pytest test_backup_manager.py --cov=modules.backup_manager --cov-report=html
```

## Test Data Sources

Test fixtures include real data from OpenShift cluster:

- **BareMetalHost**: Real BMH definition with control-plane role
- **Machine**: Real Machine definition with master role and taints
- **Secret**: Real secret structure for BMC credentials
- **BMH List**: Multiple BMH resources for template selection testing

## Mocked Dependencies

- **File Operations**: `shutil.copy2`, file opening, directory creation
- **OC Commands**: `execute_oc_command` function for cluster interactions
- **Printer**: Output/logging functions for user feedback
- **Temporary Files**: `tempfile.NamedTemporaryFile` for nmstate extraction

## Test Coverage

Tests cover all major BackupManager functionality:

✅ **Initialization** with various parameter combinations  
✅ **Backup directory** setup and cluster name detection  
✅ **File operations** including copying and error handling  
✅ **Metadata sanitization** removing runtime/managed fields  
✅ **BMH/Machine extraction** with proper field filtering  
✅ **Resource backup** for BMH, Machine, and Secret objects  
✅ **Template selection** for different operation types  
✅ **File copying** for replacement workflows  
✅ **NMState extraction** for network configuration  
✅ **Error handling** for various failure scenarios  

## Example Test Execution

```bash
$ python3 -m pytest test_backup_manager.py::TestBackupOperations::test_backup_secret_success -v

============= test session starts =============
test_backup_manager.py::TestBackupOperations::test_backup_secret_success PASSED [100%]
============= 1 passed in 0.02s =============
```

## Integration with CI/CD

These tests can be easily integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions step
- name: Run BackupManager Tests  
  run: |
    pip install -r requirements-test.txt
    python3 -m pytest test_backup_manager.py --junitxml=results.xml
```

## Test Data Validation

All test fixtures are based on real OpenShift cluster data ensuring realistic testing scenarios that match production usage patterns.
