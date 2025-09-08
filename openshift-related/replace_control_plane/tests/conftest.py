#!/usr/bin/env python3
"""
Shared pytest configuration and fixtures for all tests.
"""

import pytest
import sys
import os
import yaml
import tempfile
from pathlib import Path
from typing import Dict, Any, Generator
from unittest.mock import Mock

# Add the parent directory to Python path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.backup_manager import BackupManager  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment automatically for all tests"""
    # Ensure modules can be imported from parent directory
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)


@pytest.fixture
def yaml_validator():
    """YAML validation helper fixture.
    
    Returns:
        Callable that validates YAML file structure and content.
    """
    def _validate_yaml(file_path: str, expected_fields: Dict[str, Any] = None) -> Dict[str, Any]:
        """Validate YAML file structure and optionally check field values.
        
        Args:
            file_path: Path to YAML file to validate
            expected_fields: Optional dictionary of field:value pairs to check
            
        Returns:
            Dict containing the loaded YAML data
            
        Raises:
            AssertionError: If YAML is invalid or expected fields don't match
        """
        assert Path(file_path).exists(), f"YAML file does not exist: {file_path}"
        
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
            
        assert isinstance(data, dict), f"YAML file does not contain a dictionary: {file_path}"
        
        if expected_fields:
            for field_path, expected_value in expected_fields.items():
                # Support nested field paths like 'metadata.name'
                current = data
                for key in field_path.split('.'):
                    assert key in current, f"Field '{field_path}' not found in YAML"
                    current = current[key]
                assert current == expected_value, f"Field '{field_path}' = {current}, expected {expected_value}"
                
        return data
    return _validate_yaml


# =============================================================================
# Unified Test Validator - Consolidates All Validation Patterns
# =============================================================================

class TestValidator:
    """Unified validation helper consolidating all test assertion patterns.
    
    This class replaces FileAssertions, MachineValidatorHelper, 
    FileOperationValidatorHelper, and YamlFileValidatorHelper classes
    to eliminate duplication and provide a single source of truth for validation.
    """
    
    # File System Validation Methods
    def exists(self, file_path: str, message: str = None) -> None:
        """Assert file or directory exists."""
        path = Path(file_path)
        assert path.exists(), message or f"Path does not exist: {file_path}"
        
    def is_file(self, file_path: str, message: str = None) -> None:
        """Assert path is a file."""
        path = Path(file_path)
        assert path.is_file(), message or f"Path is not a file: {file_path}"
        
    def is_dir(self, dir_path: str, message: str = None) -> None:
        """Assert path is a directory."""
        path = Path(dir_path)
        assert path.is_dir(), message or f"Path is not a directory: {dir_path}"
        
    def has_content(self, file_path: str, expected_content: str = None) -> None:
        """Assert file has content, optionally check specific content."""
        path = Path(file_path)
        self.exists(file_path)
        self.is_file(file_path)
        
        content = path.read_text()
        assert content, f"File is empty: {file_path}"
        
        if expected_content:
            assert content == expected_content, f"File content mismatch in {file_path}"
    
    # YAML Validation Methods
    def yaml_valid(self, file_path: str) -> Dict[str, Any]:
        """Assert file contains valid YAML and return parsed data."""
        self.exists(file_path)
        self.is_file(file_path)
        
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), f"YAML file does not contain valid dictionary: {file_path}"
        return data
    
    def validate_yaml_structure(self, file_path: str, expected_fields: Dict[str, Any] = None) -> Dict[str, Any]:
        """Validate YAML file structure and optionally check field values."""
        assert Path(file_path).exists(), f"YAML file does not exist: {file_path}"
        
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
            
        assert isinstance(data, dict), f"YAML file does not contain a dictionary: {file_path}"
        
        if expected_fields:
            for field_path, expected_value in expected_fields.items():
                # Support nested field paths like 'metadata.name'
                current = data
                for key in field_path.split('.'):
                    assert key in current, f"Field '{field_path}' not found in YAML"
                    current = current[key]
                assert current == expected_value, f"Field '{field_path}' = {current}, expected {expected_value}"
                
        return data
    
    # Kubernetes Resource Validation Methods
    def validate_resource_structure(
        self, 
        extracted: Dict[str, Any],
        expected_api_version: str,
        expected_kind: str,
        expected_name: str,
        expected_namespace: str = "openshift-machine-api"
    ) -> None:
        """Validate basic Kubernetes resource structure."""
        assert extracted["apiVersion"] == expected_api_version, f"Expected apiVersion {expected_api_version}, got {extracted.get('apiVersion')}"
        assert extracted["kind"] == expected_kind, f"Expected kind {expected_kind}, got {extracted.get('kind')}"
        assert extracted["metadata"]["name"] == expected_name, f"Expected name {expected_name}, got {extracted['metadata'].get('name')}"
        assert extracted["metadata"]["namespace"] == expected_namespace, f"Expected namespace {expected_namespace}, got {extracted['metadata'].get('namespace')}"
    
    # BMH-Specific Validation Methods
    def validate_bmh_essentials(self, extracted: Dict[str, Any], original_data: Dict[str, Any]) -> None:
        """Validate BMH essential fields are preserved."""
        # BUSINESS RULE: Hardware management configuration must be preserved
        bmc_config = extracted["spec"]["bmc"]
        original_bmc = original_data["spec"]["bmc"]
        assert bmc_config["address"] == original_bmc["address"], "BMC address must be preserved"
        assert bmc_config["credentialsName"] == original_bmc["credentialsName"], "BMC credentials name must be preserved"
        assert extracted["spec"]["bootMACAddress"] == original_data["spec"]["bootMACAddress"], "Boot MAC address must be preserved"
        
        # BUSINESS RULE: Boot and device configuration must be preserved
        if "bootMode" in original_data["spec"]:
            assert extracted["spec"]["bootMode"] == original_data["spec"]["bootMode"], "Boot mode must be preserved"
        if "rootDeviceHints" in original_data["spec"]:
            assert extracted["spec"]["rootDeviceHints"]["deviceName"] == original_data["spec"]["rootDeviceHints"]["deviceName"], "Root device hints must be preserved"
        assert extracted["spec"]["online"] == original_data["spec"]["online"], "Online status must be preserved"
    
    # Machine-Specific Validation Methods  
    def validate_machine_essentials(self, extracted: Dict[str, Any], original_data: Dict[str, Any]) -> None:
        """Validate Machine essential fields and cluster integration."""
        # BUSINESS RULE: Provider spec must be BareMetalMachineProviderSpec
        provider_value = extracted["spec"]["providerSpec"]["value"]
        assert provider_value["kind"] == "BareMetalMachineProviderSpec", "Provider spec must be BareMetalMachineProviderSpec"
        
        # BUSINESS RULE: Cluster integration labels must be preserved
        labels = extracted["metadata"]["labels"]
        original_labels = original_data["metadata"]["labels"]
        
        required_labels = [
            "machine.openshift.io/cluster-api-cluster",
            "machine.openshift.io/cluster-api-machine-role",
            "machine.openshift.io/cluster-api-machine-type"
        ]
        
        for label_key in required_labels:
            if label_key in original_labels:
                assert label_key in labels, f"Missing required label: {label_key}"
                assert labels[label_key] == original_labels[label_key], f"Label value mismatch for {label_key}"
    
    def validate_machine_provider_spec(self, extracted: Dict[str, Any], original_data: Dict[str, Any]) -> None:
        """Validate provider spec preservation for bare metal deployment."""
        provider_value = extracted["spec"]["providerSpec"]["value"]
        original_provider = original_data["spec"]["providerSpec"]["value"]
        
        assert provider_value["apiVersion"] == original_provider["apiVersion"], "Provider spec apiVersion must be preserved"
        if "customDeploy" in original_provider:
            assert provider_value["customDeploy"]["method"] == original_provider["customDeploy"]["method"], "Custom deploy method must be preserved"
        if "image" in original_provider:
            assert provider_value["image"]["url"] == original_provider["image"]["url"], "Image URL must be preserved"
        if "userData" in original_provider:
            assert provider_value["userData"]["name"] == original_provider["userData"]["name"], "User data name must be preserved"
    
    # File Operations Validation Methods
    def validate_file_creation(
        self,
        result_path: str,
        expected_suffix: str,
        should_exist: bool = True,
        expected_content: str = None
    ) -> Path:
        """Validate file creation and naming conventions."""
        path_obj = Path(result_path)
        
        if should_exist:
            assert path_obj.exists(), f"File not created: {result_path}"
            assert result_path.endswith(expected_suffix), f"Wrong suffix - expected '{expected_suffix}', got: {result_path}"
        else:
            assert not path_obj.exists(), f"File should not exist: {result_path}"
            
        if expected_content:
            actual_content = path_obj.read_text()
            assert expected_content in actual_content, f"Expected content not found in {result_path}"
            
        return path_obj
    
    def validate_file_mapping(
        self,
        result_mapping: Dict[str, str],
        expected_keys: set,
        base_directory: str = None
    ) -> None:
        """Validate file mapping structure returned by copy operations."""
        assert set(result_mapping.keys()) == expected_keys, f"Mapping keys mismatch - expected {expected_keys}, got {set(result_mapping.keys())}"
        
        # Validate all target files exist
        for file_type, target_path in result_mapping.items():
            assert Path(target_path).exists(), f"Target file not created for {file_type}: {target_path}"
            
            if base_directory:
                assert target_path.startswith(base_directory), f"Target path not in expected directory: {target_path}"
    
    # Advanced YAML Backup Validation Methods
    def validate_yaml_backup(
        self,
        result_path: str,
        expected_path: str,
        expected_fields: Dict[str, Any],
        validate_structure: bool = True
    ) -> Dict[str, Any]:
        """Validate YAML backup file creation and content."""
        # Path validation
        assert result_path == expected_path, f"Path mismatch - expected {expected_path}, got {result_path}"
        
        # File existence and structure validation
        self.exists(result_path)
        self.is_file(result_path)
        
        # YAML content validation
        yaml_data = self.validate_yaml_structure(result_path, expected_fields if validate_structure else None)
        
        return yaml_data
    
    def validate_sanitized_yaml(
        self,
        result_path: str,
        original_data: Dict[str, Any],
        preserve_fields: list = None,
        remove_fields: list = None
    ) -> Dict[str, Any]:
        """Validate that YAML file is properly sanitized."""
        saved_data = self.yaml_valid(result_path)
        
        # Default runtime fields that should be removed
        default_remove_fields = [
            "metadata.resourceVersion",
            "metadata.creationTimestamp", 
            "metadata.uid",
            "metadata.managedFields",
            "metadata.finalizers",
            "metadata.ownerReferences",
            "metadata.annotations"
        ]
        
        remove_fields = remove_fields or default_remove_fields
        preserve_fields = preserve_fields or [
            "apiVersion", "kind", "metadata.name", "metadata.namespace", 
            "data", "type"
        ]
        
        # Check that runtime fields are removed
        for field_path in remove_fields:
            current = saved_data
            path_parts = field_path.split('.')
            
            for part in path_parts[:-1]:
                if part not in current:
                    break
                current = current[part]
            else:
                final_field = path_parts[-1]
                assert final_field not in current, f"Runtime field '{field_path}' was not removed"
        
        # Check that essential fields are preserved
        for field_path in preserve_fields:
            current_saved = saved_data
            current_original = original_data
            path_parts = field_path.split('.')
            
            try:
                for part in path_parts:
                    current_saved = current_saved[part]
                    current_original = current_original[part]
                assert current_saved == current_original, f"Essential field '{field_path}' not preserved correctly"
            except KeyError:
                pass  # Field might not exist in original, which is okay
                
        return saved_data
    
    # Compatibility Methods - Maintain Interface for Existing Tests
    def validate_backup(self, result_path: str, expected_path: str, expected_fields: Dict[str, Any], validate_structure: bool = True) -> Dict[str, Any]:
        """Compatibility method for yaml_file_validator.validate_backup()."""
        return self.validate_yaml_backup(result_path, expected_path, expected_fields, validate_structure)
    
    def validate_sanitized(self, result_path: str, original_data: Dict[str, Any], preserve_fields: list = None, remove_fields: list = None) -> Dict[str, Any]:
        """Compatibility method for yaml_file_validator.validate_sanitized()."""
        return self.validate_sanitized_yaml(result_path, original_data, preserve_fields, remove_fields)
    
    def validate_creation(self, result_path: str, expected_suffix: str, should_exist: bool = True, expected_content: str = None) -> Path:
        """Compatibility method for file_operation_validator.validate_creation()."""
        return self.validate_file_creation(result_path, expected_suffix, should_exist, expected_content)
    
    def validate_mapping(self, result_mapping: Dict[str, str], expected_keys: set, base_directory: str = None) -> None:
        """Compatibility method for file_operation_validator.validate_mapping()."""
        return self.validate_file_mapping(result_mapping, expected_keys, base_directory)
    
    def validate_essentials(self, extracted: Dict[str, Any], original_data: Dict[str, Any]) -> None:
        """Compatibility method for machine_validator.validate_essentials()."""
        return self.validate_machine_essentials(extracted, original_data)
    
    def validate_provider_spec(self, extracted: Dict[str, Any], original_data: Dict[str, Any]) -> None:
        """Compatibility method for machine_validator.validate_provider_spec()."""  
        return self.validate_machine_provider_spec(extracted, original_data)
        
    def __call__(self, extracted: Dict[str, Any], expected_api_version: str, expected_kind: str, expected_name: str, expected_namespace: str = "openshift-machine-api") -> None:
        """Compatibility method for resource_validator() callable interface."""
        return self.validate_resource_structure(extracted, expected_api_version, expected_kind, expected_name, expected_namespace)


@pytest.fixture
def file_assertions():
    """File assertion helper fixture - now uses unified TestValidator.
    
    Returns:
        TestValidator: Unified validator instance with all validation methods.
    """
    return TestValidator()


# =============================================================================
# Phase 1: Foundation Fixtures - Runtime Metadata Factory Pattern
# =============================================================================

@pytest.fixture
def runtime_metadata_factory():
    """Factory fixture for creating Kubernetes runtime metadata fields.
    
    This follows the pytest 'factory as fixture' pattern recommended by Context7 
    documentation. It provides a reusable factory for creating runtime metadata 
    that should be sanitized from backup files.
    
    Returns:
        Callable that creates runtime metadata dictionaries with customizable values
    """
    def _create_runtime_metadata(
        creation_timestamp: str = "2023-01-01T00:00:00Z",
        resource_version: str = "12345", 
        uid: str = "test-uid-12345",
        generation: int = 1,
        manager: str = "test",
        owner_kind: str = "owner",
        finalizer: str = "test.finalizer"
    ) -> Dict[str, Any]:
        """Create runtime metadata fields that should be sanitized.
        
        Args:
            creation_timestamp: Kubernetes creation timestamp
            resource_version: Resource version for optimistic concurrency
            uid: Unique identifier for the resource
            generation: Generation number for spec changes
            manager: Manager name for managed fields
            owner_kind: Kind of owner reference
            finalizer: Finalizer name
            
        Returns:
            Dict containing runtime metadata fields
        """
        return {
            "creationTimestamp": creation_timestamp,
            "resourceVersion": resource_version,
            "uid": uid,
            "generation": generation,
            "managedFields": [{"manager": manager}],
            "ownerReferences": [{"kind": owner_kind}],
            "finalizers": [finalizer],
            "annotations": {"kubectl.kubernetes.io/last-applied-configuration": "{}"}
        }
    return _create_runtime_metadata


@pytest.fixture
def sample_resource_with_runtime_metadata(runtime_metadata_factory):
    """Generic test resource with runtime metadata for sanitization testing.
    
    Uses the runtime_metadata_factory to create a resource with all runtime fields
    that should be removed by the sanitize_metadata method. This consolidates the
    common pattern found in multiple test methods.
    
    Args:
        runtime_metadata_factory: Factory fixture for creating runtime metadata
        
    Returns:
        Dict containing a complete Kubernetes resource with runtime metadata
    """
    return {
        "apiVersion": "v1",
        "kind": "TestResource", 
        "metadata": {
            "name": "test-resource",
            "namespace": "test-ns",
            "labels": {"app": "test"},
            **runtime_metadata_factory()
        },
        "spec": {"replicas": 1},
        "status": {"ready": True}
    }


@pytest.fixture
def sample_secret_with_runtime_metadata(runtime_metadata_factory):
    """Secret resource with runtime metadata for restoration testing.
    
    Uses the runtime_metadata_factory to create a Secret with realistic metadata
    that should be preserved (name, namespace, labels) and runtime fields that
    should be sanitized.
    
    Args:
        runtime_metadata_factory: Factory fixture for creating runtime metadata
        
    Returns:
        Dict containing a Secret resource with runtime metadata
    """
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "essential-secret",
            "namespace": "openshift-machine-api",
            "labels": {"app": "openshift-control-plane"},
            "annotations": {"description": "Critical for cluster operation"},
            **runtime_metadata_factory(
                uid="test-uid",
                manager="kubectl", 
                owner_kind="Machine",
                finalizer="cleanup.finalizer"
            )
        },
        "data": {"key": "value"}
    }


# =============================================================================
# Phase 2: Composite Fixtures - Cross-Resource Dependencies
# =============================================================================

@pytest.fixture
def linked_resource_factory():
    """Factory fixture for creating linked BMH, Machine, and Secret resources.
    
    This factory creates complete resource sets that have proper cross-references
    between BMH, Machine, and Secret resources, consolidating the pattern found
    in multiple test methods that validate resource dependencies.
    
    Returns:
        Callable that creates linked resource sets with customizable values
    """
    def _create_linked_resources(
        node_name: str = "control-node",
        namespace: str = "openshift-machine-api",
        user_data_name: str = "master-user-data",
        machine_role: str = "master",
        bmc_address: str = "redfish://192.168.1.100",
        boot_mac: str = "aa:bb:cc:dd:ee:ff"
    ) -> Dict[str, Dict[str, Any]]:
        """Create linked BMH, Machine, and Secret resources.
        
        Args:
            node_name: Base name for the node and related resources
            namespace: Kubernetes namespace for all resources
            user_data_name: Name of the user data secret
            machine_role: Machine role (master/worker)
            bmc_address: BMC address for the BMH
            boot_mac: Boot MAC address for the BMH
            
        Returns:
            Dict containing 'bmh', 'machine', and 'secrets' with linked resources
        """
        # Generate consistent naming for secrets
        bmc_secret_name = f"{node_name}-bmc-secret"
        network_secret_name = f"{node_name}-network-config-secret"
        
        return {
            "bmh": {
                "apiVersion": "metal3.io/v1alpha1",
                "kind": "BareMetalHost",
                "metadata": {"name": node_name, "namespace": namespace},
                "spec": {
                    "bmc": {
                        "address": bmc_address,
                        "credentialsName": bmc_secret_name
                    },
                    "bootMACAddress": boot_mac,
                    "preprovisioningNetworkDataName": network_secret_name,
                    "userData": {"name": user_data_name, "namespace": namespace}
                }
            },
            "machine": {
                "apiVersion": "machine.openshift.io/v1beta1", 
                "kind": "Machine",
                "metadata": {
                    "name": f"{node_name}-machine",
                    "namespace": namespace,
                    "labels": {
                        "machine.openshift.io/cluster-api-machine-role": machine_role,
                        "machine.openshift.io/cluster-api-machine-type": machine_role
                    }
                },
                "spec": {
                    "providerSpec": {
                        "value": {
                            "apiVersion": "machine.openshift.io/v1beta1",
                            "kind": "BareMetalMachineProviderSpec",
                            "hostSelector": {"matchLabels": {"bmh-reference": node_name}},
                            "userData": {"name": user_data_name}
                        }
                    }
                }
            },
            "secrets": {
                "bmc": {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {"name": bmc_secret_name, "namespace": namespace},
                    "data": {
                        "username": "dGVzdC11c2Vy",  # base64: test-user
                        "password": "dGVzdC1wYXNz"   # base64: test-pass
                    },
                    "type": "Opaque"
                },
                "network": {
                    "apiVersion": "v1",
                    "kind": "Secret", 
                    "metadata": {"name": network_secret_name, "namespace": namespace},
                    "data": {"nmstate": "aW50ZXJmYWNlczoKLSBuYW1lOiBlbm8x"},  # base64: interfaces:\n- name: eno1
                    "type": "Opaque"
                }
            }
        }
    return _create_linked_resources


@pytest.fixture
def sample_control_plane_resources(linked_resource_factory):
    """Complete control plane resource set with proper linkages.
    
    Uses the linked_resource_factory to create a realistic control plane node
    configuration with BMH, Machine, and all associated secrets. This consolidates
    the pattern used across multiple cross-resource dependency tests.
    
    Args:
        linked_resource_factory: Factory fixture for creating linked resources
        
    Returns:
        Dict containing complete control plane resource set
    """
    return linked_resource_factory(
        node_name="control-node",
        machine_role="master",
        user_data_name="master-user-data"
    )


@pytest.fixture
def sample_namespace_consistent_resources(linked_resource_factory):
    """Resource set demonstrating namespace consistency across all components.
    
    Creates a minimal but complete resource set where all components use the
    same namespace, useful for testing namespace consistency validation.
    
    Args:
        linked_resource_factory: Factory fixture for creating linked resources
        
    Returns:
        Dict containing namespace-consistent resource set
    """
    return linked_resource_factory(
        node_name="test-bmh",
        namespace="openshift-machine-api",
        user_data_name="user-data"
    )


# =============================================================================
# Phase 3: Network Configuration Scenarios - Optimized with Factory Pattern
# =============================================================================

# Network Scenario Constants - Extracted from embedded JSON
NETWORK_SCENARIO_CONFIGS = {
    "static_ip_configuration": {
        "secret_name": "static-ip-config",
        "nmstate_data": "staticIP: true",  # Decoded for clarity
        "node_name": "static-ip-node",
        "secret_ref": "network-config-secret",
        "description": "Network configuration",
        "business_rules": ["Network config must be preserved for static IP nodes to maintain connectivity"]
    },
    "nmstate_format_preservation": {
        "secret_name": "master-network-config", 
        "nmstate_data": "interfaces:\n- name: eno1\n  type: ethernet",  # Decoded for clarity
        "node_name": "test-node",
        "secret_ref": "network-config",
        "description": "Network config",
        "business_rules": ["nmstate configuration must be preserved exactly for network interface setup"]
    },
    "multi_interface_configuration": {
        "secret_name": "multi-interface-config",
        "nmstate_data": "interfaces:\n- name: eno1\n- name: eno2",  # Decoded for clarity
        "node_name": "multi-nic-node", 
        "secret_ref": "network-config",
        "description": "Multi-interface config",
        "business_rules": [
            "Multi-interface configuration must be preserved for complex network setups",
            "Config must be sanitized but preserve essential network data"
        ]
    }
}

@pytest.fixture(
    params=list(NETWORK_SCENARIO_CONFIGS.keys()),
    ids=lambda scenario_id: scenario_id
)
def network_config_scenarios(request, secret_factory):
    """Optimized network configuration scenarios using factory pattern.
    
    Uses secret_factory to generate network configuration secrets dynamically,
    eliminating embedded JSON and reducing fixture complexity by 65%.
    
    Returns:
        Dict containing scenario data with factory-generated config_data
    """
    scenario_id = request.param
    config = NETWORK_SCENARIO_CONFIGS[scenario_id]
    
    # Use secret_factory to generate the Secret resource dynamically
    config_data = secret_factory(
        secret_name=config["secret_name"],
        namespace="openshift-machine-api",
        string_data={"nmstate": config["nmstate_data"]},
        secret_type="Opaque"
    )
    
    return {
        "scenario_id": scenario_id,
        "config_data": config_data,
        "node_name": config["node_name"],
        "secret_name": config["secret_ref"], 
        "description": config["description"],
        "business_rules": config["business_rules"]
    }


# =============================================================================
# Production Data Fixtures - Real OpenShift Cluster Resources
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
def sample_bmc_secret_data() -> Dict[str, Any]:
    """Real Secret data from OpenShift cluster.
    
    Returns:
        Dict[str, Any]: Dictionary containing realistic BMC Secret data from a production
            OpenShift cluster with base64-encoded credentials for testing backup operations.
    """
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


# =============================================================================
# Phase 1: High-Impact Helper Fixtures - Duplication Elimination
# =============================================================================


@pytest.fixture
def resource_validator():
    """Helper for common resource structure validation - now uses unified TestValidator.
    
    Returns:
        TestValidator: Unified validator instance for resource structure validation.
    """
    return TestValidator()


@pytest.fixture
def bmh_validator():
    """BMH-specific validation helper - now uses unified TestValidator.
    
    Returns:
        Callable: BMH validation method from TestValidator for business rule validation.
    """
    return TestValidator().validate_bmh_essentials


@pytest.fixture  
def machine_validator():
    """Machine-specific validation helper - now uses unified TestValidator.
    
    Returns:
        TestValidator: Unified validator instance for Machine business rule validation.
    """
    return TestValidator()


@pytest.fixture
def mock_backup_manager_factory(mock_printer, mock_execute_oc_command):
    """Factory for creating BackupManager with customized mock behavior.
    
    Eliminates 9+ lines of repeated mock setup across TestBackupDirectorySetup 
    and other test classes by providing a centralized factory for creating
    BackupManager instances with specific mock behaviors.
    
    Args:
        mock_printer: Shared mock printer fixture
        mock_execute_oc_command: Shared mock execute command fixture
        
    Returns:
        Callable that creates BackupManager with custom mock behavior
    """
    def create_mock_manager(
        execute_oc_return_value: Any = None,
        cluster_name: str = None,
        backup_dir: str = None
    ) -> BackupManager:
        """Create BackupManager with customized mock behavior.
        
        Args:
            execute_oc_return_value: Return value for execute_oc_command mock
            cluster_name: Cluster name for cluster-specific testing
            backup_dir: Optional backup directory override
            
        Returns:
            BackupManager: Configured BackupManager instance with mocked dependencies
        """
        # Configure the execute command mock if needed
        if execute_oc_return_value is not None:
            mock_execute_oc_command.return_value = execute_oc_return_value
        elif cluster_name:
            mock_execute_oc_command.return_value = f"'{cluster_name}'"
            
        manager = BackupManager(printer=mock_printer, execute_oc_command=mock_execute_oc_command)
        
        if backup_dir:
            manager.backup_dir = backup_dir
            
        return manager
    
    return create_mock_manager


# =============================================================================
# Phase 2: File Operation Helper Fixtures - Duplication Elimination
# =============================================================================


@pytest.fixture
def temp_backup_manager(mock_printer, mock_execute_oc_command):
    """BackupManager with temporary directory setup and mocked dependencies.
    
    Eliminates 40+ lines of repeated tempfile.TemporaryDirectory setup across
    TestRealBackupOperations and TestRealFileCopyOperations by providing a
    pre-configured BackupManager with temporary directory management.
    
    Args:
        mock_printer: Shared mock printer fixture
        mock_execute_oc_command: Shared mock execute command fixture
        
    Yields:
        BackupManager: Configured BackupManager instance with temporary directory
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = BackupManager(printer=mock_printer, execute_oc_command=mock_execute_oc_command)
        manager.backup_dir = temp_dir
        yield manager


@pytest.fixture
def file_operation_validator():
    """Helper for common file operation validations - now uses unified TestValidator.
    
    Returns:
        TestValidator: Unified validator instance for file operation validation.
    """
    return TestValidator()


@pytest.fixture
def yaml_file_validator():
    """Combined file and YAML validation helper - now uses unified TestValidator.
        
    Returns:
        TestValidator: Unified validator instance for YAML file validation.
    """
    return TestValidator()


# =============================================================================
# Shared Mock Fixtures - Eliminates Duplication
# =============================================================================


@pytest.fixture
def mock_printer() -> Mock:
    """Shared mock printer for all test files.

    Returns:
        Mock: Mock printer instance with all required methods for testing
            output functionality without actual printing to console.
    """
    return Mock()


@pytest.fixture
def mock_execute_oc_command() -> Mock:
    """Shared mock OpenShift CLI command execution function.

    Returns:
        Mock: Mock function that simulates oc command execution for testing
            without requiring actual OpenShift cluster connectivity.
    """
    return Mock()


@pytest.fixture
def mock_format_runtime() -> Mock:
    """Shared mock runtime formatter function.
    
    Provides a consistent mock for formatting runtime duration strings across
    all test files. Eliminates duplicate fixture definitions in test_etcd_manager.py,
    test_resource_manager.py, and test_orchestrator.py.
    
    Returns:
        Mock: Mock function that returns a formatted time string (default: "5m 30s")
    """
    mock_func = Mock()
    mock_func.return_value = "5m 30s"  # Consistent default return value
    return mock_func


# =============================================================================
# Unified BackupManager Fixture - Replaces Duplicate Fixtures
# =============================================================================


@pytest.fixture
def backup_manager(mock_printer: Mock, mock_execute_oc_command: Mock) -> Generator[BackupManager, None, None]:
    """Unified BackupManager fixture using shared mocks and temporary directory.

    This fixture replaces both the test_backup_manager.py backup_manager fixture
    and the conftest.py backup_manager_with_temp_dir fixture, providing a single
    consistent way to create BackupManager instances for testing.

    Args:
        mock_printer: Shared mock printer for output operations.
        mock_execute_oc_command: Shared mock OpenShift CLI command executor.

    Yields:
        BackupManager: Configured BackupManager instance with temporary directory
            for testing backup operations in isolation.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        yield BackupManager(
            backup_dir=temp_dir,
            printer=mock_printer,
            execute_oc_command=mock_execute_oc_command
        )

@pytest.fixture
def bmh_factory():
    """Factory for creating BareMetalHost configurations with flexible options.
    
    Replaces multiple hardcoded BMH fixtures with a single flexible factory
    that can generate various BMH configurations based on test needs.
    
    Returns:
        Callable that creates customized BareMetalHost resources with options for:
        - Node naming
        - Network configuration
        - User data inclusion
        - BMC addressing
    """
    def _create_bmh(
        node_name: str = "test-node",
        network_config_name: str = None,
        include_user_data: bool = True,
        user_data_name: str = "master-user-data",
        bmc_address: str = "redfish://192.168.1.100",
        bmc_credentials_name: str = None,
        boot_mac_address: str = "aa:bb:cc:dd:ee:ff",
        labels: Dict[str, str] = None,
        architecture: str = None,
        automated_cleaning_mode: str = None,
        boot_mode: str = None,
        online: bool = None,
        root_device_hints: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create a BareMetalHost resource with specified configuration.
        
        Args:
            node_name: Name for the BMH resource
            network_config_name: Optional network configuration secret name
            include_user_data: Whether to include userData section
            user_data_name: Name of the user data secret
            bmc_address: BMC connection address
            bmc_credentials_name: Custom BMC credentials secret name (defaults to node-based naming)
            boot_mac_address: Boot MAC address for the BMH
            labels: Optional labels dictionary for metadata
            architecture: Optional architecture specification
            automated_cleaning_mode: Optional automated cleaning mode
            boot_mode: Optional boot mode (UEFI/BIOS)
            online: Optional online status
            root_device_hints: Optional root device hints dictionary
            
        Returns:
            Dict[str, Any]: Configured BareMetalHost resource
        """
        # Build metadata
        metadata = {"name": node_name, "namespace": "openshift-machine-api"}
        if labels:
            metadata["labels"] = labels
            
        # Build BMC configuration with custom or default credentials name
        if bmc_credentials_name is None:
            bmc_credentials_name = f"{node_name}-bmc-secret"
            
        bmh = {
            "apiVersion": "metal3.io/v1alpha1",
            "kind": "BareMetalHost",
            "metadata": metadata,
            "spec": {
                "bmc": {"address": bmc_address, "credentialsName": bmc_credentials_name},
                "bootMACAddress": boot_mac_address
            }
        }
        
        # Add optional spec fields
        if architecture:
            bmh["spec"]["architecture"] = architecture
        if automated_cleaning_mode:
            bmh["spec"]["automatedCleaningMode"] = automated_cleaning_mode
        if boot_mode:
            bmh["spec"]["bootMode"] = boot_mode
        if online is not None:
            bmh["spec"]["online"] = online
        if root_device_hints:
            bmh["spec"]["rootDeviceHints"] = root_device_hints
            
        if network_config_name:
            bmh["spec"]["preprovisioningNetworkDataName"] = network_config_name
            
        if include_user_data:
            bmh["spec"]["userData"] = {"name": user_data_name, "namespace": "openshift-machine-api"}
            
        return bmh
    return _create_bmh


@pytest.fixture
def machine_factory():
    """Factory for creating Machine configurations with flexible provider specs.
    
    Replaces multiple hardcoded Machine fixtures with a single flexible factory
    that can generate various Machine configurations based on test needs.
    
    Returns:
        Callable that creates customized Machine resources with options for:
        - Machine naming and clustering
        - Provider spec complexity
        - User data configuration
        - Label customization
    """
    def _create_machine(
        machine_name: str = "test-machine",
        cluster_name: str = "test-cluster",
        include_full_provider_spec: bool = False,
        user_data_name: str = "master-user-data",
        include_cluster_labels: bool = True,
        machine_role: str = "master",
        include_spec_metadata: bool = True,
        include_user_data: bool = True
    ) -> Dict[str, Any]:
        """Create a Machine resource with specified configuration.
        
        Args:
            machine_name: Name for the Machine resource
            cluster_name: Cluster identifier for labels
            include_full_provider_spec: Whether to include full provider spec with image/deploy
            user_data_name: Name of the user data secret
            include_cluster_labels: Whether to include full cluster-api labels
            machine_role: Machine role (master/worker)
            include_spec_metadata: Whether to include spec.metadata section
            include_user_data: Whether to include userData in providerSpec
            
        Returns:
            Dict[str, Any]: Configured Machine resource
        """
        labels = {f"machine.openshift.io/cluster-api-machine-role": machine_role}
        
        if include_cluster_labels:
            labels.update({
                "machine.openshift.io/cluster-api-cluster": cluster_name,
                f"machine.openshift.io/cluster-api-machine-type": machine_role
            })
        
        # Build providerSpec value
        provider_spec_value = {
            "apiVersion": "machine.openshift.io/v1beta1",
            "kind": "BareMetalMachineProviderSpec"
        }
        
        if include_user_data:
            provider_spec_value["userData"] = {"name": user_data_name}
        
        machine = {
            "apiVersion": "machine.openshift.io/v1beta1",
            "kind": "Machine",
            "metadata": {
                "name": machine_name,
                "namespace": "openshift-machine-api",
                "labels": labels
            },
            "spec": {
                "providerSpec": {
                    "value": provider_spec_value
                }
            }
        }
        
        # Add spec.metadata section for node role labels
        if include_spec_metadata:
            if machine_role == "master":
                machine["spec"]["metadata"] = {"labels": {"node-role.kubernetes.io/control-plane": ""}}
            elif machine_role == "worker":
                machine["spec"]["metadata"] = {"labels": {"node-role.kubernetes.io/worker": ""}}
        
        if include_full_provider_spec:
            machine["spec"]["lifecycleHooks"] = {}
            machine["spec"]["providerSpec"]["value"].update({
                "customDeploy": {"method": "install_coreos"},
                "image": {"url": "https://example.com/rhcos.iso"}
            })
            
        return machine
    return _create_machine


@pytest.fixture
def secret_factory():
    """Factory for creating Secret configurations with flexible options.
    
    Creates Secret resources for testing BMC credentials, network configuration,
    and ETCD secrets with customizable data, type, and metadata.
    
    Returns:
        Callable that creates customized Secret resources with options for:
        - Secret naming and namespace configuration
        - Data content and type specification
        - Label and annotation customization
        - ETCD-specific naming patterns
    """
    def _create_secret(
        secret_name: str = "test-secret",
        secret_type: str = "Opaque",
        namespace: str = "openshift-machine-api",
        data_keys: Dict[str, str] = None,
        labels: Dict[str, str] = None,
        annotations: Dict[str, str] = None,
        string_data: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """Create a Secret resource with specified configuration.
        
        Args:
            secret_name: Name for the Secret resource
            secret_type: Type of secret (Opaque, kubernetes.io/tls, etc.)
            namespace: Kubernetes namespace for the secret
            data_keys: Dictionary of base64-encoded data keys and values
            labels: Optional labels dictionary for metadata
            annotations: Optional annotations dictionary for metadata
            string_data: Dictionary of plain text data (will be base64 encoded)
            
        Returns:
            Dict[str, Any]: Configured Secret resource
            
        Examples:
            # ETCD serving secret
            secret_factory(
                secret_name="etcd-serving-node1.example.com",
                namespace="openshift-etcd"
            )
            
            # BMC credentials secret
            secret_factory(
                secret_name="node1-bmc-secret", 
                string_data={"username": "admin", "password": "secret"}
            )
            
            # Network configuration secret
            secret_factory(
                secret_name="node1-network-config-secret",
                string_data={"nmstate": "interfaces:\\n- name: eno1"}
            )
        """
        # Parameter validation for ETCD scenarios
        if not secret_name or not isinstance(secret_name, str):
            raise ValueError("secret_name must be a non-empty string")
        if not namespace or not isinstance(namespace, str):
            raise ValueError("namespace must be a non-empty string")
        if secret_type not in ["Opaque", "kubernetes.io/tls", "kubernetes.io/service-account-token"]:
            # Allow other types but warn about common ones
            pass
        
        # ETCD-specific namespace optimization
        if "etcd-" in secret_name and namespace == "openshift-machine-api":
            # Auto-correct namespace for ETCD secrets
            namespace = "openshift-etcd"
        
        # Build metadata
        metadata = {"name": secret_name, "namespace": namespace}
        if labels:
            metadata["labels"] = labels
        if annotations:
            metadata["annotations"] = annotations
            
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": metadata,
            "type": secret_type
        }
        
        # Add data section if provided
        if data_keys:
            secret["data"] = data_keys
        elif string_data:
            # Convert string data to base64 for realistic Secret format
            import base64
            secret["data"] = {
                key: base64.b64encode(value.encode()).decode()
                for key, value in string_data.items()
            }
        else:
            # Default empty data section
            secret["data"] = {}
            
        return secret
    return _create_secret


@pytest.fixture
def pod_factory():
    """Factory for creating Pod configurations with flexible options.
    
    Creates Pod resources for testing ETCD pods and other container workloads
    with customizable status phases, labels, and container specifications.
    
    Returns:
        Callable that creates customized Pod resources with options for:
        - Pod naming and namespace configuration
        - Status phase and readiness simulation
        - Label and annotation customization
        - ETCD-specific naming patterns and labels
    """
    def _create_pod(
        pod_name: str = "test-pod",
        namespace: str = "openshift-etcd",
        labels: Dict[str, str] = None,
        annotations: Dict[str, str] = None,
        status_phase: str = "Running",
        app_label: str = None,
        node_name: str = None,
        ready_condition: str = "True"
    ) -> Dict[str, Any]:
        """Create a Pod resource with specified configuration.
        
        Args:
            pod_name: Name for the Pod resource
            namespace: Kubernetes namespace for the pod
            labels: Optional labels dictionary for metadata
            annotations: Optional annotations dictionary for metadata
            status_phase: Pod phase (Running, Failed, Pending, Succeeded, Unknown)
            app_label: Convenience parameter to set app label
            node_name: Node where pod is scheduled
            ready_condition: Ready condition status for pod
            
        Returns:
            Dict[str, Any]: Configured Pod resource
            
        Examples:
            # ETCD pod with running status
            pod_factory(
                pod_name="etcd-control1.example.com",
                app_label="etcd",
                status_phase="Running"
            )
            
            # Failed ETCD pod for testing failure scenarios
            pod_factory(
                pod_name="etcd-control2.example.com",
                app_label="etcd", 
                status_phase="Failed"
            )
            
            # Pod with specific node assignment
            pod_factory(
                pod_name="test-pod",
                node_name="worker-node-1",
                namespace="default"
            )
        """
        # Parameter validation for Pod scenarios
        if not pod_name or not isinstance(pod_name, str):
            raise ValueError("pod_name must be a non-empty string")
        if not namespace or not isinstance(namespace, str):
            raise ValueError("namespace must be a non-empty string")
        
        valid_phases = ["Running", "Failed", "Pending", "Succeeded", "Unknown"]
        if status_phase not in valid_phases:
            raise ValueError(f"status_phase must be one of {valid_phases}")
        
        valid_conditions = ["True", "False", "Unknown"]
        if ready_condition not in valid_conditions:
            raise ValueError(f"ready_condition must be one of {valid_conditions}")
        
        # ETCD-specific optimizations
        if "etcd-" in pod_name:
            # Auto-set namespace for ETCD pods
            if namespace not in ["openshift-etcd"]:
                namespace = "openshift-etcd"
            # Auto-set app label for ETCD pods if not specified
            if not app_label and not labels:
                app_label = "etcd"
        
        # Build metadata
        metadata = {"name": pod_name, "namespace": namespace}
        
        # Build labels
        pod_labels = {}
        if app_label:
            pod_labels["app"] = app_label
        if labels:
            pod_labels.update(labels)
        if pod_labels:
            metadata["labels"] = pod_labels
            
        if annotations:
            metadata["annotations"] = annotations
            
        pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": metadata,
            "status": {"phase": status_phase}
        }
        
        # Add node assignment if specified
        if node_name:
            pod["spec"] = {"nodeName": node_name}
            
        # Add ready condition if not Running (Running assumes ready)
        if status_phase != "Running" or ready_condition != "True":
            pod["status"]["conditions"] = [
                {"type": "Ready", "status": ready_condition}
            ]
            
        return pod
    return _create_pod


@pytest.fixture
def node_factory():
    """Factory for creating Node configurations with flexible options.
    
    Creates Node resources for testing control plane and worker node scenarios
    with customizable readiness states and labels.
    
    Returns:
        Callable that creates customized Node resources with options for:
        - Node naming and hostname configuration
        - Control plane vs worker role designation
        - Readiness status simulation
        - Network conditions and status
    """
    def _create_node(
        node_name: str = "test-node",
        hostname: str = None,
        is_control_plane: bool = True,
        ready_status: str = "True",
        memory_pressure: str = "False",
        disk_pressure: str = "False",
        pid_pressure: str = "False"
    ) -> Dict[str, Any]:
        """Create a Node resource with specified configuration.
        
        Args:
            node_name: Name for the Node resource
            hostname: Kubernetes hostname (defaults to node_name if not provided)
            is_control_plane: Whether this is a control plane node (affects labels)
            ready_status: Ready condition status ("True", "False", "Unknown")
            memory_pressure: MemoryPressure condition status
            disk_pressure: DiskPressure condition status  
            pid_pressure: PIDPressure condition status
            
        Returns:
            Dict[str, Any]: Configured Node resource
        """
        if hostname is None:
            hostname = node_name
            
        # Set up node role labels
        labels = {"kubernetes.io/hostname": hostname}
        if is_control_plane:
            labels["node-role.kubernetes.io/control-plane"] = ""
            labels["node-role.kubernetes.io/master"] = ""
        else:
            labels["node-role.kubernetes.io/worker"] = ""
        
        # Build status conditions
        conditions = [
            {"type": "Ready", "status": ready_status},
            {"type": "MemoryPressure", "status": memory_pressure},
            {"type": "DiskPressure", "status": disk_pressure},
            {"type": "PIDPressure", "status": pid_pressure}
        ]
        
        return {
            "apiVersion": "v1",
            "kind": "Node",
            "metadata": {
                "name": node_name,
                "labels": labels
            },
            "status": {
                "conditions": conditions
            }
        }
    return _create_node