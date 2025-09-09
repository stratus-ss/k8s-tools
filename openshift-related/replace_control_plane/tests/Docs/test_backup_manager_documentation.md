# BackupManager Test Suite Documentation

## Overview

The `test_backup_manager.py` file contains comprehensive test coverage for the `BackupManager` class, which handles backup and restore operations for OpenShift node replacement scenarios. This test suite validates all critical functionality required for safely backing up, sanitizing, and restoring Kubernetes resources during control plane node replacement operations.

## Purpose and Context

The BackupManager is a critical component of the OpenShift control plane replacement system. It ensures that essential configuration data (BareMetalHosts, Machines, Secrets, and network configurations) can be safely backed up, modified, and restored during node replacement operations. The tests validate both happy path scenarios and edge cases to ensure production-grade reliability.

## Test Structure and Organization

### Test Fixtures and Data

The test file begins with comprehensive fixtures containing realistic production data from OpenShift clusters:

- **sample_bmh_data**: Complete BareMetalHost definition with all production fields
- **sample_machine_data**: Full Machine resource with proper metadata and specifications
- **sample_bmc_secret_data**: BMC credentials secret with base64-encoded credentials
- **Network configuration testing**: Now handled by `network_config_scenarios` parametrized fixture in conftest.py

**Why these fixtures matter**: They ensure tests run against realistic production data rather than synthetic test data, improving test confidence and catching real-world edge cases.

## Test Classes and Their Purposes

### 1. TestMetadataSanitization

**Purpose**: Validates the critical metadata sanitization functionality that removes Kubernetes runtime fields before backup storage.

**Why this is tested**: Kubernetes resources contain runtime-generated metadata (UIDs, creation timestamps, resource versions, etc.) that must be removed before backup to prevent conflicts during restoration.

**Key Tests**:

#### test_sanitize_metadata_removes_runtime_fields
- **What**: Verifies that all Kubernetes runtime metadata fields are properly removed
- **Why**: Runtime fields like `creationTimestamp`, `resourceVersion`, `uid`, `managedFields`, `ownerReferences`, `finalizers`, and last-applied-configuration annotations cause conflicts if restored
- **How**: Creates a resource with all problematic runtime fields, calls sanitize_metadata(), and verifies removal while preserving essential fields
- **Production Impact**: Prevents restoration failures due to metadata conflicts

#### test_sanitize_metadata_handles_missing_metadata
- **What**: Ensures sanitization works gracefully when metadata section is missing
- **Why**: Some Kubernetes resources might not have complete metadata sections
- **How**: Passes data without metadata and verifies it returns unchanged
- **Production Impact**: Prevents crashes when handling incomplete resource definitions

#### test_sanitize_metadata_preserves_essential_fields
- **What**: Validates that critical fields for resource identity are preserved
- **Why**: Fields like name, namespace, and labels are essential for proper resource restoration
- **How**: Creates resource with essential fields, sanitizes it, and verifies preservation
- **Production Impact**: Ensures restored resources maintain their identity and relationships

### 2. TestRealBackupDirectorySetup

**Purpose**: Validates backup directory creation and management with actual filesystem operations.

**Why this is tested**: Backup operations require reliable directory creation with proper permissions and error handling.

**Key Tests**:

#### test_setup_backup_directory_with_provided_path_creates_directory
- **What**: Verifies directory creation when explicit path is provided
- **Why**: Operators may specify custom backup locations for organizational or storage reasons
- **How**: Uses temporary directory, provides custom path, verifies creation and write permissions
- **Production Impact**: Ensures backup operations work with custom directory specifications

#### test_setup_backup_directory_auto_generate_with_cluster_name
- **What**: Tests automatic backup directory generation using cluster DNS name
- **Why**: Default behavior should create meaningful directory names based on cluster identity
- **How**: Mocks OpenShift DNS query, verifies cluster name extraction and directory creation
- **Production Impact**: Provides intuitive default backup locations organized by cluster

#### test_setup_backup_directory_cluster_name_failure_creates_unknown_cluster_dir
- **What**: Tests fallback behavior when cluster name cannot be retrieved
- **Why**: Backup operations should continue even if cluster identification fails
- **How**: Mocks failed DNS query, verifies fallback to "unknown-cluster" directory
- **Production Impact**: Ensures backup operations are resilient to cluster configuration issues

#### test_setup_existing_directory_is_reused
- **What**: Verifies that existing backup directories are reused without data loss
- **Why**: Operators may run backup operations multiple times and existing data should be preserved
- **How**: Creates directory with existing file, runs setup, verifies file preservation
- **Production Impact**: Prevents accidental data loss during repeated backup operations

#### test_setup_directory_is_writable_and_functional
- **What**: Tests that created directories are fully functional for backup operations
- **Why**: Directory creation alone isn't sufficient; write permissions and functionality must be verified
- **How**: Creates directory and attempts to write various backup file types
- **Production Impact**: Ensures backup operations will succeed after directory setup

#### test_setup_directory_handles_permission_errors
- **What**: Tests graceful handling of permission-related directory creation failures
- **Why**: Production environments may have restricted filesystem permissions
- **How**: Creates read-only parent directory and verifies PermissionError handling
- **Production Impact**: Provides clear error handling for permission-related failures

### 3. TestRealFileOperations

**Purpose**: Validates file copy operations with actual filesystem interaction.

**Why this is tested**: Node replacement requires copying and modifying existing backup files, which must be tested with real file I/O.

**Key Tests**:

#### test_make_file_copy_preserves_content
- **What**: Verifies file copying preserves exact content
- **Why**: Backup restoration depends on perfect content fidelity
- **How**: Creates source file with BMC secret content, copies it, verifies identical content
- **Production Impact**: Ensures backup files maintain integrity during copy operations

#### test_make_file_copy_file_not_found
- **What**: Tests error handling when source file doesn't exist
- **Why**: Production environments may have missing or moved files
- **How**: Attempts to copy non-existent file and verifies FileNotFoundError
- **Production Impact**: Provides clear error reporting for missing source files

#### test_make_file_copy_permission_denied
- **What**: Tests error handling for permission-related copy failures
- **Why**: Production filesystems may have restricted permissions
- **How**: Creates read-only destination and verifies PermissionError handling
- **Production Impact**: Ensures graceful failure with clear error messages for permission issues

### 4. TestDataExtraction

**Purpose**: Validates extraction and transformation of Kubernetes resource data.

**Why this is tested**: Node replacement requires extracting specific fields from complex Kubernetes resources while maintaining structure integrity.

**Key Tests**:

#### test_extract_bmh_fields_complete_extraction
- **What**: Verifies complete BareMetalHost field extraction with structure preservation
- **Why**: BMH resources are complex with nested configuration that must be preserved exactly
- **How**: Extracts fields from realistic BMH data and validates all critical sections (BMC, networking, storage, user data)
- **Production Impact**: Ensures BMH backup files contain all necessary configuration for restoration

#### test_extract_machine_fields_complete_extraction
- **What**: Verifies complete Machine resource field extraction
- **Why**: Machine resources define the relationship between physical hosts and Kubernetes nodes
- **How**: Extracts fields from realistic Machine data and validates metadata, labels, and provider specifications
- **Production Impact**: Ensures Machine backup files maintain all relationships and configurations

### 5. TestRealBackupOperations

**Purpose**: Validates actual backup file creation with YAML serialization.

**Why this is tested**: The core backup functionality must create valid, loadable YAML files that can be used for restoration.

**Key Tests**:

#### test_backup_bmh_definition_creates_valid_yaml
- **What**: Verifies BMH backup creates valid, complete YAML files
- **Why**: Backup files must be valid YAML that can be loaded and applied to Kubernetes
- **How**: Performs backup operation, verifies file creation, loads YAML, and validates content
- **Production Impact**: Ensures BMH backup files are usable for restoration operations

#### test_backup_machine_definition_creates_valid_yaml
- **What**: Verifies Machine backup creates valid, complete YAML files
- **Why**: Machine resources are critical for node lifecycle management
- **How**: Performs backup operation, verifies file creation and content validity
- **Production Impact**: Ensures Machine backup files maintain all necessary configuration

#### test_backup_secret_creates_sanitized_yaml
- **What**: Verifies secret backup with proper metadata sanitization
- **Why**: Secrets contain sensitive data and runtime metadata that must be cleaned before backup
- **How**: Backs up BMC secret, verifies runtime metadata removal while preserving essential data
- **Production Impact**: Ensures secret backups are clean and restorable without conflicts

#### test_backup_secret_handles_command_failure
- **What**: Tests error handling when secret retrieval fails
- **Why**: OpenShift commands may fail due to network, permissions, or resource availability
- **How**: Mocks command failure and verifies appropriate exception handling
- **Production Impact**: Provides clear error reporting for secret retrieval failures

#### test_backup_operations_use_correct_filenames
- **What**: Verifies backup operations use consistent, expected naming conventions
- **Why**: File naming conventions are critical for automation and manual operations
- **How**: Performs various backup operations and validates filename patterns
- **Production Impact**: Ensures backup files follow predictable naming for operational reliability

### 6. TestTemplateBMHBackup

**Purpose**: Validates BMH template selection and backup for different node replacement scenarios.

**Why this is tested**: Node replacement scenarios require selecting appropriate BMH templates based on the type of replacement (control plane expansion, worker addition, failed node replacement).

**Key Tests**:

#### test_backup_template_bmh_control_plane_expansion
- **What**: Tests template selection for control plane expansion scenarios
- **Why**: Control plane expansion requires templates from existing control plane nodes
- **How**: Mocks cluster BMH list retrieval and verifies control plane template selection
- **Production Impact**: Ensures control plane expansion uses appropriate BMH configurations

#### test_backup_template_bmh_worker_addition
- **What**: Tests template selection for worker node addition
- **Why**: Worker addition should use worker node templates, not control plane templates
- **How**: Mocks cluster retrieval and verifies worker template selection logic
- **Production Impact**: Ensures worker additions use correct BMH configurations

#### test_backup_template_bmh_failed_control_node
- **What**: Tests template backup from a specific failed control node
- **Why**: When replacing a failed node, the original node's configuration should be used as template
- **How**: Specifies failed node name and verifies specific BMH retrieval and backup
- **Production Impact**: Ensures failed node replacement maintains original configuration

#### test_backup_template_bmh_cluster_retrieval_failure
- **What**: Tests graceful handling of cluster BMH list retrieval failures
- **Why**: Network or authentication issues may prevent cluster resource access
- **How**: Mocks command failure and verifies graceful None return
- **Production Impact**: Prevents crashes when cluster access is unavailable

#### test_backup_template_bmh_no_suitable_templates_for_worker_addition
- **What**: Tests handling when no suitable worker templates are found
- **Why**: Clusters might not have appropriate worker nodes for template use
- **How**: Provides empty BMH list and verifies graceful handling
- **Production Impact**: Provides clear indication when template selection is impossible

#### test_backup_template_bmh_exception_handling
- **What**: Tests comprehensive exception handling for unexpected failures
- **Why**: Production environments may encounter unexpected errors during template operations
- **How**: Forces exception during template operations and verifies graceful handling
- **Production Impact**: Ensures template operations are resilient to unexpected failures

### 7. TestRealFileCopyOperations

**Purpose**: Validates complete file copy operations for node replacement workflows.

**Why this is tested**: Node replacement requires copying multiple related files (BMH, Machine, secrets, network config) with consistent naming and content preservation.

**Key Tests**:

#### test_copy_files_for_replacement_creates_all_files
- **What**: Verifies complete file copy workflow creates all required replacement files
- **Why**: Node replacement requires multiple coordinated file operations that must all succeed
- **How**: Creates source files with realistic content, performs copy operation, verifies all target files exist with correct content
- **Production Impact**: Ensures node replacement has all necessary configuration files

#### test_copy_files_for_replacement_handles_missing_source
- **What**: Tests error handling when source files are missing
- **Why**: Incomplete backups or file system issues may result in missing source files
- **How**: Attempts copy operation without creating source files and verifies appropriate error
- **Production Impact**: Provides clear error indication when backup files are incomplete

### 8. TestErrorHandlingAndEdgeCases

**Purpose**: Validates system behavior under unusual or error conditions.

**Why this is tested**: Production systems must handle edge cases gracefully without data corruption or system failures.

**Key Tests**:

#### test_sanitize_metadata_with_deeply_nested_missing_keys
- **What**: Tests metadata sanitization with complex nested structures
- **Why**: Kubernetes resources can have deeply nested metadata that requires careful handling
- **How**: Creates complex nested structure and verifies only top-level metadata fields are sanitized
- **Production Impact**: Ensures metadata sanitization doesn't corrupt complex resource structures

#### test_backup_operations_with_invalid_yaml_content
- **What**: Tests backup operations with problematic YAML content (special characters, quotes)
- **Why**: Production resources may contain special characters that could break YAML serialization
- **How**: Uses fixture with problematic characters and verifies successful YAML generation and reload
- **Production Impact**: Ensures backup operations handle edge cases in resource naming and content

### 9. TestNMStateExtraction

**Purpose**: Validates network configuration extraction for node replacement.

**Why this is tested**: Node replacement requires preserving exact network configuration from the original node.

**Key Tests**:

#### test_extract_nmstate_config_success
- **What**: Tests successful network configuration extraction
- **Why**: Network configuration is critical for node connectivity and must be preserved exactly
- **How**: Mocks successful OpenShift command execution and verifies file extraction and renaming
- **Production Impact**: Ensures network configuration is properly extracted for node replacement

#### test_extract_nmstate_config_failure
- **What**: Tests error handling when network configuration extraction fails
- **Why**: Network configuration extraction may fail due to missing secrets or command failures
- **How**: Mocks command failure and file system errors, verifies appropriate exception handling
- **Production Impact**: Provides clear error reporting when network configuration cannot be extracted

## Test Data Strategy

### Realistic Production Data
All test fixtures use realistic data extracted from actual OpenShift clusters, including:
- Complete metadata structures with all standard Kubernetes fields
- Realistic BMC addresses and network configurations
- Base64-encoded secrets with proper structure
- Complex nested configurations that mirror production complexity

### Edge Case Coverage
Tests include specific edge cases commonly encountered in production:
- Special characters in resource names and configurations
- Missing or incomplete metadata sections
- Permission and file system errors
- Network and command execution failures
- Complex nested data structures

## Error Handling Philosophy

The test suite validates that the BackupManager handles errors gracefully by:
- Providing clear, actionable error messages
- Failing fast when operations cannot complete safely
- Preserving existing data when operations fail
- Never leaving the system in an inconsistent state

## Testing Framework Integration

Tests use pytest with comprehensive fixtures and mocking:
- **Fixtures**: Provide consistent, realistic test data
- **Mocking**: Isolates units under test from external dependencies
- **Temporary directories**: Ensure test isolation and cleanup
- **Exception testing**: Validates error handling paths

## Production Readiness Validation

These tests ensure the BackupManager is production-ready by validating:
- **Data integrity**: All operations preserve data correctly
- **Error resilience**: System handles failures gracefully
- **Resource management**: Proper cleanup and resource usage
- **File system operations**: Robust handling of I/O operations
- **Kubernetes integration**: Correct handling of OpenShift resources

## Maintenance and Evolution

This test suite should be maintained by:
- Adding tests for new backup scenarios as they arise
- Updating fixtures when Kubernetes resource schemas change  
- Expanding error case coverage based on production incidents
- Validating performance characteristics under load

The comprehensive nature of these tests ensures that the BackupManager can be confidently used in production OpenShift environments where data integrity and operational reliability are critical.
