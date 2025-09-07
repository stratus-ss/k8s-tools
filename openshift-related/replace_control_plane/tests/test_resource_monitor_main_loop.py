#!/usr/bin/env python3
"""
Tests for the ResourceMonitor main monitoring loop state machine.

These tests focus on the core orchestration logic in monitor_provisioning_sequence()
which implements the 4-phase provisioning state machine.

Lines tested: 72-99 in resource_monitor.py (main monitoring loop)
"""

import pytest
import time
from unittest.mock import Mock, patch, call
import sys
import os

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.resource_monitor import ResourceMonitor


class TestResourceMonitorMainLoop:
    """Test the main monitoring loop state machine logic"""

    @pytest.fixture
    def mock_printer(self):
        """Mock printer for testing"""
        return Mock()

    @pytest.fixture
    def mock_execute_oc_command(self):
        """Mock execute_oc_command function"""
        return Mock()

    @pytest.fixture
    def resource_monitor(self, mock_printer, mock_execute_oc_command):
        """ResourceMonitor instance with mocked dependencies"""
        return ResourceMonitor(
            replacement_node="test-node",
            backup_dir="/tmp/test-backup",
            timeout_minutes=1,  # Short timeout for testing
            check_interval=0.1,  # Short interval for testing
            is_addition=False,
            is_expansion=False,
            printer=mock_printer,
            execute_oc_command=mock_execute_oc_command,
        )

    @pytest.fixture
    def worker_monitor(self, mock_printer, mock_execute_oc_command):
        """ResourceMonitor for worker addition testing"""
        return ResourceMonitor(
            replacement_node="test-worker",
            backup_dir="/tmp/test-backup",
            timeout_minutes=1,
            check_interval=0.1,
            is_addition=True,  # Worker addition mode
            is_expansion=False,
            printer=mock_printer,
            execute_oc_command=mock_execute_oc_command,
        )

    def test_complete_successful_provisioning_sequence(self, resource_monitor):
        """
        Test complete 4-phase provisioning sequence that succeeds.
        
        This tests the happy path through all state transitions:
        Phase 1: BMH Provisioned -> Phase 2: Machine Created -> 
        Phase 3: Machine Running -> Phase 4: Node Ready
        """
        # Mock all internal methods to simulate successful progression
        with patch.object(resource_monitor, '_print_progress'), \
             patch.object(resource_monitor, '_monitor_bmh_status') as mock_bmh, \
             patch.object(resource_monitor, '_discover_machine_for_control_plane') as mock_discover_cp, \
             patch.object(resource_monitor, '_monitor_machine_status') as mock_machine, \
             patch.object(resource_monitor, '_monitor_node_and_csrs') as mock_node, \
             patch.object(resource_monitor, '_get_final_status', return_value=(True, "Phase 4: Node Ready", "")) as mock_final, \
             patch('time.sleep'):  # Mock sleep to speed up test

            # Simulate state progression through all phases
            call_count = 0
            def simulate_progression(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # First call: BMH becomes provisioned
                    resource_monitor.bmh_provisioned = True
                elif call_count == 2:
                    # Second call: Machine is discovered
                    resource_monitor.machine_created = True
                elif call_count == 3:
                    # Third call: Machine becomes running
                    resource_monitor.machine_running = True
                elif call_count == 4:
                    # Fourth call: Node becomes ready
                    resource_monitor.node_ready = True

            # Set up method side effects to advance states
            mock_bmh.side_effect = lambda: setattr(resource_monitor, 'bmh_provisioned', True)
            mock_discover_cp.side_effect = lambda: setattr(resource_monitor, 'machine_created', True)
            mock_machine.side_effect = lambda: setattr(resource_monitor, 'machine_running', True)
            mock_node.side_effect = lambda: setattr(resource_monitor, 'node_ready', True)

            # Execute the monitoring sequence
            success, phase, error = resource_monitor.monitor_provisioning_sequence()

            # Verify successful completion
            assert success is True
            assert phase == "Phase 4: Node Ready"
            assert error == ""

            # Verify all phases were called in correct order
            mock_bmh.assert_called_once()
            mock_discover_cp.assert_called_once()
            mock_machine.assert_called_once()
            mock_node.assert_called_once()
            mock_final.assert_called_once()

            # Verify initial setup calls
            assert resource_monitor.printer.print_info.call_count >= 2
            resource_monitor.printer.print_info.assert_any_call(
                "Starting automated 4-phase provisioning sequence..."
            )
            resource_monitor.printer.print_info.assert_any_call("Monitoring BMH: test-node")

    def test_worker_addition_uses_different_discovery_method(self, worker_monitor):
        """
        Test that worker addition uses _discover_machine_for_worker_addition
        instead of _discover_machine_for_control_plane
        """
        with patch.object(worker_monitor, '_print_progress'), \
             patch.object(worker_monitor, '_monitor_bmh_status') as mock_bmh, \
             patch.object(worker_monitor, '_discover_machine_for_worker_addition') as mock_discover_worker, \
             patch.object(worker_monitor, '_discover_machine_for_control_plane') as mock_discover_cp, \
             patch.object(worker_monitor, '_get_final_status', return_value=(True, "Phase 4: Node Ready", "")), \
             patch('time.sleep'):

            # Set up state progression: BMH provisioned -> Machine created -> Node ready
            mock_bmh.side_effect = lambda: setattr(worker_monitor, 'bmh_provisioned', True)
            mock_discover_worker.side_effect = lambda: [
                setattr(worker_monitor, 'machine_created', True),
                setattr(worker_monitor, 'machine_running', True),
                setattr(worker_monitor, 'node_ready', True)
            ][-1]  # Use last effect

            # Execute monitoring
            success, phase, error = worker_monitor.monitor_provisioning_sequence()

            # Verify worker-specific discovery method was called
            mock_discover_worker.assert_called_once()
            mock_discover_cp.assert_not_called()

            assert success is True

    def test_control_plane_uses_correct_discovery_method(self, resource_monitor):
        """
        Test that control plane operations use _discover_machine_for_control_plane
        """
        with patch.object(resource_monitor, '_print_progress'), \
             patch.object(resource_monitor, '_monitor_bmh_status') as mock_bmh, \
             patch.object(resource_monitor, '_discover_machine_for_worker_addition') as mock_discover_worker, \
             patch.object(resource_monitor, '_discover_machine_for_control_plane') as mock_discover_cp, \
             patch.object(resource_monitor, '_get_final_status', return_value=(True, "Phase 4: Node Ready", "")), \
             patch('time.sleep'):

            # Set up state progression
            mock_bmh.side_effect = lambda: setattr(resource_monitor, 'bmh_provisioned', True)
            mock_discover_cp.side_effect = lambda: [
                setattr(resource_monitor, 'machine_created', True),
                setattr(resource_monitor, 'machine_running', True), 
                setattr(resource_monitor, 'node_ready', True)
            ][-1]

            # Execute monitoring
            success, phase, error = resource_monitor.monitor_provisioning_sequence()

            # Verify control plane discovery method was called
            mock_discover_cp.assert_called_once()
            mock_discover_worker.assert_not_called()

    def test_timeout_during_phase_1_bmh_provisioning(self, resource_monitor):
        """Test timeout while waiting for BMH to be provisioned"""
        with patch.object(resource_monitor, '_print_progress'), \
             patch.object(resource_monitor, '_monitor_bmh_status'), \
             patch.object(resource_monitor, '_is_timeout_reached', side_effect=[False, False, True]), \
             patch.object(resource_monitor, '_get_final_status', return_value=(False, "Phase 1: BMH Provisioned", "BMH did not become Provisioned")), \
             patch('time.sleep'):

            # BMH never becomes provisioned (bmh_provisioned stays False)
            
            success, phase, error = resource_monitor.monitor_provisioning_sequence()

            # Verify timeout handling
            assert success is False
            assert phase == "Phase 1: BMH Provisioned" 
            assert error == "BMH did not become Provisioned"

    def test_timeout_during_phase_2_machine_creation(self, resource_monitor):
        """Test timeout while waiting for machine to be created"""
        with patch.object(resource_monitor, '_print_progress'), \
             patch.object(resource_monitor, '_monitor_bmh_status') as mock_bmh, \
             patch.object(resource_monitor, '_discover_machine_for_control_plane'), \
             patch.object(resource_monitor, '_is_timeout_reached', side_effect=[False, False, False, True]), \
             patch.object(resource_monitor, '_get_final_status', return_value=(False, "Phase 2: Machine Created", "Machine creation failed")), \
             patch('time.sleep'):

            # BMH becomes provisioned but machine never gets created
            mock_bmh.side_effect = lambda: setattr(resource_monitor, 'bmh_provisioned', True)
            
            success, phase, error = resource_monitor.monitor_provisioning_sequence()

            # Verify timeout at phase 2
            assert success is False
            assert phase == "Phase 2: Machine Created"
            assert error == "Machine creation failed"

    def test_timeout_during_phase_3_machine_running(self, resource_monitor):
        """Test timeout while waiting for machine to reach Running state"""
        with patch.object(resource_monitor, '_print_progress'), \
             patch.object(resource_monitor, '_monitor_bmh_status') as mock_bmh, \
             patch.object(resource_monitor, '_discover_machine_for_control_plane') as mock_discover, \
             patch.object(resource_monitor, '_monitor_machine_status'), \
             patch.object(resource_monitor, '_is_timeout_reached', side_effect=[False] * 4 + [True]), \
             patch.object(resource_monitor, '_get_final_status', return_value=(False, "Phase 3: Machine Running", "Machine did not reach Running state")), \
             patch('time.sleep'):

            # BMH and machine created but machine never reaches running state
            mock_bmh.side_effect = lambda: setattr(resource_monitor, 'bmh_provisioned', True)
            mock_discover.side_effect = lambda: setattr(resource_monitor, 'machine_created', True)
            
            success, phase, error = resource_monitor.monitor_provisioning_sequence()

            # Verify timeout at phase 3
            assert success is False
            assert phase == "Phase 3: Machine Running"
            assert error == "Machine did not reach Running state"

    def test_state_machine_transitions_in_correct_order(self, resource_monitor):
        """
        Test that the state machine phases are executed in the correct order
        and that each phase is only entered when the previous phase is complete.
        """
        method_call_order = []
        
        with patch.object(resource_monitor, '_print_progress'), \
             patch.object(resource_monitor, '_monitor_bmh_status') as mock_bmh, \
             patch.object(resource_monitor, '_discover_machine_for_control_plane') as mock_discover, \
             patch.object(resource_monitor, '_monitor_machine_status') as mock_machine, \
             patch.object(resource_monitor, '_monitor_node_and_csrs') as mock_node, \
             patch.object(resource_monitor, '_get_final_status', return_value=(True, "Phase 4: Node Ready", "")), \
             patch('time.sleep'):

            # Track method call order
            mock_bmh.side_effect = lambda: [
                method_call_order.append('bmh'),
                setattr(resource_monitor, 'bmh_provisioned', True)
            ]
            
            mock_discover.side_effect = lambda: [
                method_call_order.append('discover'),
                setattr(resource_monitor, 'machine_created', True)
            ]
            
            mock_machine.side_effect = lambda: [
                method_call_order.append('machine'),
                setattr(resource_monitor, 'machine_running', True)
            ]
            
            mock_node.side_effect = lambda: [
                method_call_order.append('node'),
                setattr(resource_monitor, 'node_ready', True)
            ]

            # Execute monitoring
            resource_monitor.monitor_provisioning_sequence()

            # Verify phases were called in correct order
            assert method_call_order == ['bmh', 'discover', 'machine', 'node']

    @patch('time.time')
    def test_start_time_is_set_correctly(self, mock_time, resource_monitor):
        """Test that start_time is set when monitoring begins"""
        mock_time.return_value = 1000.0
        
        with patch.object(resource_monitor, '_print_progress'), \
             patch.object(resource_monitor, '_is_timeout_reached', return_value=True), \
             patch.object(resource_monitor, '_get_final_status', return_value=(False, "Phase 1: BMH Provisioned", "Timeout")):

            resource_monitor.monitor_provisioning_sequence()

            # Verify start_time was set
            assert resource_monitor.start_time == 1000.0

    def test_loop_exits_immediately_when_node_ready(self, resource_monitor):
        """Test that the loop exits immediately if node is already ready"""
        # Set node as already ready
        resource_monitor.node_ready = True
        
        with patch.object(resource_monitor, '_print_progress') as mock_progress, \
             patch.object(resource_monitor, '_get_final_status', return_value=(True, "Phase 4: Node Ready", "")) as mock_final:

            success, phase, error = resource_monitor.monitor_provisioning_sequence()

            # Verify loop didn't run any monitoring methods
            mock_progress.assert_not_called()
            mock_final.assert_called_once()
            
            assert success is True
            assert phase == "Phase 4: Node Ready"

    def test_sleep_is_called_between_checks_unless_node_ready(self, resource_monitor):
        """Test that sleep is called between monitoring checks, except when node becomes ready"""
        with patch.object(resource_monitor, '_print_progress'), \
             patch.object(resource_monitor, '_monitor_bmh_status') as mock_bmh, \
             patch.object(resource_monitor, '_get_final_status', return_value=(True, "Phase 4: Node Ready", "")), \
             patch('time.sleep') as mock_sleep:

            # BMH becomes provisioned after 2 iterations, then node ready immediately
            call_count = 0
            def bmh_progression():
                nonlocal call_count
                call_count += 1
                if call_count >= 2:
                    resource_monitor.bmh_provisioned = True
                    resource_monitor.node_ready = True  # Skip directly to ready

            mock_bmh.side_effect = bmh_progression

            resource_monitor.monitor_provisioning_sequence()

            # Verify sleep was called before node became ready (at least once)
            assert mock_sleep.call_count >= 1
            mock_sleep.assert_called_with(0.1)  # check_interval from fixture


class TestResourceMonitorStateValidation:
    """Test state validation and edge cases in the monitoring loop"""

    @pytest.fixture
    def resource_monitor(self):
        """Basic ResourceMonitor for state testing"""
        return ResourceMonitor(
            replacement_node="test-node",
            backup_dir="/tmp/test",
            timeout_minutes=1,
            check_interval=0.1,
            printer=Mock(),
            execute_oc_command=Mock(),
        )

    def test_initial_state_is_correct(self, resource_monitor):
        """Test that initial state flags are set correctly"""
        assert resource_monitor.bmh_provisioned is False
        assert resource_monitor.machine_created is False
        assert resource_monitor.machine_running is False
        assert resource_monitor.node_ready is False

    def test_state_flags_can_be_set_independently(self, resource_monitor):
        """Test that state flags can be modified independently"""
        # Test individual flag setting
        resource_monitor.bmh_provisioned = True
        assert resource_monitor.bmh_provisioned is True
        assert resource_monitor.machine_created is False

        resource_monitor.machine_created = True
        assert resource_monitor.machine_created is True
        assert resource_monitor.machine_running is False

        resource_monitor.machine_running = True
        assert resource_monitor.machine_running is True
        assert resource_monitor.node_ready is False

        resource_monitor.node_ready = True
        assert resource_monitor.node_ready is True
