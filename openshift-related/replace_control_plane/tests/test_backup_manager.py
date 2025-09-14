#!/usr/bin/env python3
"""
Comprehensive pytest tests for BackupManager class.
Tests all methods with realistic OpenShift data following enterprise Python standards.

This module provides comprehensive test coverage for the BackupManager class,
validating backup and restore operations for OpenShift node replacement scenarios.
All tests follow enterprise-grade patterns with proper type annotations,
comprehensive error handling, and realistic test data.

🤖 AI Attribution: Test suite generated using Cursor.ai with human-in-the-loop review and validation.
Development Process: AI-generated code → Human review → Refinement → Integration
"""

import pytest
import os
import sys
import tempfile
import yaml
from pathlib import Path
from typing import Any, Dict, Generator

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import Mock, patch, mock_open  # noqa: E402
from modules.backup_manager import BackupManager  # noqa: E402


# =============================================================================
# Test Fixtures - Static Data from Real OpenShift Cluster
# =============================================================================


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


# =============================================================================
# Test Metadata Sanitization (Core Functionality)
# =============================================================================


class TestMetadataSanitization:
    """Test metadata sanitization functionality with realistic data.

    This class validates the BackupManager's ability to sanitize Kubernetes
    resource metadata by removing runtime fields that should not be persisted
    in backup files, following OpenShift best practices.
    """

    def test_sanitize_metadata_removes_runtime_fields(
        self, backup_manager: BackupManager, sample_resource_with_runtime_metadata: dict
    ) -> None:
        """Test that all runtime fields are properly removed.

        Validates that the sanitize_metadata method correctly identifies and removes
        all Kubernetes runtime metadata fields that should not be included in backup
        files, ensuring clean restoration without conflicts.

        Args:
            backup_manager: BackupManager instance for testing.
            sample_resource_with_runtime_metadata: Fixture providing test resource with runtime fields.
        """
        result = backup_manager.sanitize_metadata(sample_resource_with_runtime_metadata)

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


class TestBackupDirectorySetup:
    """Test backup directory setup with essential business logic validation"""

    def test_directory_creation_and_functionality(self):
        """Test backup directory creation, reuse, and basic functionality"""
        mock_printer = Mock()
        mock_execute_oc_command = Mock()
        backup_manager = BackupManager(printer=mock_printer, execute_oc_command=mock_execute_oc_command)

        with tempfile.TemporaryDirectory() as temp_root:
            # Test 1: New directory creation
            new_dir = os.path.join(temp_root, "new_backup")
            assert not os.path.exists(new_dir)

            result = backup_manager.setup_backup_directory(new_dir)
            assert os.path.exists(new_dir) and os.path.isdir(new_dir)
            assert result == new_dir
            assert backup_manager.backup_dir == new_dir

            # Test 2: Directory is functional (can write files)
            test_file = os.path.join(new_dir, "test.yaml")
            with open(test_file, "w") as f:
                f.write("test: content")
            assert os.path.exists(test_file)

            # Test 3: Existing directory reuse preserves content
            existing_dir = os.path.join(temp_root, "existing_backup")
            os.makedirs(existing_dir)
            existing_file = os.path.join(existing_dir, "existing.yaml")
            with open(existing_file, "w") as f:
                f.write("preserved: content")

            result2 = backup_manager.setup_backup_directory(existing_dir)
            assert result2 == existing_dir
            assert os.path.exists(existing_file)
            with open(existing_file, "r") as f:
                assert f.read() == "preserved: content"

    def test_cluster_name_extraction_for_auto_directory_naming(self, mock_backup_manager_factory):
        """Test cluster name extraction for automatic directory generation"""
        test_cluster_name = "test-cluster.example.com"
        backup_manager = mock_backup_manager_factory(cluster_name=test_cluster_name)

        with patch("os.getenv", return_value="testuser"):
            backup_manager.backup_dir = None  # Force auto-generation
            
            with patch("builtins.open", mock_open()):
                with patch("os.makedirs") as mock_makedirs:
                    with patch("os.path.exists", return_value=False):
                        backup_manager.setup_backup_directory()
                        
                        # BUSINESS RULE: Cluster name must be extracted for directory naming
                        assert backup_manager.cluster_name == test_cluster_name
                        backup_manager.execute_oc_command.assert_called_with(
                            ["get", "dns", "cluster", "-o", "jsonpath='{.spec.baseDomain}'"]
                        )
                        
                        # BUSINESS RULE: Directory structure must include cluster name
                        mock_makedirs.assert_called_once()
                        called_path = mock_makedirs.call_args[0][0]
                        assert test_cluster_name in called_path and "backup_yamls" in called_path

# =============================================================================
# Test Data Extraction Methods with Comprehensive Testing
# =============================================================================

class TestDataExtractionAndAccuracy:
    """Test BMH and Machine data extraction with accuracy validation ensuring functional deployment"""

    def test_bmh_extraction_comprehensive_validation(self, backup_manager, sample_bmh_data, resource_validator, bmh_validator):
        """Test BMH extraction preserves all essential configuration and produces deployable configuration"""
        extracted = backup_manager.extract_bmh_fields(sample_bmh_data)

        # BUSINESS RULE: Complete structure must be preserved (using centralized validator)
        resource_validator(extracted, "metal3.io/v1alpha1", "BareMetalHost", "ocp-control2.two.ocp4.example.com")

        # BUSINESS RULE: Hardware management configuration (using centralized BMH validator)
        bmh_validator(extracted, sample_bmh_data)
        assert extracted["spec"]["automatedCleaningMode"] == "metadata"

        # BUSINESS RULE: Network and deployment configuration
        assert (
            extracted["spec"]["preprovisioningNetworkDataName"]
            == "ocp-control2.two.ocp4.example.com-network-config-secret"
        )
        user_data = extracted["spec"]["userData"]
        assert user_data["name"] == "master-user-data-managed"
        assert user_data["namespace"] == "openshift-machine-api"

        # BUSINESS RULE: Extracted BMH must contain all required fields for Metal3 deployment
        required_deployment_fields = [
            ("spec", "bmc", "address"),
            ("spec", "bmc", "credentialsName"), 
            ("spec", "bootMACAddress"),
            ("spec", "bootMode"),
            ("spec", "online"),
            ("spec", "rootDeviceHints", "deviceName")
        ]
        
        for *path, field in required_deployment_fields:
            current = extracted
            for part in path:
                assert part in current, f"Missing deployment path: {'.'.join(path)}"
                current = current[part]
            assert field in current, f"Missing deployment field: {'.'.join(path + [field])}"
            assert current[field] is not None, f"Null deployment field: {'.'.join(path + [field])}"

    def test_bmh_extraction_runtime_field_exclusion(self, backup_manager, sample_bmh_data):
        """Test that BMH extraction correctly excludes Kubernetes-managed runtime fields"""
        # Add runtime fields that should NOT be preserved
        sample_data_with_runtime = sample_bmh_data.copy()
        sample_data_with_runtime["spec"]["consumerRef"] = {"kind": "Machine", "name": "runtime-machine"}
        sample_data_with_runtime["status"] = {"provisioning": {"state": "provisioned"}}
        
        extracted = backup_manager.extract_bmh_fields(sample_data_with_runtime)
        
        # BUSINESS RULE: Runtime fields must be excluded to avoid restoration conflicts
        assert "consumerRef" not in extracted["spec"]
        assert "status" not in extracted
        
        # BUSINESS RULE: Essential fields must still be preserved
        assert "bmc" in extracted["spec"]
        assert "bootMACAddress" in extracted["spec"]

    def test_bmh_network_configuration_preservation(
        self, backup_manager, bmh_factory
    ):
        """Test that BMH extraction preserves network configuration for static IP setups"""
        sample_bmh_with_network_config = bmh_factory(network_config_name="test-node-network-config")
        extracted = backup_manager.extract_bmh_fields(sample_bmh_with_network_config)
        
        # BUSINESS RULE: Network configuration must be preserved for static IP nodes
        assert extracted["spec"]["preprovisioningNetworkDataName"] == "test-node-network-config"
        assert extracted["spec"]["userData"]["name"] == "master-user-data"
        assert extracted["spec"]["userData"]["namespace"] == "openshift-machine-api"

    def _extract_and_validate_machine_base(self, backup_manager, machine_data):
        """Helper: Extract machine fields with common structural validation
        
        This helper consolidates all Machine extraction tests following pytest best practices:
        - Reduces duplication while preserving test clarity
        - Each test maintains clear, focused business intent
        - Common validation logic is centralized
        """
        extracted = backup_manager.extract_machine_fields(machine_data)
        
        # Common structural validations for all machine extractions
        assert extracted["apiVersion"] == "machine.openshift.io/v1beta1"
        assert extracted["kind"] == "Machine"
        assert extracted["metadata"]["name"] == "PLACEHOLDER_NAME"
        assert "providerSpec" in extracted["spec"]
        assert extracted["spec"]["providerSpec"]["value"]["kind"] == "BareMetalMachineProviderSpec"
        
        return extracted
    
    def _validate_cluster_integration_labels(self, extracted, original_data):
        """Helper: Validate cluster integration labels are preserved"""
        # BUSINESS RULE: Cluster integration labels must be preserved for proper node association
        labels = extracted["metadata"]["labels"]
        original_labels = original_data["metadata"]["labels"]
        
        # Check for required cluster integration labels
        required_labels = [
            "machine.openshift.io/cluster-api-cluster",
            "machine.openshift.io/cluster-api-machine-role",
            "machine.openshift.io/cluster-api-machine-type"
        ]
        
        for label_key in required_labels:
            if label_key in original_labels:  # Only validate if it existed in original
                assert label_key in labels, f"Missing required label: {label_key}"
                assert labels[label_key] == original_labels[label_key], f"Label value mismatch for {label_key}"

    def test_machine_extraction_provider_spec_preservation(
        self, backup_manager, machine_factory
    ):
        """Test that Machine extraction preserves provider spec needed for bare metal deployment"""
        sample_machine_with_provider_spec = machine_factory(include_full_provider_spec=True, include_cluster_labels=False)
        extracted = self._extract_and_validate_machine_base(backup_manager, sample_machine_with_provider_spec)
        
        # BUSINESS RULE: Provider spec must be preserved for bare metal machine deployment
        provider_value = extracted["spec"]["providerSpec"]["value"]
        expected_provider = sample_machine_with_provider_spec["spec"]["providerSpec"]["value"]
        assert provider_value["apiVersion"] == expected_provider["apiVersion"]
        assert provider_value["customDeploy"]["method"] == expected_provider["customDeploy"]["method"]
        assert provider_value["image"]["url"] == expected_provider["image"]["url"]
        
        # BUSINESS RULE: Lifecycle hooks must be preserved for deployment coordination
        assert "lifecycleHooks" in extracted["spec"]

    def test_machine_extraction_master_node_configuration(
        self, backup_manager, machine_factory
    ):
        """Test that Machine extraction properly handles master node specific configuration"""
        sample_master_machine_data = machine_factory(machine_name="master-machine", user_data_name="master-user-data-managed")
        extracted = self._extract_and_validate_machine_base(backup_manager, sample_master_machine_data)
        self._validate_cluster_integration_labels(extracted, sample_master_machine_data)
        
        # BUSINESS RULE: Master user data must be preserved for bootstrap configuration
        assert extracted["spec"]["providerSpec"]["value"]["userData"]["name"] == sample_master_machine_data["spec"]["providerSpec"]["value"]["userData"]["name"]

    def test_machine_extraction_comprehensive_validation(self, backup_manager, sample_machine_data, resource_validator, machine_validator):
        """Test Machine extraction preserves complete structure and produces cluster-compatible configuration"""
        extracted = self._extract_and_validate_machine_base(backup_manager, sample_machine_data)
        
        # BUSINESS RULE: Complete structure validation (using centralized validator)
        resource_validator(extracted, "machine.openshift.io/v1beta1", "Machine", "PLACEHOLDER_NAME")

        # BUSINESS RULE: Machine-specific validations (using centralized validator)
        machine_validator.validate_essentials(extracted, sample_machine_data)

        # BUSINESS RULE: Spec configuration must be preserved
        assert extracted["spec"]["lifecycleHooks"] == {}
        provider_value = extracted["spec"]["providerSpec"]["value"]
        assert provider_value["apiVersion"] == "machine.openshift.io/v1beta1"

        # BUSINESS RULE: Provider spec must indicate BareMetalMachineProviderSpec (handled by machine_validator)
        assert "machine.openshift.io" in provider_value["apiVersion"]

    def test_metadata_sanitization_for_restoration_accuracy(
        self, backup_manager, sample_secret_with_runtime_metadata: dict
    ):
        """Test that metadata sanitization preserves exactly what's needed for restoration"""        
        sanitized = backup_manager.sanitize_metadata(sample_secret_with_runtime_metadata)
        
        # BUSINESS RULE: Essential metadata for restoration must be preserved
        metadata = sanitized["metadata"]
        assert metadata["name"] == "essential-secret"
        assert metadata["namespace"] == "openshift-machine-api"
        assert metadata["labels"]["app"] == "openshift-control-plane"
        
        # BUSINESS RULE: Runtime metadata must be removed to prevent restoration conflicts  
        runtime_fields = ["creationTimestamp", "resourceVersion", "uid", "generation", "managedFields", "ownerReferences", "finalizers", "annotations"]
        for field in runtime_fields:
            assert field not in metadata, f"Runtime field '{field}' was not removed"
            
        # BUSINESS RULE: Data must be preserved exactly
        assert sanitized["data"]["key"] == "value"

    def test_transformation_preserves_cross_resource_references(
        self, backup_manager, sample_control_plane_resources: dict
    ):
        """Test that transformations preserve references between BMH, Machine, and Secrets"""        
        resources = sample_control_plane_resources
        extracted_bmh = backup_manager.extract_bmh_fields(resources["bmh"])
        extracted_machine = backup_manager.extract_machine_fields(resources["machine"])
        
        # BUSINESS RULE: Cross-resource references must be preserved for proper linking
        assert extracted_bmh["spec"]["bmc"]["credentialsName"] == "control-node-bmc-secret"
        assert extracted_bmh["spec"]["preprovisioningNetworkDataName"] == "control-node-network-config-secret"
        
        # BUSINESS RULE: User data references must match between BMH and Machine
        bmh_userdata = extracted_bmh["spec"]["userData"]["name"]
        machine_userdata = extracted_machine["spec"]["providerSpec"]["value"]["userData"]["name"]
        assert bmh_userdata == machine_userdata == "master-user-data"

    def test_extraction_handles_edge_case_data_structures(self, backup_manager):
        """Test that extraction handles edge cases like missing nested fields gracefully"""
        # BMH with minimal data structure
        minimal_bmh = {
            "apiVersion": "metal3.io/v1alpha1",
            "kind": "BareMetalHost",
            "metadata": {"name": "minimal-node"},
            "spec": {
                "bmc": {"address": "redfish://192.168.1.1"},
                "bootMACAddress": "aa:bb:cc:dd:ee:ff"
                # Missing many optional fields
            }
        }
        
        extracted = backup_manager.extract_bmh_fields(minimal_bmh)
        
        # BUSINESS RULE: Extraction must handle missing fields gracefully
        assert extracted["apiVersion"] == "metal3.io/v1alpha1"
        assert extracted["spec"]["bmc"]["address"] == "redfish://192.168.1.1"
        assert extracted["spec"]["bootMACAddress"] == "aa:bb:cc:dd:ee:ff"
        
        # BUSINESS RULE: Missing fields should be None or empty, not cause failures
        assert "rootDeviceHints" in extracted["spec"]  # Should exist even if original was missing
        assert "userData" in extracted["spec"]


# =============================================================================
# Test Network Configuration Preservation
# =============================================================================


class TestNetworkConfigurationPreservation:
    """Test network configuration preservation for static IP and complex network setups"""

    def test_network_config_backup_preserves_configuration_data(
        self, backup_manager, network_config_scenarios: dict
    ):
        """Test that network configuration backup preserves essential data across different scenarios
        
        This test now uses pytest's native fixture parametrization following Context7
        recommendations instead of @pytest.mark.parametrize with complex inline data.
        
        Args:
            backup_manager: BackupManager instance for testing.
            network_config_scenarios: Parametrized fixture providing network config test scenarios.
        """        
        scenario = network_config_scenarios
        
        # Mock the network configuration secret retrieval
        backup_manager.execute_oc_command.return_value = scenario["config_data"]
        
        # Execute backup operation
        result_path = backup_manager.backup_secret(
            scenario["node_name"], 
            scenario["secret_name"], 
            "_network-config.yaml", 
            scenario["description"]
        )
        
        # Load and validate saved configuration
        with open(result_path, 'r') as f:
            saved_config = yaml.safe_load(f)
        
        # BUSINESS RULE: Network configuration data must be preserved exactly
        config_data = scenario["config_data"]
        assert saved_config["data"]["nmstate"] == config_data["data"]["nmstate"]
        assert saved_config["metadata"]["name"] == config_data["metadata"]["name"]
        assert saved_config["type"] == config_data["type"]
        
        # BUSINESS RULE: Runtime metadata should be sanitized while preserving essentials
        metadata = saved_config["metadata"]
        assert "resourceVersion" not in metadata  # Should be sanitized
        assert "name" in metadata and "namespace" in metadata  # Should be preserved

    def test_bmh_network_data_name_linking(self, backup_manager, bmh_factory):
        """Test that BMH properly links to network configuration secret"""
        sample_bmh_network_data_linking = bmh_factory(
            node_name="network-node",
            network_config_name="network-node-network-config-secret",
            include_user_data=False
        )
        extracted = backup_manager.extract_bmh_fields(sample_bmh_network_data_linking)
        
        # BUSINESS RULE: Network data reference must be preserved for proper network configuration
        assert extracted["spec"]["preprovisioningNetworkDataName"] == sample_bmh_network_data_linking["spec"]["preprovisioningNetworkDataName"]
        
        # BUSINESS RULE: Boot MAC address must be preserved for network interface identification 
        assert extracted["spec"]["bootMACAddress"] == sample_bmh_network_data_linking["spec"]["bootMACAddress"]


# =============================================================================
# Test Cross-Resource Dependency Validation
# =============================================================================


class TestCrossResourceDependencyValidation:
    """Test validation of dependencies between BMH, Machine, and Secret resources"""

    def test_bmh_secret_dependency_chain_validation(self, backup_manager, resource_validator):
        """Test that BMH properly references secrets that exist in the backup"""
        # BMH that references multiple secrets
        bmh_with_secrets = {
            "apiVersion": "metal3.io/v1alpha1",
            "kind": "BareMetalHost",
            "metadata": {"name": "control-node", "namespace": "openshift-machine-api"},
            "spec": {
                "bmc": {"credentialsName": "control-node-bmc-secret"},
                "preprovisioningNetworkDataName": "control-node-network-secret",
                "userData": {"name": "master-user-data", "namespace": "openshift-machine-api"}
            }
        }
        
        extracted_bmh = backup_manager.extract_bmh_fields(bmh_with_secrets)
        
        # BUSINESS RULE: Complete structure validation (using centralized validator)
        resource_validator(extracted_bmh, "metal3.io/v1alpha1", "BareMetalHost", "control-node")
        
        # BUSINESS RULE: BMH must maintain valid references to secrets for restoration
        assert extracted_bmh["spec"]["bmc"]["credentialsName"] == "control-node-bmc-secret"
        assert extracted_bmh["spec"]["preprovisioningNetworkDataName"] == "control-node-network-secret"
        assert extracted_bmh["spec"]["userData"]["name"] == "master-user-data"
        
        # BUSINESS RULE: All secret references must be consistently named
        bmc_secret_name = extracted_bmh["spec"]["bmc"]["credentialsName"]
        network_secret_name = extracted_bmh["spec"]["preprovisioningNetworkDataName"]
        assert "control-node" in bmc_secret_name
        assert "control-node" in network_secret_name
        assert bmc_secret_name != network_secret_name  # Must be different secrets

    def test_machine_bmh_linking_validation(self, backup_manager):
        """Test that Machine and BMH configurations are compatible for linking"""
        # Machine configuration
        machine_config = {
            "apiVersion": "machine.openshift.io/v1beta1",
            "kind": "Machine",
            "metadata": {
                "name": "control-machine",
                "namespace": "openshift-machine-api",
                "labels": {"machine.openshift.io/cluster-api-machine-role": "master"}
            },
            "spec": {
                "providerSpec": {
                    "value": {
                        "kind": "BareMetalMachineProviderSpec",
                        "hostSelector": {"matchLabels": {"role": "control-plane"}},
                        "userData": {"name": "master-user-data"}
                    }
                }
            }
        }
        
        # BMH configuration that would match
        bmh_config = {
            "apiVersion": "metal3.io/v1alpha1",
            "kind": "BareMetalHost",
            "metadata": {
                "name": "control-bmh", 
                "namespace": "openshift-machine-api",
                "labels": {"role": "control-plane"}  # Matches hostSelector
            },
            "spec": {
                "userData": {"name": "master-user-data"}  # Must match Machine
            }
        }
        
        extracted_machine = backup_manager.extract_machine_fields(machine_config)
        extracted_bmh = backup_manager.extract_bmh_fields(bmh_config)
        
        # BUSINESS RULE: Machine and BMH must have compatible configurations
        machine_userdata = extracted_machine["spec"]["providerSpec"]["value"]["userData"]["name"]
        bmh_userdata = extracted_bmh["spec"]["userData"]["name"]
        assert machine_userdata == bmh_userdata == "master-user-data"
        
        # BUSINESS RULE: Machine provider spec must be BareMetalMachineProviderSpec for BMH linking
        assert extracted_machine["spec"]["providerSpec"]["value"]["kind"] == "BareMetalMachineProviderSpec"


    def test_user_data_consistency_validation(self, backup_manager, linked_resource_factory):
        """Test that user data references are consistent between BMH and Machine
        
        Args:
            backup_manager: BackupManager instance for testing.
            linked_resource_factory: Factory for creating linked resources with custom parameters.
        """
        user_data_configs = [
            ("master-user-data-managed", "master"),
            ("worker-user-data", "worker")
        ]
        
        for user_data_name, role in user_data_configs:
            # Use factory to create linked resources with custom user data and role
            resources = linked_resource_factory(
                node_name=f"{role}-node",
                user_data_name=user_data_name,
                machine_role=role
            )
            
            extracted_bmh = backup_manager.extract_bmh_fields(resources["bmh"])
            extracted_machine = backup_manager.extract_machine_fields(resources["machine"])
            
            # BUSINESS RULE: User data must match between BMH and Machine for proper deployment
            bmh_userdata = extracted_bmh["spec"]["userData"]["name"]
            machine_userdata = extracted_machine["spec"]["providerSpec"]["value"]["userData"]["name"]
            assert bmh_userdata == machine_userdata == user_data_name

    def test_resource_naming_consistency_validation(self, backup_manager, linked_resource_factory):
        """Test that resource naming follows consistent patterns for dependency resolution
        
        Args:
            backup_manager: BackupManager instance for testing.
            linked_resource_factory: Factory for creating linked resources with consistent naming.
        """
        node_name = "control-node-1"
        
        # Use factory to create resources with consistent naming patterns
        resources = linked_resource_factory(node_name=node_name)
        
        # Generate expected naming patterns
        expected_bmc_secret = f"{node_name}-bmc-secret"
        expected_network_secret = f"{node_name}-network-config-secret"
        
        extracted = backup_manager.extract_bmh_fields(resources["bmh"])
        
        # BUSINESS RULE: Resource naming must follow consistent patterns for backup/restore
        actual_bmc_secret = extracted["spec"]["bmc"]["credentialsName"] 
        actual_network_secret = extracted["spec"]["preprovisioningNetworkDataName"]
        
        assert actual_bmc_secret == expected_bmc_secret
        assert actual_network_secret == expected_network_secret
        
        # BUSINESS RULE: All secret names should reference the same node
        assert node_name in actual_bmc_secret
        assert node_name in actual_network_secret


# =============================================================================
# Test Backup Operations
# =============================================================================


class TestRealBackupOperations:
    """Test backup operations with actual YAML file generation"""

    def test_backup_bmh_definition_creates_valid_yaml(self, backup_manager, sample_bmh_data, yaml_file_validator):
        """Test BMH definition backup creates valid YAML file with correct content"""
        bmh_name = "test-bmh"
        
        result_path = backup_manager.backup_bmh_definition(bmh_name, sample_bmh_data)
        
        # Verify file creation and YAML content using centralized validator
        expected_path = f"{backup_manager.backup_dir}/{bmh_name}_bmh.yaml"
        expected_fields = {
            "apiVersion": "metal3.io/v1alpha1",
            "kind": "BareMetalHost", 
            "metadata.name": "ocp-control2.two.ocp4.example.com",
            "spec.bootMACAddress": "52:54:00:e9:d5:8a"
        }
        yaml_file_validator.validate_backup(result_path, expected_path, expected_fields)

    def test_backup_machine_definition_creates_valid_yaml(self, backup_manager, sample_machine_data, yaml_file_validator):
        """Test Machine definition backup creates valid YAML file with correct content"""
        machine_name = "test-machine"
        
        result_path = backup_manager.backup_machine_definition(machine_name, sample_machine_data)
        
        # Verify file creation and YAML content using centralized validator
        expected_path = f"{backup_manager.backup_dir}/{machine_name}_machine.yaml"
        expected_fields = {
            "apiVersion": "machine.openshift.io/v1beta1",
            "kind": "Machine",
            "metadata.name": "PLACEHOLDER_NAME"
        }
        saved_data = yaml_file_validator.validate_backup(result_path, expected_path, expected_fields)
        
        # Verify complex Kubernetes label directly (contains dots, can't use nested path)
        assert saved_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "master"

    def test_backup_secret_creates_sanitized_yaml(self, backup_manager, sample_bmc_secret_data, yaml_file_validator):
        """Test secret backup creates properly sanitized YAML file"""
        node_name = "test-node"
        secret_suffix = "bmc-secret"
        backup_filename_suffix = "-bmc-secret.yaml"
        secret_description = "BMC secret"

        backup_manager.execute_oc_command.return_value = sample_bmc_secret_data
        
        result_path = backup_manager.backup_secret(
            node_name, secret_suffix, backup_filename_suffix, secret_description
        )

        # Verify file creation and sanitization using centralized validator
        yaml_file_validator.validate_sanitized(result_path, sample_bmc_secret_data)


    def test_backup_operations_use_correct_filenames(self, temp_backup_manager, sample_bmh_data, sample_machine_data, file_operation_validator):
        """Test that backup operations create files with expected naming conventions"""
        # Test BMH backup filename
        bmh_path = temp_backup_manager.backup_bmh_definition("control-node-1", sample_bmh_data)
        file_operation_validator.validate_creation(bmh_path, "control-node-1_bmh.yaml")

        # Test Machine backup filename  
        machine_path = temp_backup_manager.backup_machine_definition("machine-abc123", sample_machine_data)
        file_operation_validator.validate_creation(machine_path, "machine-abc123_machine.yaml")
    
    def test_backup_template_bmh_comprehensive_scenarios(
        self, backup_manager, sample_bmh_list, sample_bmh_data
    ):
        """Test template BMH backup for all scenarios with actual file generation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_manager.backup_dir = temp_dir
            
            # Test 1: Control plane expansion with available template
            backup_manager.execute_oc_command.return_value = sample_bmh_list
            template_file, is_worker = backup_manager.backup_template_bmh(
                failed_control_node=None, is_control_plane_expansion=True
            )
            
            assert template_file is not None
            assert template_file.endswith("_bmh.yaml")
            assert os.path.exists(template_file)
            assert is_worker is False
            
            # Verify the backup file contains valid YAML
            with open(template_file, "r") as f:
                template_data = yaml.safe_load(f)
            assert template_data["apiVersion"] == "metal3.io/v1alpha1"
            assert template_data["kind"] == "BareMetalHost"
            
            # Test 2: Failed control node backup
            failed_node = "ocp-control1.two.ocp4.example.com"
            backup_manager.execute_oc_command.return_value = sample_bmh_data
            
            template_file_2, is_worker_2 = backup_manager.backup_template_bmh(
                failed_control_node=failed_node
            )
            
            assert template_file_2 is not None
            assert failed_node in template_file_2
            assert os.path.exists(template_file_2)
            assert is_worker_2 is False
  
# =============================================================================
# Test Real File Copy Operations for Node Replacement
# =============================================================================


class TestRealFileCopyOperations:
    """Test file copy operations for node replacement with actual file operations"""

    def test_copy_files_for_replacement_successful_operation(self, temp_backup_manager, file_operation_validator):
        """Test file copy operation returns correct file mapping"""
        bad_node, bmh_name, bad_machine = "old-node", "old-bmh", "old-machine" 
        replacement_node = "new-node"
        
        # Create minimal source files - content doesn't matter for this test
        source_files = [
            f"{bad_node}_nmstate",
            f"{bad_node}-bmc-secret.yaml", 
            f"{bmh_name}_bmh.yaml",
            f"{bad_node}_network-config-secret.yaml",
            f"{bad_machine}_machine.yaml"
        ]
        
        for filename in source_files:
            (Path(temp_backup_manager.backup_dir) / filename).write_text("test-content")
            
        result = temp_backup_manager.copy_files_for_replacement(
            bad_node, bmh_name, bad_machine, replacement_node
        )
        
        # Verify file mapping structure using centralized validator
        expected_keys = {"nmstate", "bmc_secret", "bmh", "network_secret", "machine"}
        file_operation_validator.validate_mapping(result, expected_keys, temp_backup_manager.backup_dir)
    
    @pytest.mark.parametrize("file_type,source_suffix", [
        ("nmstate", "_nmstate"),
        ("bmc_secret", "-bmc-secret.yaml"),
        ("network_secret", "_network-config-secret.yaml"),
    ])
    def test_copy_files_preserves_content_for_file_types(
        self, temp_backup_manager, file_type, source_suffix, file_operation_validator
    ):
        """Test that file content is preserved during copy operations"""
        bad_node, replacement_node = "source-node", "target-node"
        bmh_name, machine_name = f"{bad_node}-bmh", f"{bad_node}-machine"
        test_content = f"test-content-for-{file_type}"
        
        # Create all required files first with dummy content
        all_required_files = [
            f"{bad_node}_nmstate",
            f"{bad_node}-bmc-secret.yaml",
            f"{bmh_name}_bmh.yaml",
            f"{bad_node}_network-config-secret.yaml",
            f"{machine_name}_machine.yaml"
        ]
        
        for filename in all_required_files:
            (Path(temp_backup_manager.backup_dir) / filename).write_text("dummy")
        
        # Now overwrite the specific file we want to test with our test content
        source_file = Path(temp_backup_manager.backup_dir) / f"{bad_node}{source_suffix}"
        source_file.write_text(test_content)
            
        result = temp_backup_manager.copy_files_for_replacement(
            bad_node, bmh_name, machine_name, replacement_node
        )
        
        # Verify specific file content was preserved using centralized validator
        target_path = result[file_type]
        file_operation_validator.validate_creation(target_path, expected_suffix="", expected_content=test_content)
    

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
