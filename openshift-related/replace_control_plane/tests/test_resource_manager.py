#!/usr/bin/env python3
"""
Comprehensive pytest tests for resource_manager module.
Tests all functionality of ResourceManager class with realistic OpenShift data.
"""

import pytest
import os
import sys

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import Mock, patch, call  # noqa: E402
from modules.resource_manager import ResourceManager  # noqa: E402


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def kubeconfig_path():
    """Path to kubeconfig for testing"""
    return "/home/stratus/temp/kubeconfig"


@pytest.fixture
def mock_printer():
    """Simple mock printer - not testing printer functionality"""
    return Mock()


@pytest.fixture
def mock_execute_oc_command():
    """Mock function for executing OpenShift CLI commands"""
    
    mock_func = Mock()
    
    def _mock_execute_oc(cmd, **kwargs):
        # Check if return_value has been explicitly set by a test  
        if hasattr(mock_func, '_explicit_return_value'):
            explicit_value = mock_func._explicit_return_value
            # Return explicit_value regardless of whether it's None, Mock, or other value
            if not isinstance(explicit_value, Mock) or explicit_value is None:
                return explicit_value
        
        # Handle json_output parameter - when json_output=True, return data directly
        json_output = kwargs.get('json_output', False)
        
        # Default behavior for common commands
        if "get" in cmd and "bmh" in cmd:
            data = sample_bmh_data()
            return data if json_output else (data, "", 0)
        elif "get" in cmd and "machine" in cmd and len(cmd) == 7:  # Single machine get
            machine_name = cmd[2]  # Extract machine name from command
            if "control" in machine_name:
                data = sample_machine_data()  # Control plane machine with owner ref
            else:
                data = sample_worker_machine_data()  # Worker machine with owner ref
            return data if json_output else (data, "", 0)
        elif "get" in cmd and "machines" in cmd:  # All machines
            data = sample_machines_data()
            return data if json_output else (data, "", 0)
        elif "get" in cmd and "machineset" in cmd:
            # Handle both singular and plural machineset queries
            if len(cmd) > 2 and cmd[2] not in ["-n", "machineset"]:  # Single machineset query
                # Return single machineset object (not wrapped in items)
                data = {
                    "apiVersion": "machine.openshift.io/v1beta1",
                    "kind": "MachineSet",
                    "metadata": {
                        "name": "test-worker-machineset", 
                        "namespace": "openshift-machine-api",
                    },
                    "spec": {"replicas": 3},
                }
            else:  # Multiple machinesets query
                data = sample_machineset_data()
            return data if json_output else (data, "", 0)
        elif "apply" in cmd:
            data = {"success": True}
            return data if json_output else (data, "", 0)
        elif "delete" in cmd:
            data = {"success": True}
            return data if json_output else (data, "", 0)
        elif "scale" in cmd:
            data = {"success": True}
            return data if json_output else (data, "", 0)
        
        data = {"success": True}
        return data if json_output else (data, "", 0)

    mock_func.side_effect = _mock_execute_oc
    return mock_func


@pytest.fixture
def mock_format_runtime():
    """Mock function for formatting runtime duration"""
    return Mock(return_value="5m 30s")


@pytest.fixture
def mock_find_bmh_by_pattern():
    """Mock function for finding BMH by pattern"""
    return Mock(return_value="test-control-1.example.com")


@pytest.fixture
def mock_backup_manager():
    """Mock BackupManager for testing"""
    backup_manager = Mock()
    backup_manager.backup_bmh_definition = Mock(return_value="/tmp/bmh_backup.yaml")
    backup_manager.backup_machine_definition = Mock(return_value="/tmp/machine_backup.yaml")
    return backup_manager


@pytest.fixture
def mock_resource_monitor_class():
    """Mock ResourceMonitor class constructor"""
    resource_monitor = Mock()
    resource_monitor.monitor_provisioning_sequence = Mock(return_value=(True, "ready", None))
    return Mock(return_value=resource_monitor)


@pytest.fixture
def mock_handle_provisioning_failure():
    """Mock provisioning failure handler"""
    return Mock()


@pytest.fixture
def resource_manager(mock_printer, mock_execute_oc_command, mock_find_bmh_by_pattern, mock_format_runtime):
    """ResourceManager instance with mocked dependencies"""
    return ResourceManager(
        printer=mock_printer,
        execute_oc_command=mock_execute_oc_command,
        find_bmh_by_pattern=mock_find_bmh_by_pattern,
        format_runtime=mock_format_runtime,
    )


def sample_bmh_data():
    """Sample BMH data for testing"""
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "metal3.io/v1alpha1",
                "kind": "BareMetalHost",
                "metadata": {
                    "name": "test-control-1.example.com",
                    "namespace": "openshift-machine-api",
                    "labels": {"installer.openshift.io/role": "control-plane"},
                },
                "spec": {
                    "architecture": "x86_64",
                    "bmc": {
                        "address": "redfish+http://192.168.1.100:8000/redfish/v1/Systems/test",
                        "credentialsName": "test-control-1-bmc-secret",
                    },
                    "bootMACAddress": "52:54:00:12:34:56",
                    "consumerRef": {
                        "apiVersion": "machine.openshift.io/v1beta1",
                        "kind": "Machine",
                        "name": "test-control-1-machine",
                        "namespace": "openshift-machine-api",
                    },
                    "online": True,
                },
                "status": {"provisioning": {"state": "provisioned"}},
            },
            {
                "apiVersion": "metal3.io/v1alpha1",
                "kind": "BareMetalHost",
                "metadata": {
                    "name": "test-worker-1.example.com",
                    "namespace": "openshift-machine-api",
                    "labels": {"installer.openshift.io/role": "worker"},
                },
                "spec": {
                    "architecture": "x86_64",
                    "bmc": {
                        "address": "redfish+http://192.168.1.101:8000/redfish/v1/Systems/test",
                        "credentialsName": "test-worker-1-bmc-secret",
                    },
                    "bootMACAddress": "52:54:00:12:34:57",
                    "consumerRef": {
                        "apiVersion": "machine.openshift.io/v1beta1",
                        "kind": "Machine",
                        "name": "test-worker-1-machine",
                        "namespace": "openshift-machine-api",
                    },
                    "online": True,
                },
                "status": {"provisioning": {"state": "provisioned"}},
            },
        ],
    }


def sample_machine_data():
    """Sample single machine data for testing"""
    return {
        "apiVersion": "machine.openshift.io/v1beta1",
        "kind": "Machine",
        "metadata": {
            "name": "test-control-1-machine",
            "namespace": "openshift-machine-api",
            "ownerReferences": [
                {
                    "apiVersion": "machine.openshift.io/v1beta1",
                    "kind": "MachineSet",
                    "name": "test-worker-machineset",
                    "uid": "12345678-1234-5678-9012-123456789012",
                }
            ],
        },
        "spec": {"metadata": {"labels": {"node-role.kubernetes.io/control-plane": ""}}},
    }


def sample_worker_machine_data():
    """Sample worker machine data with MachineSet owner reference"""
    return {
        "apiVersion": "machine.openshift.io/v1beta1",
        "kind": "Machine",
        "metadata": {
            "name": "test-worker-1-machine",
            "namespace": "openshift-machine-api",
            "ownerReferences": [
                {
                    "apiVersion": "machine.openshift.io/v1beta1",
                    "kind": "MachineSet",
                    "name": "test-worker-machineset",
                    "uid": "12345678-1234-5678-9012-123456789012",
                }
            ],
        },
        "spec": {"metadata": {"labels": {"node-role.kubernetes.io/worker": ""}}},
    }


def sample_machines_data():
    """Sample machines data for testing"""
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "machine.openshift.io/v1beta1",
                "kind": "Machine",
                "metadata": {"name": "test-control-1-machine", "namespace": "openshift-machine-api"},
            },
            {
                "apiVersion": "machine.openshift.io/v1beta1",
                "kind": "Machine",
                "metadata": {
                    "name": "test-worker-1-machine",
                    "namespace": "openshift-machine-api",
                    "ownerReferences": [
                        {
                            "apiVersion": "machine.openshift.io/v1beta1",
                            "kind": "MachineSet",
                            "name": "test-worker-machineset",
                            "uid": "12345678-1234-5678-9012-123456789012",
                        }
                    ],
                },
            },
        ],
    }


def sample_machineset_data():
    """Sample MachineSet data for testing"""
    return {
        "items": [
            {
                "apiVersion": "machine.openshift.io/v1beta1",
                "kind": "MachineSet",
                "metadata": {
                    "name": "test-worker-machineset", 
                    "namespace": "openshift-machine-api",
                    "labels": {
                        "machine.openshift.io/cluster-api-machine-role": "worker"
                    }
                },
                "spec": {"replicas": 3},
            }
        ]
    }


def sample_copied_files():
    """Sample copied files dictionary for testing"""
    return {
        "bmh": "/tmp/test-bmh.yaml",
        "machine": "/tmp/test-machine.yaml",
        "secret": "/tmp/test-secret.yaml",
        "nmstate": "/tmp/test-nmstate.yaml",
    }


# =============================================================================
# Tests for ResourceManager Class
# =============================================================================


class TestResourceManagerInitialization:
    """Test cases for ResourceManager initialization"""

    def test_initialization_with_all_dependencies(
        self, mock_printer, mock_execute_oc_command, mock_find_bmh_by_pattern, mock_format_runtime
    ):
        """Test ResourceManager initialization with all dependencies"""
        rm = ResourceManager(
            printer=mock_printer,
            execute_oc_command=mock_execute_oc_command,
            find_bmh_by_pattern=mock_find_bmh_by_pattern,
            format_runtime=mock_format_runtime,
        )

        assert rm.printer == mock_printer
        assert rm.execute_oc_command == mock_execute_oc_command
        assert rm.find_bmh_by_pattern == mock_find_bmh_by_pattern
        assert rm.format_runtime == mock_format_runtime
        assert rm._bmh_cache is None
        assert rm._cache_timestamp is None
        assert rm._cache_ttl == 300

    def test_initialization_with_minimal_dependencies(self):
        """Test ResourceManager initialization with minimal dependencies"""
        rm = ResourceManager()

        assert rm.printer is None
        assert rm.execute_oc_command is None
        assert rm.find_bmh_by_pattern is None
        assert rm.format_runtime is None


class TestBMHDataCaching:
    """Test cases for BMH data caching functionality"""

    def test_get_bmh_data_initial_fetch(self, resource_manager):
        """Test initial BMH data fetch and caching"""
        with patch("time.time", return_value=1000.0):
            result = resource_manager._get_bmh_data()

        assert result is not None
        assert resource_manager._bmh_cache is not None
        assert resource_manager._cache_timestamp == 1000.0
        resource_manager.execute_oc_command.assert_called_once()

    def test_get_bmh_data_cache_hit(self, resource_manager):
        """Test BMH data retrieval from cache when cache is valid"""
        # Set up cached data
        resource_manager._bmh_cache = sample_bmh_data()
        resource_manager._cache_timestamp = 1000.0

        with patch("time.time", return_value=1200.0):  # Within TTL (300s)
            result = resource_manager._get_bmh_data()

        assert result == sample_bmh_data()
        resource_manager.execute_oc_command.assert_not_called()

    def test_get_bmh_data_cache_expired(self, resource_manager):
        """Test BMH data refresh when cache is expired"""
        # Set up expired cached data
        resource_manager._bmh_cache = {"old": "data"}
        resource_manager._cache_timestamp = 500.0

        with patch("time.time", return_value=1000.0):  # Beyond TTL
            result = resource_manager._get_bmh_data()

        assert result is not None
        assert result != {"old": "data"}
        resource_manager.execute_oc_command.assert_called_once()

    def test_get_bmh_data_force_refresh(self, resource_manager):
        """Test forced refresh of BMH data"""
        # Set up cached data
        resource_manager._bmh_cache = {"cached": "data"}
        resource_manager._cache_timestamp = 1000.0

        with patch("time.time", return_value=1100.0):  # Within TTL
            result = resource_manager._get_bmh_data(force_refresh=True)

        assert result is not None
        resource_manager.execute_oc_command.assert_called_once()


class TestBMHDataUtilities:
    """Test cases for BMH data utility methods"""

    def test_find_bmh_data_by_name_found(self, resource_manager):
        """Test finding BMH data by name when it exists"""
        bmh_data = sample_bmh_data()
        result = resource_manager._find_bmh_data_by_name("test-control-1.example.com", bmh_data)

        assert result is not None
        assert result["metadata"]["name"] == "test-control-1.example.com"

    def test_find_bmh_data_by_name_not_found(self, resource_manager):
        """Test finding BMH data by name when it doesn't exist"""
        bmh_data = sample_bmh_data()
        result = resource_manager._find_bmh_data_by_name("nonexistent-bmh", bmh_data)

        assert result is None

    def test_find_bmh_data_by_name_empty_data(self, resource_manager):
        """Test finding BMH data with empty data"""
        result = resource_manager._find_bmh_data_by_name("any-name", {})
        assert result is None

        result = resource_manager._find_bmh_data_by_name("any-name", {"items": []})
        assert result is None


class TestOperationFailureHandling:
    """Test cases for operation failure handling"""

    def test_handle_operation_failure_with_runtime(self, resource_manager):
        """Test operation failure handling with runtime calculation"""
        with patch("time.time", return_value=1100.0):
            result = resource_manager._handle_operation_failure("Test error", 1000.0, 5)

        assert result == (None, None, 5)
        resource_manager.format_runtime.assert_called_once_with(1000.0, 1100.0)

    def test_handle_operation_failure_without_format_runtime(self, resource_manager):
        """Test operation failure handling without format_runtime"""
        resource_manager.format_runtime = None

        result = resource_manager._handle_operation_failure("Test error", 1000.0, 3)

        assert result == (None, None, 3)


class TestFindAndValidateBMH:
    """Test cases for finding and validating BMH"""

    def test_find_and_validate_bmh_success(self, resource_manager):
        """Test successful BMH finding and validation"""
        with patch.object(resource_manager, "_get_bmh_data", return_value=sample_bmh_data()):
            bmh_name, all_bmh_data, step = resource_manager._find_and_validate_bmh("test-control-1", 2, 10, 1000.0)

        assert bmh_name == "test-control-1.example.com"
        assert all_bmh_data is not None
        assert step == 3
        resource_manager.find_bmh_by_pattern.assert_called_once_with(
            "test-control-1", all_bmh_data, printer=resource_manager.printer
        )

    def test_find_and_validate_bmh_no_data(self, resource_manager):
        """Test BMH validation when no data is available"""
        with patch.object(resource_manager, "_get_bmh_data", return_value=None):
            bmh_name, all_bmh_data, step = resource_manager._find_and_validate_bmh("test-control-1", 2, 10, 1000.0)

        assert bmh_name is None
        assert all_bmh_data is None
        assert step == 2

    def test_find_and_validate_bmh_not_found(self, resource_manager):
        """Test BMH validation when BMH pattern is not found"""
        resource_manager.find_bmh_by_pattern.return_value = None

        with patch.object(resource_manager, "_get_bmh_data", return_value=sample_bmh_data()):
            bmh_name, all_bmh_data, step = resource_manager._find_and_validate_bmh("nonexistent-node", 2, 10, 1000.0)

        assert bmh_name is None
        assert all_bmh_data is None
        assert step == 2


class TestBackupBMHAndMachineResources:
    """Test cases for backing up BMH and machine resources"""

    def test_backup_bmh_and_machine_success(self, resource_manager, mock_backup_manager):
        """Test successful backup of BMH and machine resources"""
        bmh_data = sample_bmh_data()

        machine_name, step = resource_manager._backup_bmh_and_machine_resources(
            "test-control-1.example.com", bmh_data, mock_backup_manager, 3, 10, 1000.0
        )

        assert machine_name == "test-control-1-machine"
        assert step == 4
        mock_backup_manager.backup_bmh_definition.assert_called_once()
        mock_backup_manager.backup_machine_definition.assert_called_once()
        resource_manager.execute_oc_command.assert_called()

    def test_backup_bmh_and_machine_bmh_not_found(self, resource_manager, mock_backup_manager):
        """Test backup when specific BMH is not found in data"""
        bmh_data = sample_bmh_data()

        result = resource_manager._backup_bmh_and_machine_resources(
            "nonexistent-bmh", bmh_data, mock_backup_manager, 3, 10, 1000.0
        )

        # _handle_simple_failure returns (None, step) - 2-tuple  
        assert result == (None, 3)

    def test_backup_bmh_and_machine_no_consumer_ref(self, resource_manager, mock_backup_manager):
        """Test backup when BMH has no consumer reference"""
        bmh_data = sample_bmh_data()
        # Remove consumer reference
        del bmh_data["items"][0]["spec"]["consumerRef"]

        result = resource_manager._backup_bmh_and_machine_resources(
            "test-control-1.example.com", bmh_data, mock_backup_manager, 3, 10, 1000.0
        )

        # _handle_simple_failure returns (None, step) - 2-tuple  
        assert result == (None, 3)

    def test_backup_bmh_and_machine_failed_machine_fetch(self, resource_manager, mock_backup_manager):
        """Test backup when machine data fetch fails"""
        resource_manager.execute_oc_command.side_effect = [None]  # Machine fetch fails
        bmh_data = sample_bmh_data()

        result = resource_manager._backup_bmh_and_machine_resources(
            "test-control-1.example.com", bmh_data, mock_backup_manager, 3, 10, 1000.0
        )

        # _handle_simple_failure returns (None, step) - 2-tuple  
        assert result == (None, 3)


class TestRemoveFailedNodeResources:
    """Test cases for removing failed node resources"""

    def test_remove_failed_node_resources_success(self, resource_manager):
        """Test successful removal of failed node resources"""
        with patch("time.sleep"):  # Mock sleep to speed up tests
            step = resource_manager._remove_failed_node_resources("test-bmh", "test-machine", 5, 10)

        assert step == 6

        # Verify machine deletion was called
        machine_delete_call = call(
            ["delete", "machine", "test-machine", "-n", "openshift-machine-api"], printer=resource_manager.printer
        )

        # Verify BMH deletion was called
        bmh_delete_call = call(
            ["delete", "bmh", "test-bmh", "-n", "openshift-machine-api"], printer=resource_manager.printer
        )

        resource_manager.execute_oc_command.assert_has_calls([machine_delete_call, bmh_delete_call])


class TestBackupAndRemoveResources:
    """Test cases for the main backup and remove workflow"""

    def test_backup_and_remove_resources_success(self, resource_manager, mock_backup_manager):
        """Test complete successful backup and remove workflow"""
        with patch.object(
            resource_manager, "_find_and_validate_bmh", return_value=("test-bmh", sample_bmh_data(), 3)
        ), patch.object(
            resource_manager, "_backup_bmh_and_machine_resources", return_value=("test-machine", 4)
        ), patch.object(
            resource_manager, "_remove_failed_node_resources", return_value=5
        ):

            bmh_name, machine_name, step = resource_manager.backup_and_remove_resources(
                "failed-node", mock_backup_manager, 1000.0, 2, 10
            )

        assert bmh_name == "test-bmh"
        assert machine_name == "test-machine"
        assert step == 5

    def test_backup_and_remove_resources_bmh_failure(self, resource_manager, mock_backup_manager):
        """Test backup and remove workflow when BMH validation fails"""
        with patch.object(resource_manager, "_find_and_validate_bmh", return_value=(None, None, 3)):

            bmh_name, machine_name, step = resource_manager.backup_and_remove_resources(
                "failed-node", mock_backup_manager, 1000.0, 2, 10
            )

        assert bmh_name is None
        assert machine_name is None
        assert step == 3

    def test_backup_and_remove_resources_backup_failure(self, resource_manager, mock_backup_manager):
        """Test backup and remove workflow when backup fails"""
        with patch.object(
            resource_manager, "_find_and_validate_bmh", return_value=("test-bmh", sample_bmh_data(), 3)
        ), patch.object(resource_manager, "_backup_bmh_and_machine_resources", return_value=(None, 4)):

            bmh_name, machine_name, step = resource_manager.backup_and_remove_resources(
                "failed-node", mock_backup_manager, 1000.0, 2, 10
            )

        assert bmh_name is None
        assert machine_name is None
        assert step == 4


class TestMachineSetOperations:
    """Test cases for MachineSet operations"""

    def test_find_machineset_for_machine_success(self, resource_manager):
        """Test finding MachineSet for a machine successfully"""
        # Make sure the mock returns data with owner references
        machine_data = sample_machine_data()
        resource_manager.execute_oc_command.reset_mock()
        resource_manager.execute_oc_command.return_value = machine_data

        machineset_name = resource_manager.find_machineset_for_machine("test-control-1-machine")

        assert machineset_name == "test-worker-machineset"
        resource_manager.execute_oc_command.assert_called_once_with(
            ["get", "machine", "test-control-1-machine", "-n", "openshift-machine-api", "-o", "json"],
            json_output=True,
            printer=resource_manager.printer,
        )

    def test_find_machineset_for_machine_no_owner(self, resource_manager):
        """Test finding MachineSet when machine has no owner reference"""
        # Mock machine without owner references
        machine_without_owner = {"metadata": {"name": "test-machine", "namespace": "openshift-machine-api"}}
        resource_manager.execute_oc_command._explicit_return_value = machine_without_owner

        machineset_name = resource_manager.find_machineset_for_machine("test-machine")

        # Reset the mock for other tests
        if hasattr(resource_manager.execute_oc_command, '_explicit_return_value'):
            del resource_manager.execute_oc_command._explicit_return_value
        assert machineset_name is None

    def test_find_machineset_for_machine_failed_fetch(self, resource_manager):
        """Test finding MachineSet when machine fetch fails"""
        resource_manager.execute_oc_command._explicit_return_value = None

        machineset_name = resource_manager.find_machineset_for_machine("test-machine")

        # Reset the mock for other tests
        if hasattr(resource_manager.execute_oc_command, '_explicit_return_value'):
            del resource_manager.execute_oc_command._explicit_return_value
        assert machineset_name is None

    def test_get_machineset_by_name_found(self, resource_manager):
        """Test getting MachineSet by name when it exists"""
        machinesets_data = {
            "items": [
                {"metadata": {"name": "test-machineset-1"}},
                {"metadata": {"name": "test-machineset-2"}},
                {"metadata": {"name": "target-machineset"}},
            ]
        }

        result = resource_manager.get_machineset_by_name(machinesets_data, "target-machineset")

        assert result is not None
        assert result["metadata"]["name"] == "target-machineset"

    def test_get_machineset_by_name_not_found(self, resource_manager):
        """Test getting MachineSet by name when it doesn't exist"""
        machinesets_data = {
            "items": [{"metadata": {"name": "test-machineset-1"}}, {"metadata": {"name": "test-machineset-2"}}]
        }

        result = resource_manager.get_machineset_by_name(machinesets_data, "nonexistent-machineset")

        assert result is None

    def test_scale_machineset_for_machine_scale_up(self, resource_manager):
        """Test scaling MachineSet up for a machine"""
        with patch.object(resource_manager, "find_machineset_for_machine", return_value="test-machineset"):
            result = resource_manager.scale_machineset_for_machine("test-machine", "up")

        assert result is True

        # Verify scale command was called
        resource_manager.execute_oc_command.assert_called_with(
            ["scale", "machineset", "test-machineset", "-n", "openshift-machine-api", "--replicas=4"],
            printer=resource_manager.printer,
        )

    def test_scale_machineset_for_machine_scale_down(self, resource_manager):
        """Test scaling MachineSet down for a machine"""
        with patch.object(resource_manager, "find_machineset_for_machine", return_value="test-machineset"):
            result = resource_manager.scale_machineset_for_machine("test-machine", "down")

        assert result is True

        # Verify scale command was called with correct replicas (3-1=2)
        resource_manager.execute_oc_command.assert_called_with(
            ["scale", "machineset", "test-machineset", "-n", "openshift-machine-api", "--replicas=2"],
            printer=resource_manager.printer,
        )

    def test_scale_machineset_for_machine_no_machineset(self, resource_manager):
        """Test scaling when machine has no MachineSet"""
        with patch.object(resource_manager, "find_machineset_for_machine", return_value=None):
            result = resource_manager.scale_machineset_for_machine("test-machine", "up")

        assert result is False

    def test_scale_machineset_for_machine_invalid_direction(self, resource_manager):
        """Test scaling with invalid direction"""
        with patch.object(resource_manager, "find_machineset_for_machine", return_value="test-machineset"):
            result = resource_manager.scale_machineset_for_machine("test-machine", "invalid")

        assert result is False


class TestApplyResourcesAndMonitor:
    """Test cases for applying resources and monitoring"""

    def test_apply_resources_and_monitor_control_plane_success(
        self, resource_manager, mock_resource_monitor_class, mock_handle_provisioning_failure
    ):
        """Test successful resource application and monitoring for control plane"""
        copied_files = sample_copied_files()

        result_files, step = resource_manager.apply_resources_and_monitor(
            copied_files,
            "/tmp/backup",
            "new-control-1",
            1000.0,
            8,
            12,
            is_addition=False,
            ResourceMonitor=mock_resource_monitor_class,
            handle_provisioning_failure=mock_handle_provisioning_failure,
        )

        assert result_files == copied_files
        assert step == 10  # 8 + 1 (apply) + 1 (monitor success)

        # Verify all files except nmstate were applied
        apply_calls = resource_manager.execute_oc_command.call_args_list
        apply_file_calls = [call for call in apply_calls if "apply" in call[0][0]]
        assert len(apply_file_calls) == 3  # bmh, machine, secret (not nmstate)

    def test_apply_resources_and_monitor_worker_addition_success(
        self, resource_manager, mock_resource_monitor_class, mock_handle_provisioning_failure
    ):
        """Test successful resource application and monitoring for worker addition"""
        copied_files = sample_copied_files()

        # Ensure the mock returns the correct machineset data for worker scaling
        def mock_get_machineset_cmd(cmd, **kwargs):
            if "get" in cmd and "machineset" in cmd:
                return sample_machineset_data()
            return resource_manager.execute_oc_command.side_effect(cmd, **kwargs)
        
        resource_manager.execute_oc_command.side_effect = mock_get_machineset_cmd
        
        with patch.object(resource_manager, "scale_machineset_directly", return_value=True) as mock_scale:
            result_files, step = resource_manager.apply_resources_and_monitor(
                copied_files,
                "/tmp/backup",
                "new-worker-1",
                1000.0,
                5,
                8,
                is_addition=True,
                ResourceMonitor=mock_resource_monitor_class,
                handle_provisioning_failure=mock_handle_provisioning_failure,
            )

        assert result_files == copied_files
        assert step == 7  # 5 + 1 (apply) + 1 (monitor success)

        # Verify machine file was not applied for worker addition
        apply_calls = resource_manager.execute_oc_command.call_args_list
        apply_file_calls = [call for call in apply_calls if "apply" in call[0][0]]
        assert len(apply_file_calls) == 2  # bmh, secret only (not machine, not nmstate)

        # Verify machineset scaling was called
        mock_scale.assert_called_once()

    def test_apply_resources_and_monitor_provisioning_failure(
        self, resource_manager, mock_resource_monitor_class, mock_handle_provisioning_failure
    ):
        """Test resource application when provisioning monitoring fails"""
        copied_files = sample_copied_files()

        # Configure monitor to return failure
        monitor_instance = mock_resource_monitor_class.return_value
        monitor_instance.monitor_provisioning_sequence.return_value = (False, "failed", "Network error")

        result_files, step = resource_manager.apply_resources_and_monitor(
            copied_files,
            "/tmp/backup",
            "new-control-1",
            1000.0,
            8,
            12,
            is_addition=False,
            ResourceMonitor=mock_resource_monitor_class,
            handle_provisioning_failure=mock_handle_provisioning_failure,
        )

        assert result_files is None
        assert step == 9  # 8 + 1 (apply), no increment for failed monitoring

        # Verify provisioning failure handler was called
        mock_handle_provisioning_failure.assert_called_once()

    def test_apply_resources_and_monitor_keyboard_interrupt(
        self, resource_manager, mock_resource_monitor_class, mock_handle_provisioning_failure
    ):
        """Test resource application when monitoring is interrupted"""
        copied_files = sample_copied_files()

        # Configure monitor to raise KeyboardInterrupt
        monitor_instance = mock_resource_monitor_class.return_value
        monitor_instance.monitor_provisioning_sequence.side_effect = KeyboardInterrupt()

        result_files, step = resource_manager.apply_resources_and_monitor(
            copied_files,
            "/tmp/backup",
            "new-control-1",
            1000.0,
            8,
            12,
            is_addition=False,
            ResourceMonitor=mock_resource_monitor_class,
            handle_provisioning_failure=mock_handle_provisioning_failure,
        )

        assert result_files is None
        assert step == 9  # 8 + 1 (apply), no increment for interrupted monitoring

        # Verify provisioning failure handler was not called for interrupt
        mock_handle_provisioning_failure.assert_not_called()


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests that verify end-to-end workflows"""

    @patch("time.time", side_effect=[1000.0, 1100.0, 1200.0, 1300.0])
    def test_full_backup_and_remove_workflow(self, mock_time, resource_manager, mock_backup_manager, kubeconfig_path):
        """Test complete backup and remove workflow"""
        # Set up environment
        os.environ["KUBECONFIG"] = kubeconfig_path

        # Execute the workflow
        bmh_name, machine_name, final_step = resource_manager.backup_and_remove_resources(
            "failed-control-1", mock_backup_manager, 1000.0, 2, 8
        )

        # Verify successful completion
        assert bmh_name == "test-control-1.example.com"
        assert machine_name == "test-control-1-machine"
        assert final_step == 5

        # Verify all major operations were called
        resource_manager.find_bmh_by_pattern.assert_called_once()
        mock_backup_manager.backup_bmh_definition.assert_called_once()
        mock_backup_manager.backup_machine_definition.assert_called_once()

    @patch("time.time", side_effect=[1000.0, 1100.0, 1200.0])
    def test_full_apply_and_monitor_workflow(
        self,
        mock_time,
        resource_manager,
        mock_resource_monitor_class,
        mock_handle_provisioning_failure,
        kubeconfig_path,
    ):
        """Test complete apply resources and monitor workflow"""
        # Set up environment
        os.environ["KUBECONFIG"] = kubeconfig_path

        copied_files = sample_copied_files()

        with patch.object(resource_manager, "scale_machineset_for_machine", return_value=True):
            result_files, final_step = resource_manager.apply_resources_and_monitor(
                copied_files,
                "/tmp/backup",
                "new-worker-1",
                1000.0,
                3,
                6,
                is_addition=True,
                ResourceMonitor=mock_resource_monitor_class,
                handle_provisioning_failure=mock_handle_provisioning_failure,
            )

        # Verify successful completion
        assert result_files == copied_files
        assert final_step == 5

        # Verify resource monitoring was set up
        mock_resource_monitor_class.assert_called_once_with(
            "new-worker-1",
            "/tmp/backup",
            is_addition=True,
            is_expansion=False,
            printer=resource_manager.printer,
            execute_oc_command=resource_manager.execute_oc_command,
        )

    @patch("time.time", side_effect=[1000.0, 1200.0, 1400.0])
    def test_caching_performance_workflow(self, mock_time, resource_manager, kubeconfig_path):
        """Test that caching improves performance in repeated operations"""
        # Set up environment
        os.environ["KUBECONFIG"] = kubeconfig_path

        # First call should fetch data
        result1 = resource_manager._get_bmh_data()
        assert result1 is not None

        # Reset mock to verify second call doesn't fetch
        resource_manager.execute_oc_command.reset_mock()

        # Second call should use cache (within TTL)
        result2 = resource_manager._get_bmh_data()
        assert result2 == result1

        # Verify no additional API call was made
        resource_manager.execute_oc_command.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__])
