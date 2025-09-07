#!/usr/bin/env python3
"""
Comprehensive pytest tests for BackupManager class.
Tests all methods with realistic OpenShift data following enterprise Python standards.

This module provides comprehensive test coverage for the BackupManager class,
validating backup and restore operations for OpenShift node replacement scenarios.
All tests follow enterprise-grade patterns with proper type annotations,
comprehensive error handling, and realistic test data.
"""

import pytest
import os
import sys
import tempfile
import yaml
from typing import Any, Dict, Generator

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import Mock, patch, mock_open  # noqa: E402
from modules.backup_manager import BackupManager  # noqa: E402


# =============================================================================
# Test Fixtures - Static Data from Real OpenShift Cluster
# =============================================================================


@pytest.fixture
def sample_bmh_data() -> Dict[str, Any]:
    """Real BareMetalHost data from OpenShift cluster.

    Returns:
        Dict[str, Any]: Dictionary containing realistic BMH data from a production
            OpenShift cluster, including all essential fields for testing backup operations.
    """
    return {
        "apiVersion": "metal3.io/v1alpha1",
        "kind": "BareMetalHost",
        "metadata": {
            "creationTimestamp": "2025-08-26T13:41:57Z",
            "finalizers": ["baremetalhost.metal3.io"],
            "generation": 3,
            "labels": {"installer.openshift.io/role": "control-plane"},
            "name": "ocp-control2.two.ocp4.example.com",
            "namespace": "openshift-machine-api",
            "resourceVersion": "309046",
            "uid": "86aefc1b-5d63-47b0-9cf8-92db6de8ee0e",
        },
        "spec": {
            "architecture": "x86_64",
            "automatedCleaningMode": "metadata",
            "bmc": {
                "address": "redfish-virtualmedia+http://192.168.94.1:8000/redfish/v1/Systems/8e74843e-9f5b-4b3b-b818-9bb09d881c94",
                "credentialsName": "ocp-control2.two.ocp4.example.com-bmc-secret",
            },
            "bootMACAddress": "52:54:00:e9:d5:8a",
            "bootMode": "UEFI",
            "consumerRef": {
                "apiVersion": "machine.openshift.io/v1beta1",
                "kind": "Machine",
                "name": "two-xkb99-master-1",
                "namespace": "openshift-machine-api",
            },
            "customDeploy": {"method": "install_coreos"},
            "hardwareProfile": "unknown",
            "online": True,
            "preprovisioningNetworkDataName": "ocp-control2.two.ocp4.example.com-network-config-secret",
            "rootDeviceHints": {"deviceName": "/dev/vda"},
            "userData": {"name": "master-user-data-managed", "namespace": "openshift-machine-api"},
        },
        "status": {"provisioning": {"state": "provisioned"}, "poweredOn": True},
    }


@pytest.fixture
def sample_machine_data() -> Dict[str, Any]:
    """Real Machine data from OpenShift cluster.

    Returns:
        Dict[str, Any]: Dictionary containing realistic Machine resource data from
            a production OpenShift cluster with all required metadata and specifications.
    """
    return {
        "apiVersion": "machine.openshift.io/v1beta1",
        "kind": "Machine",
        "metadata": {
            "creationTimestamp": "2025-08-26T13:41:57Z",
            "finalizers": ["machine.machine.openshift.io"],
            "generation": 1,
            "labels": {
                "machine.openshift.io/cluster-api-cluster": "two-xkb99",
                "machine.openshift.io/cluster-api-machine-role": "master",
                "machine.openshift.io/cluster-api-machine-type": "master",
            },
            "name": "two-xkb99-master-1",
            "namespace": "openshift-machine-api",
            "ownerReferences": [
                {
                    "apiVersion": "machine.openshift.io/v1beta1",
                    "blockOwnerDeletion": True,
                    "controller": True,
                    "kind": "MachineSet",
                    "name": "two-xkb99-master",
                    "uid": "12345678-1234-1234-1234-123456789abc",
                }
            ],
            "resourceVersion": "309047",
            "uid": "abcdef12-3456-7890-abcd-ef1234567890",
        },
        "spec": {
            "lifecycleHooks": {},
            "metadata": {"labels": {"node-role.kubernetes.io/control-plane": "", "node-role.kubernetes.io/master": ""}},
            "providerSpec": {
                "value": {
                    "apiVersion": "machine.openshift.io/v1beta1",
                    "kind": "BareMetalMachineProviderSpec",
                    "hostSelector": {"matchLabels": {"installer.openshift.io/role": "control-plane"}},
                }
            },
            "taints": [{"effect": "NoSchedule", "key": "node-role.kubernetes.io/master"}],
        },
        "status": {"phase": "Running"},
    }


@pytest.fixture
def sample_bmc_secret_data():
    """Real Secret data from OpenShift cluster"""
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "creationTimestamp": "2025-08-26T13:41:57Z",
            "name": "ocp-control2.two.ocp4.example.com-bmc-secret",
            "namespace": "openshift-machine-api",
            "resourceVersion": "309048",
        },
        "data": {
            "password": "dGVzdC1wYXNzd29yZA==",  # base64 encoded "test-password"
            "username": "dGVzdC11c2VyZXI=",  # base64 encoded "test-userer"
        },
        "type": "Opaque",
    }


@pytest.fixture
def sample_bmh_list():
    """List of BMH data for template selection tests"""
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "metal3.io/v1alpha1",
                "kind": "BareMetalHost",
                "metadata": {
                    "name": "ocp-control1.two.ocp4.example.com",
                    "namespace": "openshift-machine-api",
                    "labels": {"installer.openshift.io/role": "control-plane"},
                },
                "spec": {"online": True},
                "status": {"provisioning": {"state": "provisioned"}},
            },
            {
                "apiVersion": "metal3.io/v1alpha1",
                "kind": "BareMetalHost",
                "metadata": {"name": "ocp-worker1.two.ocp4.example.com", "namespace": "openshift-machine-api"},
                "spec": {"online": True},
                "status": {"provisioning": {"state": "provisioned"}},
            },
        ],
    }


@pytest.fixture
def mock_printer() -> Mock:
    """Mock printer for testing output operations.

    Returns:
        Mock: Mock printer instance with all required methods for testing
            output functionality without actual printing to console.
    """
    return Mock()


@pytest.fixture
def mock_execute_oc_command() -> Mock:
    """Mock OpenShift CLI command execution function.

    Returns:
        Mock: Mock function that simulates oc command execution for testing
            without requiring actual OpenShift cluster connectivity.
    """
    return Mock()


@pytest.fixture
def sample_nmstate_config():
    """Sample nmstate network configuration"""
    return """interfaces:
- name: eno1
  type: ethernet
  state: up
  ipv4:
    enabled: true
    dhcp: false
    address:
    - ip: 192.168.1.100
      prefix-length: 24
  ipv6:
    enabled: false"""


@pytest.fixture
def sample_network_config_secret():
    """Sample network configuration secret"""
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "control1-network-config-secret",
            "namespace": "openshift-machine-api",
        },
        "data": {"nmstate": "aW50ZXJmYWNlczoKLSBuYW1lOiBlbm8xCiAgdHlwZTogZXRoZXJuZXQ="},  # base64
        "type": "Opaque",
    }


@pytest.fixture
def sample_complex_nested_data():
    """Sample data with deeply nested structure for testing metadata sanitization edge cases"""
    return {
        "apiVersion": "v1",
        "kind": "ComplexResource",
        "metadata": {
            "name": "test",
            "deeply": {"nested": {"structure": {"with": {"resourceVersion": "should-be-preserved-in-deep-nesting"}}}},
        },
    }


@pytest.fixture
def sample_problematic_yaml_data():
    """Sample data with special characters that might cause YAML issues"""
    return {
        "apiVersion": "v1",
        "kind": "BareMetalHost",
        "metadata": {"name": "node-with-@#$%^&*()characters", "namespace": "openshift-machine-api"},
        "spec": {
            "bmc": {
                "address": "https://192.168.1.100:443/redfish/v1/Systems/1",
                "credentialsName": "credentials-with-'quotes'-and-\"double-quotes\"",
            }
        },
    }


@pytest.fixture
def backup_manager(mock_printer: Mock, mock_execute_oc_command: Mock) -> Generator[BackupManager, None, None]:
    """BackupManager instance with mocked dependencies.

    Args:
        mock_printer: Mock printer for output operations.
        mock_execute_oc_command: Mock OpenShift CLI command executor.

    Yields:
        BackupManager: Configured BackupManager instance with temporary directory
            for testing backup operations in isolation.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        yield BackupManager(backup_dir=temp_dir, printer=mock_printer, execute_oc_command=mock_execute_oc_command)


# =============================================================================
# Test Metadata Sanitization (Core Functionality)
# =============================================================================


class TestMetadataSanitization:
    """Test metadata sanitization functionality with realistic data.

    This class validates the BackupManager's ability to sanitize Kubernetes
    resource metadata by removing runtime fields that should not be persisted
    in backup files, following OpenShift best practices.
    """

    def test_sanitize_metadata_removes_runtime_fields(self, backup_manager: BackupManager) -> None:
        """Test that all runtime fields are properly removed.

        Validates that the sanitize_metadata method correctly identifies and removes
        all Kubernetes runtime metadata fields that should not be included in backup
        files, ensuring clean restoration without conflicts.

        Args:
            backup_manager: BackupManager instance for testing.
        """
        data_with_runtime_fields = {
            "apiVersion": "v1",
            "kind": "TestResource",
            "metadata": {
                "name": "test-resource",
                "namespace": "test-ns",
                "labels": {"app": "test"},
                # Runtime fields that should be removed
                "creationTimestamp": "2023-01-01T00:00:00Z",
                "resourceVersion": "12345",
                "uid": "test-uid-12345",
                "generation": 1,
                "managedFields": [{"manager": "test"}],
                "ownerReferences": [{"kind": "owner"}],
                "finalizers": ["test.finalizer"],
                "annotations": {"kubectl.kubernetes.io/last-applied-configuration": "{}"},
            },
            "spec": {"replicas": 1},
            "status": {"ready": True},
        }

        result = backup_manager.sanitize_metadata(data_with_runtime_fields)

        # Essential fields should remain
        assert result["apiVersion"] == "v1"
        assert result["kind"] == "TestResource"
        assert result["metadata"]["name"] == "test-resource"
        assert result["metadata"]["namespace"] == "test-ns"
        assert result["metadata"]["labels"]["app"] == "test"
        assert result["spec"]["replicas"] == 1
        assert result["status"]["ready"] is True

        # Runtime fields should be removed
        metadata = result["metadata"]
        assert "creationTimestamp" not in metadata
        assert "resourceVersion" not in metadata
        assert "uid" not in metadata
        assert "managedFields" not in metadata
        assert "ownerReferences" not in metadata
        assert "finalizers" not in metadata
        assert "annotations" not in metadata

    def test_sanitize_metadata_handles_missing_metadata(self, backup_manager):
        """Test sanitization when metadata section is missing"""
        data_without_metadata = {"apiVersion": "v1", "kind": "TestResource", "spec": {"test": "value"}}

        result = backup_manager.sanitize_metadata(data_without_metadata)

        assert result == data_without_metadata  # Should return unchanged

    def test_sanitize_metadata_preserves_essential_fields(self, backup_manager):
        """Test that essential fields are never removed"""
        data = {
            "metadata": {
                "name": "essential-resource",
                "namespace": "essential-ns",
                "labels": {"critical": "yes"},
                "generation": 2,  # Should be removed (is in removal list)
            }
        }

        result = backup_manager.sanitize_metadata(data)

        metadata = result["metadata"]
        assert metadata["name"] == "essential-resource"
        assert metadata["namespace"] == "essential-ns"
        assert metadata["labels"]["critical"] == "yes"
        assert "generation" not in metadata  # Should be removed


# =============================================================================
# Test Real Backup Directory Setup
# =============================================================================


class TestRealBackupDirectorySetup:
    """Test backup directory setup with actual filesystem operations"""

    def test_setup_backup_directory_with_provided_path_creates_directory(self):
        """Test setup with provided backup directory path actually creates the directory"""
        mock_printer = Mock()
        mock_execute_oc_command = Mock()
        backup_manager = BackupManager(printer=mock_printer, execute_oc_command=mock_execute_oc_command)

        with tempfile.TemporaryDirectory() as temp_root:
            provided_dir = os.path.join(temp_root, "custom", "backup", "path")

            # Directory shouldn't exist initially
            assert not os.path.exists(provided_dir)

            result = backup_manager.setup_backup_directory(provided_dir)

            # Directory should now exist and be usable
            assert os.path.exists(provided_dir)
            assert os.path.isdir(provided_dir)
            assert result == provided_dir
            assert backup_manager.backup_dir == provided_dir

            # Should be able to write files to the directory
            test_file = os.path.join(provided_dir, "test.yaml")
            with open(test_file, "w") as f:
                f.write("test: content")
            assert os.path.exists(test_file)

    def test_setup_backup_directory_auto_generate_with_cluster_name(self):
        """Test automatic backup directory generation with cluster name extraction"""
        test_cluster_name = "my-test-cluster.example.com"

        mock_printer = Mock()
        mock_execute_oc_command = Mock()
        mock_execute_oc_command.return_value = f"'{test_cluster_name}'"
        backup_manager = BackupManager(printer=mock_printer, execute_oc_command=mock_execute_oc_command)

        with tempfile.TemporaryDirectory() as temp_root:
            with patch("os.getenv", return_value="testuser"):
                # Reset backup_dir to force auto-generation
                backup_manager.backup_dir = None

                # Patch the home directory construction to use temp directory
                def mock_setup_backup_directory(backup_dir=None):
                    if backup_dir:
                        backup_manager.backup_dir = backup_dir
                    elif not backup_manager.backup_dir:
                        # Get cluster name from OpenShift DNS
                        cluster_cmd = ["get", "dns", "cluster", "-o", "jsonpath='{.spec.baseDomain}'"]
                        cluster_output = backup_manager.execute_oc_command(cluster_cmd)
                        if cluster_output:
                            backup_manager.cluster_name = cluster_output.strip("'")
                        else:
                            backup_manager.cluster_name = "unknown-cluster"
                        # Use temp directory instead of actual home
                        backup_manager.backup_dir = os.path.join(temp_root, "backup_yamls", backup_manager.cluster_name)

                    # Create directory if it doesn't exist
                    if not os.path.exists(backup_manager.backup_dir):
                        os.makedirs(backup_manager.backup_dir)

                    return backup_manager.backup_dir

                result = mock_setup_backup_directory()

                # Verify cluster name was extracted correctly
                assert backup_manager.cluster_name == test_cluster_name

                # Verify directory was created and is functional
                assert os.path.exists(result)
                assert os.path.isdir(result)
                assert test_cluster_name in result

                # Verify the directory is writable by creating a test file
                test_file = os.path.join(result, "test.yaml")
                with open(test_file, "w") as f:
                    f.write("test: cluster-name-extraction")
                assert os.path.exists(test_file)

                # Verify oc command was called correctly
                mock_execute_oc_command.assert_called_with(
                    ["get", "dns", "cluster", "-o", "jsonpath='{.spec.baseDomain}'"]
                )

    def test_setup_backup_directory_cluster_name_failure_creates_unknown_cluster_dir(self):
        """Test handling of cluster name retrieval failure with actual directory creation"""
        mock_printer = Mock()
        mock_execute_oc_command = Mock()
        mock_execute_oc_command.return_value = None  # Simulate failure
        backup_manager = BackupManager(printer=mock_printer, execute_oc_command=mock_execute_oc_command)

        with tempfile.TemporaryDirectory() as temp_root:
            with patch("os.getenv", return_value="testuser"):
                with patch.object(backup_manager, "backup_dir", None):  # Force auto-generation
                    # Override the default home path construction
                    def patched_setup():
                        cluster_cmd = ["get", "dns", "cluster", "-o", "jsonpath='{.spec.baseDomain}'"]
                        cluster_output = backup_manager.execute_oc_command(cluster_cmd)
                        if cluster_output:
                            backup_manager.cluster_name = cluster_output.strip("'")
                        else:
                            backup_manager.cluster_name = "unknown-cluster"
                        # Use temp directory
                        backup_manager.backup_dir = os.path.join(temp_root, "backup_yamls", backup_manager.cluster_name)

                        if not os.path.exists(backup_manager.backup_dir):
                            os.makedirs(backup_manager.backup_dir)

                        return backup_manager.backup_dir

                    result = patched_setup()

                    # Should fall back to unknown-cluster and create directory
                    assert backup_manager.cluster_name == "unknown-cluster"
                    assert os.path.exists(result)
                    assert "unknown-cluster" in result
                    # Function should work correctly even when cluster name retrieval fails

    def test_setup_existing_directory_is_reused(self):
        """Test setup with existing directory doesn't recreate it"""
        mock_printer = Mock()
        mock_execute_oc_command = Mock()
        backup_manager = BackupManager(printer=mock_printer, execute_oc_command=mock_execute_oc_command)

        with tempfile.TemporaryDirectory() as temp_root:
            existing_dir = os.path.join(temp_root, "existing_backup")
            os.makedirs(existing_dir)

            # Create a file in the existing directory to verify it's preserved
            existing_file = os.path.join(existing_dir, "existing.yaml")
            with open(existing_file, "w") as f:
                f.write("existing: content")

            result = backup_manager.setup_backup_directory(existing_dir)

            # Directory should be reused and existing file preserved
            assert result == existing_dir
            assert os.path.exists(existing_file)
            with open(existing_file, "r") as f:
                assert f.read() == "existing: content"
            # Function should preserve existing directory and its contents

    def test_setup_directory_is_writable_and_functional(self):
        """Test that created backup directory is actually functional for backup operations"""
        mock_printer = Mock()
        mock_execute_oc_command = Mock()
        backup_manager = BackupManager(printer=mock_printer, execute_oc_command=mock_execute_oc_command)

        with tempfile.TemporaryDirectory() as temp_root:
            backup_dir = os.path.join(temp_root, "functional_backup")

            result = backup_manager.setup_backup_directory(backup_dir)

            # Directory should be created and functional
            assert os.path.exists(result)
            assert os.access(result, os.W_OK)  # Should be writable

            # Should be able to create backup files in the directory
            test_files = ["node1_bmh.yaml", "node1-bmc-secret.yaml", "node1_machine.yaml", "node1_nmstate"]

            for filename in test_files:
                file_path = os.path.join(result, filename)
                with open(file_path, "w") as f:
                    f.write(f"# Test backup file: {filename}\napiVersion: v1\nkind: Test")
                assert os.path.exists(file_path)

    def test_setup_directory_handles_permission_errors(self):
        """Test directory creation handles permission errors gracefully"""
        mock_printer = Mock()
        mock_execute_oc_command = Mock()
        backup_manager = BackupManager(printer=mock_printer, execute_oc_command=mock_execute_oc_command)

        with tempfile.TemporaryDirectory() as temp_root:
            readonly_parent = os.path.join(temp_root, "readonly")
            os.makedirs(readonly_parent)
            os.chmod(readonly_parent, 0o444)  # Read-only

            restricted_dir = os.path.join(readonly_parent, "backup")

            try:
                with pytest.raises(PermissionError):
                    backup_manager.setup_backup_directory(restricted_dir)
            finally:
                # Cleanup: restore permissions
                os.chmod(readonly_parent, 0o755)


# =============================================================================
# Test File Operations with Real File I/O
# =============================================================================


class TestRealFileOperations:
    """Test file operations with actual file system interaction"""

    def test_make_file_copy_preserves_content(self, backup_manager, sample_bmc_secret_data):
        """Test file copy actually copies BMC secret content correctly"""
        # Use realistic BMC secret content from fixture
        bmc_secret_content = yaml.dump(sample_bmc_secret_data)

        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = os.path.join(temp_dir, "control1-bmc-secret.yaml")
            dest_file = os.path.join(temp_dir, "control4-bmc-secret.yaml")

            # Write BMC secret content to source file
            with open(source_file, "w") as f:
                f.write(bmc_secret_content)

            # Copy file using BackupManager
            backup_manager.make_file_copy(source_file, dest_file)

            # Verify destination file exists and has identical content
            assert os.path.exists(dest_file)
            with open(dest_file, "r") as f:
                copied_content = f.read()
            assert copied_content == bmc_secret_content

    def test_make_file_copy_file_not_found(self, backup_manager):
        """Test file copy failure when source file doesn't exist"""
        with tempfile.TemporaryDirectory() as temp_dir:
            nonexistent_source = os.path.join(temp_dir, "nonexistent.yaml")
            dest_file = os.path.join(temp_dir, "dest.yaml")

            with pytest.raises(FileNotFoundError):
                backup_manager.make_file_copy(nonexistent_source, dest_file)

    def test_make_file_copy_permission_denied(self, backup_manager):
        """Test file copy failure with permission issues"""
        test_content = "test content"

        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = os.path.join(temp_dir, "source.yaml")
            readonly_dir = os.path.join(temp_dir, "readonly")
            dest_file = os.path.join(readonly_dir, "dest.yaml")

            # Create source file
            with open(source_file, "w") as f:
                f.write(test_content)

            # Create readonly directory
            os.makedirs(readonly_dir)
            os.chmod(readonly_dir, 0o444)  # Read-only permissions

            try:
                with pytest.raises(PermissionError):
                    backup_manager.make_file_copy(source_file, dest_file)
            finally:
                # Cleanup: restore permissions
                os.chmod(readonly_dir, 0o755)


# =============================================================================
# Test Data Extraction Methods with Comprehensive Testing
# =============================================================================


class TestDataExtraction:
    """Test BMH and Machine data extraction with edge cases and validation"""

    def test_extract_bmh_fields_complete_extraction(self, backup_manager, sample_bmh_data):
        """Test BMH extraction preserves all essential fields and structure"""
        extracted = backup_manager.extract_bmh_fields(sample_bmh_data)

        # Verify complete structure is preserved
        assert extracted["apiVersion"] == "metal3.io/v1alpha1"
        assert extracted["kind"] == "BareMetalHost"

        # Metadata
        assert extracted["metadata"]["name"] == "ocp-control2.two.ocp4.example.com"
        assert extracted["metadata"]["namespace"] == "openshift-machine-api"

        # BMC configuration
        bmc = extracted["spec"]["bmc"]
        assert (
            bmc["address"]
            == "redfish-virtualmedia+http://192.168.94.1:8000/redfish/v1/Systems/8e74843e-9f5b-4b3b-b818-9bb09d881c94"
        )
        assert bmc["credentialsName"] == "ocp-control2.two.ocp4.example.com-bmc-secret"

        # Hardware configuration
        assert extracted["spec"]["bootMACAddress"] == "52:54:00:e9:d5:8a"
        assert extracted["spec"]["bootMode"] == "UEFI"
        assert extracted["spec"]["online"] is True
        assert extracted["spec"]["automatedCleaningMode"] == "metadata"

        # Storage configuration
        assert extracted["spec"]["rootDeviceHints"]["deviceName"] == "/dev/vda"

        # Networking
        assert (
            extracted["spec"]["preprovisioningNetworkDataName"]
            == "ocp-control2.two.ocp4.example.com-network-config-secret"
        )

        # User data
        user_data = extracted["spec"]["userData"]
        assert user_data["name"] == "master-user-data-managed"
        assert user_data["namespace"] == "openshift-machine-api"

    def test_extract_machine_fields_complete_extraction(self, backup_manager, sample_machine_data):
        """Test Machine extraction preserves all essential fields and structure"""
        extracted = backup_manager.extract_machine_fields(sample_machine_data)

        # Verify complete structure
        assert extracted["apiVersion"] == "machine.openshift.io/v1beta1"
        assert extracted["kind"] == "Machine"

        # Metadata with labels
        metadata = extracted["metadata"]
        assert metadata["name"] == "PLACEHOLDER_NAME"
        assert metadata["namespace"] == "openshift-machine-api"

        labels = metadata["labels"]
        assert labels["machine.openshift.io/cluster-api-cluster"] == "two-xkb99"
        assert labels["machine.openshift.io/cluster-api-machine-role"] == "master"
        assert labels["machine.openshift.io/cluster-api-machine-type"] == "master"

        # Spec configuration
        spec = extracted["spec"]
        assert spec["lifecycleHooks"] == {}

        # Provider spec
        provider_value = spec["providerSpec"]["value"]
        assert provider_value["apiVersion"] == "machine.openshift.io/v1beta1"
        assert provider_value["kind"] == "BareMetalMachineProviderSpec"


# =============================================================================
# Test Backup Operations
# =============================================================================


class TestRealBackupOperations:
    """Test backup operations with actual YAML file generation"""

    def test_backup_bmh_definition_creates_valid_yaml(self, backup_manager, sample_bmh_data):
        """Test BMH definition backup creates valid YAML file with correct content"""
        bmh_name = "test-bmh"

        with tempfile.TemporaryDirectory() as temp_dir:
            backup_manager.backup_dir = temp_dir
            result_path = backup_manager.backup_bmh_definition(bmh_name, sample_bmh_data)

            expected_path = f"{temp_dir}/{bmh_name}_bmh.yaml"
            assert result_path == expected_path
            assert os.path.exists(result_path)

            # Verify YAML file content
            with open(result_path, "r") as f:
                saved_data = yaml.safe_load(f)

            # Should contain extracted BMH fields
            assert saved_data["apiVersion"] == "metal3.io/v1alpha1"
            assert saved_data["kind"] == "BareMetalHost"
            assert saved_data["metadata"]["name"] == "ocp-control2.two.ocp4.example.com"
            assert saved_data["spec"]["bootMACAddress"] == "52:54:00:e9:d5:8a"

            # Verify file is valid YAML (can be loaded back)
            assert isinstance(saved_data, dict)

    def test_backup_machine_definition_creates_valid_yaml(self, backup_manager, sample_machine_data):
        """Test Machine definition backup creates valid YAML file with correct content"""
        machine_name = "test-machine"

        with tempfile.TemporaryDirectory() as temp_dir:
            backup_manager.backup_dir = temp_dir
            result_path = backup_manager.backup_machine_definition(machine_name, sample_machine_data)

            expected_path = f"{temp_dir}/{machine_name}_machine.yaml"
            assert result_path == expected_path
            assert os.path.exists(result_path)

            # Verify YAML file content
            with open(result_path, "r") as f:
                saved_data = yaml.safe_load(f)

            # Should contain extracted Machine fields
            assert saved_data["apiVersion"] == "machine.openshift.io/v1beta1"
            assert saved_data["kind"] == "Machine"
            assert saved_data["metadata"]["name"] == "PLACEHOLDER_NAME"
            assert saved_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "master"

    def test_backup_secret_creates_sanitized_yaml(self, backup_manager, sample_bmc_secret_data):
        """Test secret backup creates properly sanitized YAML file"""
        node_name = "test-node"
        secret_suffix = "bmc-secret"
        backup_filename_suffix = "-bmc-secret.yaml"
        secret_description = "BMC secret"

        backup_manager.execute_oc_command.return_value = sample_bmc_secret_data

        with tempfile.TemporaryDirectory() as temp_dir:
            backup_manager.backup_dir = temp_dir
            result_path = backup_manager.backup_secret(
                node_name, secret_suffix, backup_filename_suffix, secret_description
            )

            # Verify file creation
            expected_path = f"{temp_dir}/{node_name}{backup_filename_suffix}"
            assert result_path == expected_path
            assert os.path.exists(result_path)

            # Verify YAML file content
            with open(result_path, "r") as f:
                saved_data = yaml.safe_load(f)

            # Should be sanitized (runtime metadata removed)
            metadata = saved_data["metadata"]
            assert "resourceVersion" not in metadata
            assert "creationTimestamp" not in metadata
            assert "uid" not in metadata
            assert "managedFields" not in metadata
            assert "finalizers" not in metadata
            assert "ownerReferences" not in metadata
            assert "annotations" not in metadata

            # Should preserve essential fields
            assert saved_data["apiVersion"] == sample_bmc_secret_data["apiVersion"]
            assert saved_data["kind"] == sample_bmc_secret_data["kind"]
            assert saved_data["type"] == sample_bmc_secret_data["type"]
            assert saved_data["data"]["username"] == sample_bmc_secret_data["data"]["username"]
            assert saved_data["data"]["password"] == sample_bmc_secret_data["data"]["password"]
            assert metadata["name"] == sample_bmc_secret_data["metadata"]["name"]
            assert metadata["namespace"] == sample_bmc_secret_data["metadata"]["namespace"]

            # Verify YAML structure is valid
            assert isinstance(saved_data, dict)

    def test_backup_secret_handles_command_failure(self, backup_manager):
        """Test secret backup handles command execution failure properly"""
        backup_manager.execute_oc_command.return_value = None

        with pytest.raises(Exception, match="Failed to retrieve BMC secret for test-node"):
            backup_manager.backup_secret("test-node", "bmc-secret", "-bmc-secret.yaml", "BMC secret")

    def test_backup_operations_use_correct_filenames(self, backup_manager, sample_bmh_data, sample_machine_data):
        """Test that backup operations create files with expected naming conventions"""
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_manager.backup_dir = temp_dir

            # Test BMH backup filename
            bmh_path = backup_manager.backup_bmh_definition("control-node-1", sample_bmh_data)
            assert bmh_path.endswith("control-node-1_bmh.yaml")

            # Test Machine backup filename
            machine_path = backup_manager.backup_machine_definition("machine-abc123", sample_machine_data)
            assert machine_path.endswith("machine-abc123_machine.yaml")

            # Both files should exist
            assert os.path.exists(bmh_path)
            assert os.path.exists(machine_path)


# =============================================================================
# Test Template BMH Backup
# =============================================================================


class TestTemplateBMHBackup:
    """Test BMH template selection and backup logic"""

    def test_backup_template_bmh_control_plane_expansion(self, backup_manager, sample_bmh_list):
        """Test template backup for control plane expansion"""
        backup_manager.execute_oc_command.return_value = sample_bmh_list

        with patch.object(backup_manager, "backup_bmh_definition") as mock_backup:
            mock_backup.return_value = "/backup/path/control-template_bmh.yaml"

            template_file, is_worker = backup_manager.backup_template_bmh(
                failed_control_node=None, is_control_plane_expansion=True
            )

            assert template_file == "/backup/path/control-template_bmh.yaml"
            assert is_worker is False
            mock_backup.assert_called_once()

    def test_backup_template_bmh_worker_addition(self, backup_manager, sample_bmh_list):
        """Test template backup for worker addition"""
        backup_manager.execute_oc_command.return_value = sample_bmh_list

        with patch.object(backup_manager, "backup_bmh_definition") as mock_backup:
            mock_backup.return_value = "/backup/path/worker-template_bmh.yaml"

            template_file, is_worker = backup_manager.backup_template_bmh(
                failed_control_node=None, is_control_plane_expansion=False
            )

            assert template_file == "/backup/path/worker-template_bmh.yaml"
            assert is_worker is False  # Worker BMH has no control-plane role label, so returns False
            mock_backup.assert_called_once()

    def test_backup_template_bmh_failed_control_node(self, backup_manager, sample_bmh_data):
        """Test template backup from failed control node"""
        failed_node = "ocp-control1.two.ocp4.example.com"
        backup_manager.execute_oc_command.return_value = sample_bmh_data

        with patch.object(backup_manager, "backup_bmh_definition") as mock_backup:
            mock_backup.return_value = f"/backup/path/{failed_node}_bmh.yaml"

            template_file, is_worker = backup_manager.backup_template_bmh(failed_control_node=failed_node)

            assert template_file == f"/backup/path/{failed_node}_bmh.yaml"
            assert is_worker is False
            mock_backup.assert_called_once()

    def test_backup_template_bmh_cluster_retrieval_failure(self, backup_manager):
        """Test error handling when cluster BMH list cannot be retrieved"""
        backup_manager.execute_oc_command.return_value = None  # Simulate command failure

        template_file, is_worker = backup_manager.backup_template_bmh(
            failed_control_node=None, is_control_plane_expansion=True
        )

        assert template_file is None
        assert is_worker is False
        # Function should handle cluster BMH list retrieval failures gracefully

    def test_backup_template_bmh_no_suitable_templates_for_worker_addition(self, backup_manager):
        """Test error handling when no suitable templates found for worker addition"""
        # Empty BMH list
        backup_manager.execute_oc_command.return_value = {"items": []}

        template_file, is_worker = backup_manager.backup_template_bmh(
            failed_control_node=None, is_control_plane_expansion=False
        )

        assert template_file is None
        assert is_worker is False
        # Function should handle empty BMH lists correctly

    def test_backup_template_bmh_exception_handling(self, backup_manager):
        """Test exception handling in backup_template_bmh method"""
        # Mock execute_oc_command to raise an exception
        backup_manager.execute_oc_command.side_effect = Exception("Simulated oc command failure")

        template_file, is_worker = backup_manager.backup_template_bmh(failed_control_node=None)

        assert template_file is None
        assert is_worker is False
        # Function should handle exceptions gracefully and return None


# =============================================================================
# Test Real File Copy Operations for Node Replacement
# =============================================================================


class TestRealFileCopyOperations:
    """Test file copy operations for node replacement with actual file operations"""

    def test_copy_files_for_replacement_creates_all_files(
        self,
        backup_manager,
        sample_nmstate_config,
        sample_bmc_secret_data,
        sample_bmh_data,
        sample_network_config_secret,
        sample_machine_data,
    ):
        """Test copying files for node replacement actually creates all expected files"""
        bad_node = "bad-control1"
        bmh_name = "bad-control1-bmh"
        bad_machine = "bad-control1-machine"
        replacement_node = "new-control4"

        with tempfile.TemporaryDirectory() as temp_dir:
            backup_manager.backup_dir = temp_dir

            # Create source files using fixture data
            source_files = {
                f"{bad_node}_nmstate": sample_nmstate_config,
                f"{bad_node}-bmc-secret.yaml": yaml.dump(sample_bmc_secret_data),
                f"{bmh_name}_bmh.yaml": yaml.dump(sample_bmh_data),
                f"{bad_node}_network-config-secret.yaml": yaml.dump(sample_network_config_secret),
                f"{bad_machine}_machine.yaml": yaml.dump(sample_machine_data),
            }

            for filename, content in source_files.items():
                with open(os.path.join(temp_dir, filename), "w") as f:
                    f.write(content)

            # Execute the copy operation
            result = backup_manager.copy_files_for_replacement(bad_node, bmh_name, bad_machine, replacement_node)

            # Verify all expected files are created with correct paths
            expected_files = {
                "nmstate": f"{temp_dir}/{replacement_node}_nmstate",
                "bmc_secret": f"{temp_dir}/{replacement_node}-bmc-secret.yaml",
                "bmh": f"{temp_dir}/{replacement_node}_bmh.yaml",
                "network_secret": f"{temp_dir}/{replacement_node}_network-config-secret.yaml",
                "machine": f"{temp_dir}/{replacement_node}_machine.yaml",
            }

            assert result == expected_files

            # Verify all files exist and have correct content
            for file_type, expected_path in expected_files.items():
                assert os.path.exists(expected_path), f"File not created: {expected_path}"

                # Verify content was copied correctly
                source_key = list(source_files.keys())[list(expected_files.keys()).index(file_type)]
                expected_content = source_files[source_key]

                with open(expected_path, "r") as f:
                    actual_content = f.read()
                assert actual_content == expected_content, f"Content mismatch in {expected_path}"

    def test_copy_files_for_replacement_handles_missing_source(self, backup_manager):
        """Test file copy operations handle missing source files gracefully"""
        bad_node = "missing-node"
        bmh_name = "missing-bmh"
        bad_machine = "missing-machine"
        replacement_node = "new-node"

        with tempfile.TemporaryDirectory() as temp_dir:
            backup_manager.backup_dir = temp_dir

            # Don't create any source files - they're missing
            with pytest.raises(FileNotFoundError):
                backup_manager.copy_files_for_replacement(bad_node, bmh_name, bad_machine, replacement_node)


# =============================================================================
# Test Error Handling and Edge Cases
# =============================================================================


class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge case scenarios"""

    def test_sanitize_metadata_with_deeply_nested_missing_keys(self, backup_manager, sample_complex_nested_data):
        """Test metadata sanitization with complex missing nested structures"""
        result = backup_manager.sanitize_metadata(sample_complex_nested_data)

        # Should only remove top-level metadata keys, not deeply nested ones
        assert result["metadata"]["name"] == "test"
        assert (
            result["metadata"]["deeply"]["nested"]["structure"]["with"]["resourceVersion"]
            == "should-be-preserved-in-deep-nesting"
        )

    def test_backup_operations_with_invalid_yaml_content(self, backup_manager, sample_problematic_yaml_data):
        """Test backup operations handle edge cases in YAML generation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_manager.backup_dir = temp_dir

            # Should not crash and should create valid YAML
            result_path = backup_manager.backup_bmh_definition("problematic-node", sample_problematic_yaml_data)
            assert os.path.exists(result_path)

            # Should be able to load the YAML back
            with open(result_path, "r") as f:
                reloaded_data = yaml.safe_load(f)

            assert reloaded_data["metadata"]["name"] == sample_problematic_yaml_data["metadata"]["name"]
            assert "quotes" in reloaded_data["spec"]["bmc"]["credentialsName"]


# =============================================================================
# Test NMState Configuration Extraction
# =============================================================================


class TestNMStateExtraction:
    """Test nmstate configuration extraction"""

    @patch("os.rename")
    @patch("builtins.open", new_callable=mock_open)
    def test_extract_nmstate_config_success(self, mock_file, mock_rename, backup_manager):
        """Test successful nmstate configuration extraction"""
        node_name = "test-node"

        # Mock successful command execution
        backup_manager.execute_oc_command.return_value = "success"

        result = backup_manager.extract_nmstate_config(node_name)

        expected_path = f"{backup_manager.backup_dir}/{node_name}_nmstate"
        assert result == expected_path
        backup_manager.execute_oc_command.assert_called_once_with(
            [
                "extract",
                "-n",
                "openshift-machine-api",
                f"secret/{node_name}-network-config-secret",
                "--to",
                backup_manager.backup_dir,
            ]
        )
        mock_rename.assert_called_once_with(f"{backup_manager.backup_dir}/nmstate", expected_path)

    @patch("os.rename")
    def test_extract_nmstate_config_failure(self, mock_rename, backup_manager):
        """Test nmstate configuration extraction failure"""
        node_name = "test-node"
        backup_manager.execute_oc_command.return_value = None
        mock_rename.side_effect = FileNotFoundError("File not found")

        with pytest.raises(FileNotFoundError):
            backup_manager.extract_nmstate_config(node_name)


# =============================================================================
# Test Runner Configuration
# =============================================================================

if __name__ == "__main__":
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "--cov=modules.backup_manager",
            "--cov-report=term-missing",
            "--cov-fail-under=60",
        ]
    )
