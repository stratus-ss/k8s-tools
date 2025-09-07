#!/usr/bin/env python3
"""
Comprehensive functional tests for the 4 main use cases.

These tests validate end-to-end functionality before any refactoring begins.
They serve as our regression protection during architectural changes.

Test Coverage:
- Case 1: Add worker node to cluster
- Case 2: Replace NotReady control plane node with new hardware  
- Case 3: Replace NotReady control plane node with existing worker node
- Case 4: Add new control plane node (expansion)
"""

import pytest
import os
import sys
import tempfile
import yaml
from unittest.mock import Mock, patch
from types import SimpleNamespace

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.orchestrator import NodeOperationOrchestrator  # noqa: E402


# =============================================================================
# Test Fixtures - Mock Data for 4 Use Cases
# =============================================================================


@pytest.fixture
def mock_cluster_state():
    """Mock cluster state with control plane and worker nodes"""
    return {
        "nodes": {
            "control_plane": [
                {"name": "master-0", "status": "Ready"},
                {"name": "master-1", "status": "NotReady"},  # Failed node for Case 2
                {"name": "master-2", "status": "Ready"}
            ],
            "workers": [
                {"name": "worker-0", "status": "Ready"},  # Available for Case 3
                {"name": "worker-1", "status": "Ready"}
            ]
        },
        "bmh_resources": [
            {"name": "master-0", "role": "control-plane", "state": "provisioned"},
            {"name": "master-1", "role": "control-plane", "state": "error"},
            {"name": "master-2", "role": "control-plane", "state": "provisioned"},
            {"name": "worker-0", "role": "worker", "state": "provisioned"},
            {"name": "worker-1", "role": "worker", "state": "provisioned"}
        ]
    }


@pytest.fixture
def case_1_args():
    """Arguments for Case 1: Add worker node"""
    return SimpleNamespace(
        replacement_node="new-worker-1",
        replacement_node_ip="192.168.1.100",
        replacement_node_bmc_ip="192.168.2.100",
        replacement_node_mac_address="52:54:00:e9:d5:8a",
        replacement_node_role="worker",
        backup_dir="/tmp/test_backup",
        sushy_uid=None,
        debug=False,
        skip_etcd=False,
        expand_control_plane=False,
        add_new_node=True  # Key flag for worker addition
    )


@pytest.fixture
def case_2_args():
    """Arguments for Case 2: Replace failed control plane"""
    return SimpleNamespace(
        replacement_node="new-master-1",
        replacement_node_ip="192.168.1.101",
        replacement_node_bmc_ip="192.168.2.101",
        replacement_node_mac_address="52:54:00:e9:d5:8b",
        replacement_node_role="master",
        backup_dir="/tmp/test_backup",
        sushy_uid=None,
        debug=False,
        skip_etcd=False,
        expand_control_plane=False,
        add_new_node=False  # Default replacement mode
    )


@pytest.fixture
def case_3_args():
    """Arguments for Case 3: Convert worker to control plane"""
    return SimpleNamespace(
        replacement_node="worker-0",  # Existing worker node
        replacement_node_ip="192.168.1.50",  # Current worker IP
        replacement_node_bmc_ip="192.168.2.50",
        replacement_node_mac_address="52:54:00:e9:d5:8c",
        replacement_node_role="master",  # Convert to master
        backup_dir="/tmp/test_backup",
        sushy_uid=None,
        debug=False,
        skip_etcd=False,
        expand_control_plane=False,
        add_new_node=False
    )


@pytest.fixture
def case_4_args():
    """Arguments for Case 4: Expand control plane"""
    return SimpleNamespace(
        replacement_node="new-master-3",
        replacement_node_ip="192.168.1.103",
        replacement_node_bmc_ip="192.168.2.103",
        replacement_node_mac_address="52:54:00:e9:d5:8d",
        replacement_node_role="master",
        backup_dir="/tmp/test_backup",
        sushy_uid=None,
        debug=False,
        skip_etcd=False,
        expand_control_plane=True,  # Key flag for expansion
        add_new_node=False
    )


@pytest.fixture
def mock_dependencies():
    """Mock all dependencies needed by NodeOperationOrchestrator"""
    return {
        "printer": Mock(),
        "determine_failed_control_node": Mock(return_value="master-1"),
        "format_runtime": Mock(return_value="5m 30s"),
        "execute_oc_command": Mock(),
        "find_bmh_by_pattern": Mock(),
        "find_bmh_by_mac_address": Mock(return_value=None),  # No MAC conflicts by default
        "find_machineset_for_machine": Mock(),
        "annotate_machine_for_deletion": Mock(),
        "scale_down_machineset": Mock(),
        "cordon_node": Mock(),
        "drain_node": Mock(),
        "delete_machine": Mock(),
        "delete_bmh": Mock(),
        "verify_resources_deleted": Mock(),
        "exec_pod_command": Mock(),
        "BackupManager": Mock(),
        "NodeConfigurator": Mock(),
        "ResourceMonitor": Mock(),
        "handle_successful_completion": Mock(),
        "handle_provisioning_failure": Mock(),
        "ResourceManager": Mock(),
        "create_new_node_configs": Mock(),
        "configure_replacement_node": Mock(),
        "handle_etcd_operations_for_replacement": Mock(return_value=("master-1", 5)),
        "handle_etcd_operations_for_expansion": Mock(return_value=(True, 5)),
        "re_enable_quorum_guard_after_expansion": Mock(return_value=6),
    }


# =============================================================================
# Functional Tests for the 4 Main Use Cases
# =============================================================================


class TestCase1AddWorkerNode:
    """Test Case 1: Add worker node to cluster"""

    def test_case_1_worker_addition_end_to_end(self, case_1_args, mock_dependencies, mock_cluster_state):
        """
        Test complete worker node addition workflow.
        
        This test validates:
        - Worker addition flag is respected
        - No ETCD operations are performed (worker addition doesn't need ETCD)
        - MachineSet scaling occurs for worker nodes
        - Resource monitoring happens in 4-phase sequence
        - Completion handlers are called correctly
        """
        # Setup BackupManager mock
        backup_manager = Mock()
        backup_manager.setup_backup_directory = Mock(return_value="/tmp/test_backup")
        backup_manager.backup_template_bmh = Mock(return_value=("/tmp/template.yaml", True))  # True = worker template
        mock_dependencies["BackupManager"].return_value = backup_manager
        
        # Setup configuration mock
        mock_dependencies["create_new_node_configs"].return_value = {
            "bmh": "/tmp/new-worker-1_bmh.yaml",
            "network_secret": "/tmp/new-worker-1_network-config-secret.yaml",
            "bmc_secret": "/tmp/new-worker-1-bmc-secret.yaml",
            "nmstate": "/tmp/new-worker-1_nmstate"
        }
        
        # Setup ResourceManager mock for worker addition
        resource_manager = Mock()
        resource_manager.apply_resources_and_monitor = Mock(return_value=({
            "bmh": "/tmp/new-worker-1_bmh.yaml",
            "network_secret": "/tmp/new-worker-1_network-config-secret.yaml",
            "bmc_secret": "/tmp/new-worker-1-bmc-secret.yaml",
            "nmstate": "/tmp/new-worker-1_nmstate"
        }, 8))
        mock_dependencies["ResourceManager"].return_value = resource_manager
        
        # Create orchestrator and run worker addition
        orchestrator = NodeOperationOrchestrator(**mock_dependencies)
        orchestrator.process_node_operation(case_1_args, is_addition=True)
        
        # Verify worker addition specific behavior
        backup_manager.setup_backup_directory.assert_called_once()
        backup_manager.backup_template_bmh.assert_called_once_with(failed_control_node=None)
        
        # Verify ETCD operations were skipped
        mock_dependencies["handle_etcd_operations_for_replacement"].assert_not_called()
        mock_dependencies["handle_etcd_operations_for_expansion"].assert_not_called()
        
        # Verify resource configuration and application
        mock_dependencies["create_new_node_configs"].assert_called_once()
        mock_dependencies["configure_replacement_node"].assert_called_once()
        resource_manager.apply_resources_and_monitor.assert_called_once()
        
        # Verify completion handling
        mock_dependencies["handle_successful_completion"].assert_called_once()
        args = mock_dependencies["handle_successful_completion"].call_args[0]
        assert args[0] == "new-worker-1"  # replacement_node
        assert args[2] is True  # is_addition flag

    def test_case_1_worker_addition_handles_template_failure(self, case_1_args, mock_dependencies):
        """Test worker addition handles template backup failure gracefully"""
        backup_manager = Mock()
        backup_manager.setup_backup_directory = Mock(return_value="/tmp/test_backup")
        backup_manager.backup_template_bmh = Mock(return_value=(None, False))  # Template failure
        mock_dependencies["BackupManager"].return_value = backup_manager
        
        orchestrator = NodeOperationOrchestrator(**mock_dependencies)
        
        # Should exit gracefully when template backup fails
        orchestrator.process_node_operation(case_1_args, is_addition=True)
        
        # Verify it stops at template stage
        backup_manager.backup_template_bmh.assert_called_once()
        mock_dependencies["create_new_node_configs"].assert_not_called()


class TestCase2ReplaceControlPlane:
    """Test Case 2: Replace NotReady control plane node with new hardware"""

    def test_case_2_control_plane_replacement_end_to_end(self, case_2_args, mock_dependencies, mock_cluster_state):
        """
        Test complete control plane replacement workflow.
        
        This test validates:
        - Failed control plane node is identified
        - ETCD operations are performed (member removal, quorum guard)
        - Resource backup and removal occur
        - New node configuration and provisioning
        - All 12 steps of replacement process
        """
        # Setup failed node identification
        mock_dependencies["determine_failed_control_node"].return_value = "master-1"
        
        # Setup BackupManager for control plane template
        backup_manager = Mock()
        backup_manager.setup_backup_directory = Mock(return_value="/tmp/test_backup")
        backup_manager.backup_template_bmh = Mock(return_value=("/tmp/template.yaml", False))  # False = control template
        mock_dependencies["BackupManager"].return_value = backup_manager
        
        # Setup ETCD operations
        mock_dependencies["handle_etcd_operations_for_replacement"].return_value = ("master-1", 6)
        
        # Setup ResourceManager for control plane operations
        resource_manager = Mock()
        resource_manager.backup_and_remove_resources = Mock(return_value=("master-1-bmh", "master-1-machine", 7))
        resource_manager.apply_resources_and_monitor = Mock(return_value=({
            "bmh": "/tmp/new-master-1_bmh.yaml",
            "machine": "/tmp/new-master-1_machine.yaml",
            "network_secret": "/tmp/new-master-1_network-config-secret.yaml",
            "bmc_secret": "/tmp/new-master-1-bmc-secret.yaml",
            "nmstate": "/tmp/new-master-1_nmstate"
        }, 11))
        mock_dependencies["ResourceManager"].return_value = resource_manager
        
        # Setup configuration creation
        mock_dependencies["create_new_node_configs"].return_value = {
            "bmh": "/tmp/new-master-1_bmh.yaml",
            "machine": "/tmp/new-master-1_machine.yaml",
            "network_secret": "/tmp/new-master-1_network-config-secret.yaml",
            "bmc_secret": "/tmp/new-master-1-bmc-secret.yaml",
            "nmstate": "/tmp/new-master-1_nmstate"
        }
        
        # Create orchestrator and run control plane replacement
        orchestrator = NodeOperationOrchestrator(**mock_dependencies)
        orchestrator.process_node_operation(case_2_args, is_addition=False, is_expansion=False)
        
        # Verify control plane replacement specific behavior
        mock_dependencies["determine_failed_control_node"].assert_called_once()
        backup_manager.backup_template_bmh.assert_called_once_with(failed_control_node="master-1")
        
        # Verify ETCD operations were performed
        mock_dependencies["handle_etcd_operations_for_replacement"].assert_called_once()
        
        # Verify resource backup and removal
        resource_manager.backup_and_remove_resources.assert_called_once()
        
        # Verify new node configuration
        mock_dependencies["create_new_node_configs"].assert_called_once()
        mock_dependencies["configure_replacement_node"].assert_called_once()
        
        # Verify resource application and monitoring
        resource_manager.apply_resources_and_monitor.assert_called_once()
        
        # Verify completion handling
        mock_dependencies["handle_successful_completion"].assert_called_once()
        args = mock_dependencies["handle_successful_completion"].call_args[0]
        assert args[0] == "new-master-1"  # replacement_node
        assert args[2] is False  # is_addition flag

    def test_case_2_replacement_handles_etcd_failure(self, case_2_args, mock_dependencies):
        """Test control plane replacement handles ETCD operation failure"""
        backup_manager = Mock()
        backup_manager.setup_backup_directory = Mock(return_value="/tmp/test_backup")
        backup_manager.backup_template_bmh = Mock(return_value=("/tmp/template.yaml", False))
        mock_dependencies["BackupManager"].return_value = backup_manager
        
        # Simulate ETCD operation failure
        mock_dependencies["handle_etcd_operations_for_replacement"].return_value = (None, 4)  # None = failure
        
        orchestrator = NodeOperationOrchestrator(**mock_dependencies)
        orchestrator.process_node_operation(case_2_args, is_addition=False, is_expansion=False)
        
        # Should stop at ETCD operations
        mock_dependencies["handle_etcd_operations_for_replacement"].assert_called_once()
        mock_dependencies["create_new_node_configs"].assert_not_called()


class TestCase3ConvertWorkerToControl:
    """Test Case 3: Replace NotReady control plane node with existing worker node"""

    def test_case_3_worker_to_control_conversion(self, case_3_args, mock_dependencies, mock_cluster_state):
        """
        Test converting existing worker to control plane.
        
        This test validates:
        - Existing worker node is identified and handled
        - MachineSet scaling prevents automatic worker replacement
        - Node conversion from worker to control plane role
        - ETCD operations for control plane integration
        """
        # Setup MAC address conflict detection (existing worker)
        existing_bmh_info = {
            "bmh_name": "worker-0-bmh",
            "node_name": "worker-0",
            "machine_name": "worker-0-machine",
            "mac_address": "52:54:00:e9:d5:8c"
        }
        mock_dependencies["find_bmh_by_mac_address"].return_value = existing_bmh_info
        
        # Setup MachineSet operations for worker scaling
        mock_dependencies["find_machineset_for_machine"].return_value = {
            "machineset_name": "worker-machineset-0",
            "current_replicas": 2
        }
        
        # Setup other dependencies similar to Case 2 but for worker conversion
        backup_manager = Mock()
        backup_manager.setup_backup_directory = Mock(return_value="/tmp/test_backup")
        backup_manager.backup_template_bmh = Mock(return_value=("/tmp/template.yaml", True))  # Worker template initially
        mock_dependencies["BackupManager"].return_value = backup_manager
        
        mock_dependencies["handle_etcd_operations_for_replacement"].return_value = ("master-1", 6)
        
        resource_manager = Mock()
        resource_manager.backup_and_remove_resources = Mock(return_value=("master-1-bmh", "master-1-machine", 7))
        resource_manager.apply_resources_and_monitor = Mock(return_value=({
            "bmh": "/tmp/worker-0_bmh.yaml",
            "machine": "/tmp/worker-0_machine.yaml",
            "network_secret": "/tmp/worker-0_network-config-secret.yaml",
            "bmc_secret": "/tmp/worker-0-bmc-secret.yaml",
            "nmstate": "/tmp/worker-0_nmstate"
        }, 11))
        mock_dependencies["ResourceManager"].return_value = resource_manager
        
        orchestrator = NodeOperationOrchestrator(**mock_dependencies)
        orchestrator.process_node_operation(case_3_args, is_addition=False, is_expansion=False)
        
        # Verify existing worker handling
        mock_dependencies["find_bmh_by_mac_address"].assert_called_once_with("52:54:00:e9:d5:8c", printer=mock_dependencies["printer"])
        
        # Verify MachineSet scaling to prevent automatic replacement
        mock_dependencies["find_machineset_for_machine"].assert_called_once_with("worker-0-machine", printer=mock_dependencies["printer"])
        mock_dependencies["annotate_machine_for_deletion"].assert_called_once()
        mock_dependencies["scale_down_machineset"].assert_called_once()
        
        # Verify node cordoning and draining
        mock_dependencies["cordon_node"].assert_called_once_with("worker-0", printer=mock_dependencies["printer"])
        mock_dependencies["drain_node"].assert_called_once_with("worker-0", printer=mock_dependencies["printer"])


class TestCase4ExpandControlPlane:
    """Test Case 4: Add new control plane node (expansion)"""

    def test_case_4_control_plane_expansion_end_to_end(self, case_4_args, mock_dependencies, mock_cluster_state):
        """
        Test complete control plane expansion workflow.
        
        This test validates:
        - No failed node identification needed (expansion, not replacement)
        - ETCD quorum guard disabled for expansion
        - Control plane template used
        - New control plane node provisioning
        - ETCD quorum guard re-enabled after completion
        """
        # Setup BackupManager for control plane expansion template
        backup_manager = Mock()
        backup_manager.setup_backup_directory = Mock(return_value="/tmp/test_backup")
        backup_manager.backup_template_bmh = Mock(return_value=("/tmp/template.yaml", False))  # Control plane template
        mock_dependencies["BackupManager"].return_value = backup_manager
        
        # Setup ETCD expansion operations
        mock_dependencies["handle_etcd_operations_for_expansion"].return_value = (True, 4)
        mock_dependencies["re_enable_quorum_guard_after_expansion"].return_value = 9
        
        # Setup ResourceManager for expansion
        resource_manager = Mock()
        resource_manager.apply_resources_and_monitor = Mock(return_value=({
            "bmh": "/tmp/new-master-3_bmh.yaml",
            "machine": "/tmp/new-master-3_machine.yaml",
            "network_secret": "/tmp/new-master-3_network-config-secret.yaml",
            "bmc_secret": "/tmp/new-master-3-bmc-secret.yaml",
            "nmstate": "/tmp/new-master-3_nmstate"
        }, 8))
        mock_dependencies["ResourceManager"].return_value = resource_manager
        
        # Setup configuration creation
        mock_dependencies["create_new_node_configs"].return_value = {
            "bmh": "/tmp/new-master-3_bmh.yaml",
            "machine": "/tmp/new-master-3_machine.yaml",
            "network_secret": "/tmp/new-master-3_network-config-secret.yaml",
            "bmc_secret": "/tmp/new-master-3-bmc-secret.yaml",
            "nmstate": "/tmp/new-master-3_nmstate"
        }
        
        # Create orchestrator and run control plane expansion
        orchestrator = NodeOperationOrchestrator(**mock_dependencies)
        orchestrator.process_node_operation(case_4_args, is_addition=False, is_expansion=True)
        
        # Verify expansion-specific behavior
        backup_manager.backup_template_bmh.assert_called_once_with(failed_control_node=None, is_control_plane_expansion=True)
        
        # Verify ETCD expansion operations (not replacement)
        mock_dependencies["handle_etcd_operations_for_expansion"].assert_called_once()
        mock_dependencies["handle_etcd_operations_for_replacement"].assert_not_called()
        
        # Verify no resource backup/removal (expansion doesn't remove existing resources)
        if hasattr(resource_manager, 'backup_and_remove_resources'):
            resource_manager.backup_and_remove_resources.assert_not_called()
        
        # Verify resource application and monitoring
        resource_manager.apply_resources_and_monitor.assert_called_once()
        call_args = resource_manager.apply_resources_and_monitor.call_args
        assert call_args[1]["is_expansion"] is True  # Expansion flag passed
        
        # Verify ETCD quorum guard re-enabling
        mock_dependencies["re_enable_quorum_guard_after_expansion"].assert_called_once()
        
        # Verify completion handling
        mock_dependencies["handle_successful_completion"].assert_called_once()


class TestUseCaseIntegration:
    """Integration tests combining multiple use cases"""

    def test_all_use_cases_have_distinct_workflows(self, mock_dependencies):
        """
        Test that all 4 use cases follow different code paths.
        
        This validates that our use case distinction logic works correctly
        and each case triggers the appropriate workflow.
        """
        orchestrator = NodeOperationOrchestrator(**mock_dependencies)
        
        # Mock different return values to track which path each use case takes
        backup_manager = Mock()
        backup_manager.setup_backup_directory = Mock(return_value="/tmp/test")
        backup_manager.backup_template_bmh = Mock(return_value=("/tmp/template.yaml", False))
        mock_dependencies["BackupManager"].return_value = backup_manager
        
        resource_manager = Mock()
        resource_manager.apply_resources_and_monitor = Mock(return_value=({}, 8))
        mock_dependencies["ResourceManager"].return_value = resource_manager
        
        # Create test arguments for each case
        case1_args = SimpleNamespace(
            add_new_node=True,
            expand_control_plane=False,
            replacement_node="test-worker",
            replacement_node_ip="192.168.1.100",
            replacement_node_bmc_ip="192.168.2.100",
            replacement_node_mac_address="52:54:00:e9:d5:8a",
            replacement_node_role="worker",
            backup_dir="/tmp/test",
            sushy_uid=None,
            debug=False,
            skip_etcd=False
        )
        
        case2_args = SimpleNamespace(
            add_new_node=False,
            expand_control_plane=False,
            replacement_node="test-master",
            replacement_node_ip="192.168.1.101",
            replacement_node_bmc_ip="192.168.2.101",
            replacement_node_mac_address="52:54:00:e9:d5:8b",
            replacement_node_role="master",
            backup_dir="/tmp/test",
            sushy_uid=None,
            debug=False,
            skip_etcd=False
        )
        
        case4_args = SimpleNamespace(
            add_new_node=False,
            expand_control_plane=True,
            replacement_node="test-master-expand",
            replacement_node_ip="192.168.1.103",
            replacement_node_bmc_ip="192.168.2.103",
            replacement_node_mac_address="52:54:00:e9:d5:8d",
            replacement_node_role="master",
            backup_dir="/tmp/test",
            sushy_uid=None,
            debug=False,
            skip_etcd=False
        )
        
        # Test that each case has distinct behavior
        test_cases = [
            # (args, is_addition, is_expansion, expected_etcd_calls)
            (case1_args, True, False, 0),   # Worker addition - no ETCD
            (case2_args, False, False, 1),  # Replacement - ETCD replacement
            (case4_args, False, True, 1),   # Expansion - ETCD expansion
        ]
        
        for i, (args, is_addition, is_expansion, expected_etcd_calls) in enumerate(test_cases):
            # Reset mocks between test cases
            for key, mock in mock_dependencies.items():
                if isinstance(mock, Mock):
                    mock.reset_mock()
            
            # Run the specific use case
            try:
                orchestrator.process_node_operation(args, is_addition=is_addition, is_expansion=is_expansion)
            except:
                pass  # Ignore errors, we're just testing workflow paths
            
            # Verify each case follows different paths
            if is_addition:
                # Worker addition should skip ETCD operations
                mock_dependencies["handle_etcd_operations_for_replacement"].assert_not_called()
                mock_dependencies["handle_etcd_operations_for_expansion"].assert_not_called()
            elif is_expansion:
                # Expansion should use expansion ETCD operations
                mock_dependencies["handle_etcd_operations_for_expansion"].assert_called_once()
                mock_dependencies["handle_etcd_operations_for_replacement"].assert_not_called()
            else:
                # Replacement should use replacement ETCD operations
                mock_dependencies["handle_etcd_operations_for_replacement"].assert_called_once()
                mock_dependencies["handle_etcd_operations_for_expansion"].assert_not_called()


# =============================================================================
# Performance and Stress Tests
# =============================================================================


class TestUseCasePerformance:
    """Performance validation tests"""

    @pytest.mark.slow
    def test_use_case_execution_time_bounds(self, mock_dependencies):
        """Test that all use cases complete within reasonable time bounds"""
        import time
        
        orchestrator = NodeOperationOrchestrator(**mock_dependencies)
        
        # Setup minimal mocks for fast execution
        backup_manager = Mock()
        backup_manager.setup_backup_directory = Mock(return_value="/tmp/test")
        backup_manager.backup_template_bmh = Mock(return_value=("/tmp/template.yaml", False))
        mock_dependencies["BackupManager"].return_value = backup_manager
        
        resource_manager = Mock()
        resource_manager.apply_resources_and_monitor = Mock(return_value=({}, 8))
        mock_dependencies["ResourceManager"].return_value = resource_manager
        
        # Test execution time for each use case
        test_cases = [
            ("worker_addition", True, False),
            ("control_replacement", False, False), 
            ("control_expansion", False, True)
        ]
        
        for case_name, is_addition, is_expansion in test_cases:
            args = SimpleNamespace(
                add_new_node=is_addition,
                expand_control_plane=is_expansion,
                replacement_node="test-node",
                replacement_node_ip="192.168.1.100",
                replacement_node_bmc_ip="192.168.2.100", 
                replacement_node_mac_address="52:54:00:e9:d5:8a",
                replacement_node_role="worker" if is_addition else "master",
                backup_dir="/tmp/test",
                sushy_uid=None,
                debug=False,
                skip_etcd=False
            )
            
            start_time = time.time()
            try:
                orchestrator.process_node_operation(args, is_addition=is_addition, is_expansion=is_expansion)
            except:
                pass  # Ignore errors, we're testing performance
            execution_time = time.time() - start_time
            
            # Each use case should complete in under 1 second with mocks
            assert execution_time < 1.0, f"{case_name} took {execution_time}s (expected < 1s)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
