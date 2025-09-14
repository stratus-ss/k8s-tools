#!/usr/bin/env python3
"""
Comprehensive pytest tests for orchestrator module.
Tests all functionality of NodeOperationOrchestrator class with realistic OpenShift data.
"""

import pytest
import os
import sys
import time

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import Mock, patch  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from modules.orchestrator import (  # noqa: E402
    NodeOperationOrchestrator,
    handle_successful_completion,
    handle_provisioning_failure,
)  # noqa: E402

# Test Configuration Constants
KUBECONFIG_PATH = "/home/stratus/temp/kubeconfig"


@pytest.fixture
def mock_execute_oc_command(sample_machines_data):
    """Mock function for executing OpenShift CLI commands.
    
    NOTE: This fixture overrides the basic conftest.py version to provide
    orchestrator-specific behavior for machine data queries. The custom logic
    returns sample_machines_data fixture for machine-related commands.
    """

    def _mock_execute_oc(cmd, **kwargs):
        # Return different responses based on command
        if "get" in cmd and "machines" in cmd:
            return sample_machines_data
        return {"success": True}

    mock_func = Mock(side_effect=_mock_execute_oc)
    return mock_func



@pytest.fixture
def mock_backup_manager_class():
    """Mock BackupManager class constructor"""
    backup_manager = Mock()
    backup_manager.setup_backup_directory = Mock(return_value="/tmp/backup_test")
    backup_manager.backup_template_bmh = Mock(return_value=("/tmp/template.yaml", False))
    backup_manager.copy_files_for_replacement = Mock(
        return_value={
            "bmh_file": "/tmp/bmh.yaml",
            "machine_file": "/tmp/machine.yaml",
            "secret_file": "/tmp/secret.yaml",
        }
    )

    return Mock(return_value=backup_manager)


@pytest.fixture
def mock_node_configurator_class():
    """Mock NodeConfigurator class constructor"""
    node_configurator = Mock()
    return Mock(return_value=node_configurator)


@pytest.fixture
def mock_resource_monitor_class():
    """Mock ResourceMonitor class constructor"""
    resource_monitor = Mock()
    return Mock(return_value=resource_monitor)


@pytest.fixture
def mock_resource_manager_class():
    """Mock ResourceManager class constructor"""
    resource_manager = Mock()
    resource_manager.backup_and_remove_resources = Mock(return_value=(True, True, 5))
    resource_manager.apply_resources_and_monitor = Mock(
        return_value=({"bmh_file": "/tmp/bmh.yaml", "machine_file": "/tmp/machine.yaml"}, 8)
    )

    return Mock(return_value=resource_manager)


@pytest.fixture
def mock_utility_functions():
    """Mock utility functions used by orchestrator"""
    return {
        "find_bmh_by_mac_address": Mock(return_value=None),
        "find_bmh_by_pattern": Mock(return_value={}),
        "find_machineset_for_machine": Mock(return_value={}),
        "annotate_machine_for_deletion": Mock(return_value=True),
        "scale_down_machineset": Mock(return_value=True),
        "cordon_node": Mock(return_value=True),
        "drain_node": Mock(return_value=True),
        "delete_machine": Mock(return_value=True),
        "delete_bmh": Mock(return_value=True),
        "verify_resources_deleted": Mock(return_value=True),
    }


@pytest.fixture
def mock_workflow_functions():
    """Mock workflow functions used by orchestrator"""
    return {
        "configure_replacement_node": Mock(return_value=True),
        "handle_successful_completion": Mock(),
        "create_new_node_configs": Mock(
            return_value={
                "bmh_file": "/tmp/new_bmh.yaml",
                "machine_file": "/tmp/new_machine.yaml",
                "secret_file": "/tmp/new_secret.yaml",
            }
        ),
        "handle_provisioning_failure": Mock(),
    }


@pytest.fixture
def mock_etcd_functions():
    """Mock ETCD functions used by orchestrator"""
    return {
        "handle_etcd_operations_for_replacement": Mock(return_value=("bad-node", 4)),
        "handle_etcd_operations_for_expansion": Mock(return_value=("bad-node", 4)),
        "re_enable_quorum_guard_after_expansion": Mock(return_value=9),
        "exec_pod_command": Mock(return_value=True),
        "determine_failed_control_node": Mock(return_value="failed-control-1"),
    }


@pytest.fixture
def orchestrator_dependencies(
    mock_printer,
    mock_execute_oc_command,
    mock_format_runtime,
    mock_backup_manager_class,
    mock_node_configurator_class,
    mock_resource_monitor_class,
    mock_resource_manager_class,
    mock_utility_functions,
    mock_workflow_functions,
    mock_etcd_functions,
):
    """Complete set of dependencies for NodeOperationOrchestrator"""
    return {
        "printer": mock_printer,
        "execute_oc_command": mock_execute_oc_command,
        "format_runtime": mock_format_runtime,
        "BackupManager": mock_backup_manager_class,
        "NodeConfigurator": mock_node_configurator_class,
        "ResourceMonitor": mock_resource_monitor_class,
        "ResourceManager": mock_resource_manager_class,
        **mock_utility_functions,
        **mock_workflow_functions,
        **mock_etcd_functions,
    }


@pytest.fixture
def orchestrator(orchestrator_dependencies):
    """NodeOperationOrchestrator instance with mocked dependencies"""
    return NodeOperationOrchestrator(**orchestrator_dependencies)


@pytest.fixture
def sample_args():
    """Sample command line arguments for testing"""
    return SimpleNamespace(
        replacement_node="new-control-1",
        replacement_node_ip="192.168.1.100",
        replacement_node_bmc_ip="192.168.2.100",
        replacement_node_mac_address="52:54:00:12:34:56",
        replacement_node_role="control-plane",
        sushy_uid="test-uid-123",
        backup_dir="/tmp/backup_test",
    )


@pytest.fixture
def sample_machines_data(machine_factory):
    """Sample machines data for testing using machine_factory.
    
    Uses the established machine_factory from conftest.py to generate 
    consistent Machine resources following enterprise factory patterns.
    Returns List structure expected by orchestrator mock commands.
    """
    test_machine = machine_factory(
        machine_name="test-master-0",
        cluster_name="test-cluster", 
        machine_role="master",
        include_cluster_labels=True,
        include_spec_metadata=True
    )
    
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [test_machine]
    }

class TestNodeOperationOrchestrator:
    """Test cases for NodeOperationOrchestrator class"""

    def test_initialization(self, orchestrator_dependencies):
        """Test orchestrator initialization with all dependencies"""
        orchestrator = NodeOperationOrchestrator(**orchestrator_dependencies)

        # Verify core dependencies are set
        assert orchestrator.printer == orchestrator_dependencies["printer"]
        assert orchestrator.execute_oc_command == orchestrator_dependencies["execute_oc_command"]
        assert orchestrator.format_runtime == orchestrator_dependencies["format_runtime"]

        # Verify class constructors are set
        assert orchestrator.BackupManager == orchestrator_dependencies["BackupManager"]
        assert orchestrator.NodeConfigurator == orchestrator_dependencies["NodeConfigurator"]
        assert orchestrator.ResourceMonitor == orchestrator_dependencies["ResourceMonitor"]

        # Verify utility functions are set
        assert orchestrator.find_bmh_by_mac_address == orchestrator_dependencies["find_bmh_by_mac_address"]
        assert orchestrator.cordon_node == orchestrator_dependencies["cordon_node"]
        assert orchestrator.drain_node == orchestrator_dependencies["drain_node"]


class TestOperationParameterSetup:
    """Test cases for _setup_operation_parameters method"""

    def test_setup_operation_parameters_replacement(self, orchestrator, sample_args):
        """Test setup for control plane replacement operation"""
        total_steps, operation_params = orchestrator._setup_operation_parameters(
            sample_args, is_addition=False, is_expansion=False
        )

        assert total_steps == 12  # Full replacement workflow
        assert operation_params["replacement_node"] == "new-control-1"
        assert operation_params["replacement_node_ip"] == "192.168.1.100"
        assert operation_params["replacement_node_bmc_ip"] == "192.168.2.100"
        assert operation_params["replacement_node_mac_address"] == "52:54:00:12:34:56"
        assert operation_params["replacement_node_role"] == "control-plane"
        assert operation_params["sushy_uid"] == "test-uid-123"

    def test_setup_operation_parameters_addition(self, orchestrator, sample_args):
        """Test setup for worker node addition operation"""
        total_steps, operation_params = orchestrator._setup_operation_parameters(
            sample_args, is_addition=True, is_expansion=False
        )

        assert total_steps == 6  # Worker addition: fewer steps
        assert operation_params["replacement_node"] == "new-control-1"

    def test_setup_operation_parameters_expansion(self, orchestrator, sample_args):
        """Test setup for control plane expansion operation"""
        total_steps, operation_params = orchestrator._setup_operation_parameters(
            sample_args, is_addition=False, is_expansion=True
        )

        assert total_steps == 9  # Control plane expansion steps
        assert operation_params["replacement_node"] == "new-control-1"


class TestMacConflictHandling:
    """Test cases for _handle_existing_mac_conflict method"""

    def test_handle_existing_mac_conflict_no_conflict(self, orchestrator):
        """Test when no existing node has the same MAC address"""
        orchestrator.find_bmh_by_mac_address.return_value = None

        total_steps = orchestrator._handle_existing_mac_conflict("52:54:00:12:34:56", 10)

        assert total_steps == 10  # No change in steps
        orchestrator.find_bmh_by_mac_address.assert_called_once()

    def test_handle_existing_mac_conflict_with_node(self, orchestrator):
        """Test when existing node has the same MAC address"""
        existing_bmh_info = {
            "node_name": "existing-node",
            "bmh_name": "existing-bmh",
            "machine_name": "existing-machine",
        }
        orchestrator.find_bmh_by_mac_address.return_value = existing_bmh_info

        total_steps = orchestrator._handle_existing_mac_conflict("52:54:00:12:34:56", 10)

        assert total_steps == 13  # Added 3 steps for cleanup
        orchestrator.cordon_node.assert_called_once_with("existing-node", printer=orchestrator.printer)
        orchestrator.drain_node.assert_called_once_with("existing-node", printer=orchestrator.printer)

    def test_handle_existing_mac_conflict_without_machine(self, orchestrator):
        """Test cleanup of existing node without associated machine"""
        existing_bmh_info = {
            "node_name": "existing-node",
            "bmh_name": "existing-bmh",
            "machine_name": None,  # No machine
        }
        orchestrator.find_bmh_by_mac_address.return_value = existing_bmh_info

        total_steps = orchestrator._handle_existing_mac_conflict("52:54:00:12:34:56", 10)

        assert total_steps == 13
        
        # Verify workflow sequence: cordon -> drain -> cleanup
        orchestrator.cordon_node.assert_called_once_with("existing-node", printer=orchestrator.printer)
        orchestrator.drain_node.assert_called_once_with("existing-node", printer=orchestrator.printer)
        
        # Verify cleanup operations were called for the case without machine
        orchestrator.delete_bmh.assert_called_once_with("existing-bmh", printer=orchestrator.printer)
        # Should NOT delete machine since machine_name is None
        orchestrator.delete_machine.assert_not_called()


class TestMachinesetScaling:
    """Test cases for _handle_machineset_scaling method"""

    def test_handle_machineset_scaling_success(self, orchestrator):
        """Test successful machineset scaling"""
        machineset_info = {"machineset_name": "test-machineset", "current_replicas": 3}
        orchestrator.find_machineset_for_machine.return_value = machineset_info

        orchestrator._handle_machineset_scaling("test-machine")

        orchestrator.annotate_machine_for_deletion.assert_called_once_with(
            "test-machine", printer=orchestrator.printer, execute_oc_command=orchestrator.execute_oc_command
        )
        orchestrator.scale_down_machineset.assert_called_once_with(
            "test-machineset", printer=orchestrator.printer, execute_oc_command=orchestrator.execute_oc_command
        )

    def test_handle_machineset_scaling_no_machineset(self, orchestrator):
        """Test when machine is not managed by any machineset"""
        orchestrator.find_machineset_for_machine.return_value = None

        orchestrator._handle_machineset_scaling("test-machine")

        # Verify method completes successfully and finds no machineset
        orchestrator.find_machineset_for_machine.assert_called_once_with(
            "test-machine", printer=orchestrator.printer
        )

    def test_handle_machineset_scaling_annotation_failure(self, orchestrator):
        """Test when annotation fails but scaling continues"""
        machineset_info = {"machineset_name": "test-machineset", "current_replicas": 3}
        orchestrator.find_machineset_for_machine.return_value = machineset_info
        orchestrator.annotate_machine_for_deletion.return_value = False

        orchestrator._handle_machineset_scaling("test-machine")

        orchestrator.scale_down_machineset.assert_called_once()


class TestResourceDeletion:
    """Test cases for _delete_existing_resources method"""

    def test_delete_existing_resources_success(self, orchestrator):
        """Test successful deletion of machine and BMH"""
        orchestrator._delete_existing_resources("test-machine", "test-bmh")

        orchestrator.delete_machine.assert_called_once_with("test-machine", printer=orchestrator.printer)
        orchestrator.delete_bmh.assert_called_once_with("test-bmh", printer=orchestrator.printer)
        orchestrator.verify_resources_deleted.assert_called_once_with(
            machine_name="test-machine", bmh_name="test-bmh", printer=orchestrator.printer
        )

    def test_delete_existing_resources_no_machine(self, orchestrator):
        """Test deletion when no machine exists"""
        orchestrator._delete_existing_resources(None, "test-bmh")

        orchestrator.delete_machine.assert_not_called()
        orchestrator.delete_bmh.assert_called_once_with("test-bmh", printer=orchestrator.printer)
        orchestrator.verify_resources_deleted.assert_called_once()

    def test_delete_existing_resources_failure(self, orchestrator):
        """Test when resource deletion fails"""
        orchestrator.delete_machine.return_value = False
        orchestrator.delete_bmh.return_value = False

        orchestrator._delete_existing_resources("test-machine", "test-bmh")

        # Verify deletion methods were called even though they failed
        orchestrator.delete_machine.assert_called_once_with("test-machine", printer=orchestrator.printer)
        orchestrator.delete_bmh.assert_called_once_with("test-bmh", printer=orchestrator.printer)
        orchestrator.verify_resources_deleted.assert_called_once_with(
            machine_name="test-machine", bmh_name="test-bmh", printer=orchestrator.printer
        )


class TestTemplateConfiguration:
    """Test cases for _get_template_configuration method"""

    def _create_mock_backup_manager(self, return_value):
        """Helper method to create mock backup manager with common setup"""
        backup_manager = Mock()
        backup_manager.backup_template_bmh.return_value = return_value
        return backup_manager

    def test_get_template_configuration_addition(self, orchestrator):
        """Test template configuration for worker addition"""
        backup_manager = self._create_mock_backup_manager(("/tmp/template.yaml", True))

        result = orchestrator._get_template_configuration(True, False, backup_manager)

        assert result[0] == "/tmp/template.yaml"  # template_backup_file
        assert result[1] is True  # is_worker_template
        assert result[2] is None  # failed_node
        backup_manager.backup_template_bmh.assert_called_once_with(failed_control_node=None)

    def test_get_template_configuration_expansion(self, orchestrator):
        """Test template configuration for control plane expansion"""
        backup_manager = self._create_mock_backup_manager(("/tmp/template.yaml", False))

        result = orchestrator._get_template_configuration(False, True, backup_manager)

        assert result[0] == "/tmp/template.yaml"
        assert result[1] is False  # Not worker template
        assert result[2] is None  # No failed node
        backup_manager.backup_template_bmh.assert_called_once_with(
            failed_control_node=None, is_control_plane_expansion=True
        )

    def test_get_template_configuration_replacement(self, orchestrator):
        """Test template configuration for control plane replacement"""
        backup_manager = self._create_mock_backup_manager(("/tmp/template.yaml", False))
        orchestrator.determine_failed_control_node.return_value = "failed-control-1"

        result = orchestrator._get_template_configuration(False, False, backup_manager)

        assert result[0] == "/tmp/template.yaml"
        assert result[1] is False
        assert result[2] == "failed-control-1"
        backup_manager.backup_template_bmh.assert_called_once_with(failed_control_node="failed-control-1")

    def test_get_template_configuration_no_failed_node(self, orchestrator):
        """Test when no failed control node can be determined"""
        backup_manager = self._create_mock_backup_manager(("/tmp/template.yaml", False))
        orchestrator.determine_failed_control_node.return_value = None

        with patch.object(orchestrator, "_exit_with_runtime") as mock_exit:
            orchestrator._get_template_configuration(False, False, backup_manager)

            mock_exit.assert_called_once()
            # Verify error handling for missing failed node

    def test_get_template_configuration_backup_failure(self, orchestrator):
        """Test when template backup fails"""
        backup_manager = self._create_mock_backup_manager((None, None))  # Backup failed

        with patch.object(orchestrator, "_exit_with_runtime") as mock_exit:
            orchestrator._get_template_configuration(True, False, backup_manager)

            mock_exit.assert_called_once()
            # Verify error handling for backup failure


class TestEtcdOperations:
    """Test cases for _handle_etcd_operations_step method"""

    def test_handle_etcd_operations_addition(self, orchestrator, sample_args):
        """Test ETCD operations for worker addition (should skip)"""
        bad_node, current_step = orchestrator._handle_etcd_operations_step(
            True, False, sample_args, None, time.time(), 3, 10
        )

        assert bad_node is None
        assert current_step == 4

    def test_handle_etcd_operations_expansion(self, orchestrator, sample_args):
        """Test ETCD operations for control plane expansion"""
        orchestrator.handle_etcd_operations_for_expansion.return_value = ("bad-node", 4)

        bad_node, current_step = orchestrator._handle_etcd_operations_step(
            False, True, sample_args, None, time.time(), 3, 10
        )

        assert bad_node == "bad-node"
        assert current_step == 4
        orchestrator.handle_etcd_operations_for_expansion.assert_called_once()

    def test_handle_etcd_operations_replacement(self, orchestrator, sample_args):
        """Test ETCD operations for control plane replacement"""
        orchestrator.handle_etcd_operations_for_replacement.return_value = ("bad-node", 4)

        bad_node, current_step = orchestrator._handle_etcd_operations_step(
            False, False, sample_args, "failed-control-1", time.time(), 3, 10
        )

        assert bad_node == "bad-node"
        assert current_step == 4
        orchestrator.handle_etcd_operations_for_replacement.assert_called_once()


class TestConfigurationFiles:
    """Test cases for _create_configuration_files method"""

    def _create_mock_backup_manager_for_config(self, return_value=None):
        """Helper method to create mock backup manager for configuration tests"""
        backup_manager = Mock()
        if return_value:
            backup_manager.copy_files_for_replacement.return_value = return_value
        return backup_manager

    def test_create_configuration_files_addition(self, orchestrator):
        """Test creating configuration files for worker addition"""
        backup_manager = self._create_mock_backup_manager_for_config()
        operation_params = {"replacement_node": "new-worker-1"}

        result = orchestrator._create_configuration_files(
            True, False, backup_manager, "/tmp/backup", "/tmp/template.yaml", True, operation_params
        )

        assert result is not None
        orchestrator.create_new_node_configs.assert_called_once()

    def test_create_configuration_files_replacement(self, orchestrator):
        """Test creating configuration files for control plane replacement"""
        backup_manager = self._create_mock_backup_manager_for_config(
            {"bmh_file": "/tmp/bmh.yaml", "machine_file": "/tmp/machine.yaml"}
        )
        operation_params = {"replacement_node": "new-control-1"}

        result = orchestrator._create_configuration_files(
            False,
            False,
            backup_manager,
            "/tmp/backup",
            "/tmp/template.yaml",
            False,
            operation_params,
            "failed-control-1",
        )

        assert result is not None
        # Should call create_new_node_configs instead of copy_files_for_replacement
        orchestrator.create_new_node_configs.assert_called_once()

    def test_create_configuration_files_no_failed_node(self, orchestrator):
        """Test when failed node is not provided for replacement"""
        backup_manager = self._create_mock_backup_manager_for_config()
        operation_params = {"replacement_node": "new-control-1"}

        result = orchestrator._create_configuration_files(
            False,
            False,
            backup_manager,
            "/tmp/backup",
            "/tmp/template.yaml",
            False,
            operation_params,
            None,  # No failed node
        )

        # Now returns configuration files even without failed node
        assert result is not None
        orchestrator.create_new_node_configs.assert_called_once()


class TestStepDescriptions:
    """Test cases for _get_step_description method"""

    def _assert_step_description(self, orchestrator, operation_type, step_name, expected_desc):
        """Helper method to test step descriptions"""
        desc = orchestrator._get_step_description(operation_type, step_name)
        assert desc == expected_desc

    def test_get_step_description_replacement(self, orchestrator):
        """Test step descriptions for replacement operation"""
        self._assert_step_description(orchestrator, "replacement", "configure_node", "Configuring replacement node")
        self._assert_step_description(
            orchestrator, "replacement", "apply_resources", "Applying resources and monitoring replacement"
        )

    def test_get_step_description_addition(self, orchestrator):
        """Test step descriptions for addition operation"""
        self._assert_step_description(orchestrator, "addition", "configure_node", "Configuring new worker node")
        self._assert_step_description(
            orchestrator, "addition", "apply_resources", "Applying resources and monitoring worker addition"
        )

    def test_get_step_description_expansion(self, orchestrator):
        """Test step descriptions for expansion operation"""
        self._assert_step_description(orchestrator, "expansion", "configure_node", "Configuring new control plane node")
        self._assert_step_description(
            orchestrator, "expansion", "apply_resources", "Applying resources and monitoring control plane expansion"
        )

    def test_get_step_description_unknown(self, orchestrator):
        """Test step description for unknown step"""
        self._assert_step_description(orchestrator, "unknown", "unknown_step", "Processing unknown_step")


class TestMainOrchestration:
    """Test cases for process_node_operation method"""

    @patch("time.time", return_value=1000.0)
    def test_process_node_operation_worker_addition(self, mock_time, orchestrator, sample_args):
        """Test complete worker addition workflow"""
        orchestrator.process_node_operation(sample_args, is_addition=True, is_expansion=False)

        # Verify key method calls
        orchestrator.BackupManager.assert_called_once()
        orchestrator.configure_replacement_node.assert_called_once()
        orchestrator.handle_successful_completion.assert_called_once()

    @patch("time.time", return_value=1000.0)
    def test_process_node_operation_control_plane_expansion(self, mock_time, orchestrator, sample_args):
        """Test complete control plane expansion workflow"""
        orchestrator.process_node_operation(sample_args, is_addition=False, is_expansion=True)

        # Verify ETCD operations for expansion are called
        orchestrator.handle_etcd_operations_for_expansion.assert_called_once()

        # Verify quorum guard re-enablement
        orchestrator.re_enable_quorum_guard_after_expansion.assert_called_once()

        orchestrator.handle_successful_completion.assert_called_once()

    @patch("time.time", return_value=1000.0)
    def test_process_node_operation_control_plane_replacement(self, mock_time, orchestrator, sample_args):
        """Test complete control plane replacement workflow"""
        orchestrator.process_node_operation(sample_args, is_addition=False, is_expansion=False)

        # Verify ETCD operations for replacement are called
        orchestrator.handle_etcd_operations_for_replacement.assert_called_once()

        # Verify no quorum guard re-enablement (only for expansion)
        orchestrator.re_enable_quorum_guard_after_expansion.assert_not_called()

        orchestrator.handle_successful_completion.assert_called_once()

    @patch("time.time", return_value=1000.0)
    def test_process_node_operation_template_failure(self, mock_time, orchestrator, sample_args):
        """Test when template backup fails"""
        backup_manager = Mock()
        backup_manager.setup_backup_directory.return_value = "/tmp/backup"
        backup_manager.backup_template_bmh.return_value = (None, None)  # Failure
        orchestrator.BackupManager.return_value = backup_manager

        with patch.object(orchestrator, "_exit_with_runtime") as mock_exit:
            orchestrator.process_node_operation(sample_args, is_addition=True, is_expansion=False)

            # Should exit due to template failure
            mock_exit.assert_called_once()

    @patch("time.time", return_value=1000.0)
    def test_process_node_operation_etcd_failure(self, mock_time, orchestrator, sample_args):
        """Test when ETCD operations fail"""
        orchestrator.handle_etcd_operations_for_replacement.return_value = (None, 4)  # Failure

        # Should return early due to ETCD failure
        orchestrator.process_node_operation(sample_args, is_addition=False, is_expansion=False)

        # Should not reach completion
        orchestrator.handle_successful_completion.assert_not_called()


class TestUtilityFunctions:
    """Test cases for utility functions"""

    @patch("time.time", return_value=1300.0)
    def test_exit_with_runtime(self, mock_time, orchestrator):
        """Test _exit_with_runtime method"""
        start_time = 1000.0
        orchestrator.format_runtime.return_value = "2m 15s"

        orchestrator._exit_with_runtime(start_time)

        orchestrator.format_runtime.assert_called_once_with(start_time, 1300.0)


# =============================================================================
# Tests for Standalone Functions
# =============================================================================


class TestStandaloneFunctions:
    """Test cases for standalone functions in orchestrator module"""

    def test_handle_successful_completion_addition(self, mock_printer, mock_format_runtime):
        """Test successful completion handler for worker addition"""
        handle_successful_completion(
            "new-worker-1", 1000.0, True, printer=mock_printer, format_runtime=mock_format_runtime
        )

        # Verify completion was called with correct parameters

    def test_handle_successful_completion_control_plane(self, mock_printer, mock_format_runtime):
        """Test successful completion handler for control plane operations"""
        handle_successful_completion(
            "new-control-1", 1000.0, False, printer=mock_printer, format_runtime=mock_format_runtime
        )

        # Verify completion was called with correct parameters

    @patch("time.time", return_value=1300.0)
    def test_handle_provisioning_failure(self, mock_time, mock_printer, mock_format_runtime):
        """Test provisioning failure handler"""
        handle_provisioning_failure("Network error occurred", mock_format_runtime, 1000.0, printer=mock_printer)

        # Verify provisioning failure was called with correct error message
        mock_format_runtime.assert_called_once_with(1000.0, 1300.0)


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests that verify end-to-end workflows"""

    @patch("time.time", side_effect=[1000.0, 1100.0, 1200.0, 1300.0])
    def test_full_worker_addition_workflow(self, mock_time, orchestrator, sample_args):
        """Test complete end-to-end worker addition workflow"""
        # Set up environment
        os.environ["KUBECONFIG"] = KUBECONFIG_PATH

        # Execute the full workflow
        orchestrator.process_node_operation(sample_args, is_addition=True, is_expansion=False)

        # Verify the workflow completed all major steps
        orchestrator.BackupManager.assert_called_once()
        orchestrator.configure_replacement_node.assert_called_once()
        orchestrator.handle_successful_completion.assert_called_once()

    @patch("time.time", side_effect=[1000.0, 1100.0, 1200.0, 1300.0, 1400.0])
    def test_full_expansion_workflow_with_quorum_guard(self, mock_time, orchestrator, sample_args):
        """Test complete control plane expansion including quorum guard operations"""
        # Set up environment
        os.environ["KUBECONFIG"] = KUBECONFIG_PATH

        # Execute the expansion workflow
        orchestrator.process_node_operation(sample_args, is_addition=False, is_expansion=True)

        # Verify expansion-specific operations
        orchestrator.handle_etcd_operations_for_expansion.assert_called_once()
        orchestrator.re_enable_quorum_guard_after_expansion.assert_called_once()

        # Verify completion
        orchestrator.handle_successful_completion.assert_called_once_with(
            "new-control-1", 1000.0, False, printer=orchestrator.printer, format_runtime=orchestrator.format_runtime
        )

    @patch("time.time", side_effect=[1000.0, 1100.0, 1200.0, 1300.0, 1400.0, 1500.0])
    def test_full_replacement_workflow_with_cleanup(self, mock_time, orchestrator, sample_args):
        """Test complete control plane replacement with existing node cleanup"""
        # Set up environment
        os.environ["KUBECONFIG"] = KUBECONFIG_PATH

        # Set up existing node conflict
        existing_bmh_info = {
            "node_name": "existing-control-1",
            "bmh_name": "existing-control-1-bmh",
            "machine_name": "existing-control-1-machine",
        }
        orchestrator.find_bmh_by_mac_address.return_value = existing_bmh_info

        # Execute the replacement workflow
        orchestrator.process_node_operation(sample_args, is_addition=False, is_expansion=False)

        # Verify cleanup operations were performed
        orchestrator.cordon_node.assert_called_once_with("existing-control-1", printer=orchestrator.printer)
        orchestrator.drain_node.assert_called_once_with("existing-control-1", printer=orchestrator.printer)

        # Verify replacement-specific operations
        orchestrator.handle_etcd_operations_for_replacement.assert_called_once()

        # Verify completion
        orchestrator.handle_successful_completion.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
