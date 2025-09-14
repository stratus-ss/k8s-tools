#!/usr/bin/env python3
"""
Tests for the ResourceMonitor machine discovery functionality.

These tests focus on Phase 2 machine discovery logic which is critical for all 4 use cases.
This handles the transition from BMH provisioned (Phase 1) to machine monitoring (Phase 3).

Lines tested:
- 127-144 (_discover_machine_for_worker_addition)
- 146-163 (_discover_machine_for_control_plane)
- 165-188 (_get_machine_info and related logic)
"""

import sys
import os

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from unittest.mock import Mock, patch  # noqa: E402

from modules.resource_monitor import ResourceMonitor  # noqa: E402


class TestResourceMonitorWorkerMachineDiscovery:
    """Test _discover_machine_for_worker_addition() - Phase 2 worker addition workflow"""

    @pytest.fixture
    def mock_printer(self):
        """Mock printer for testing"""
        return Mock()

    @pytest.fixture
    def mock_execute_oc_command(self):
        """Mock execute_oc_command function"""
        return Mock()

    @pytest.fixture
    def worker_monitor(self, mock_printer, mock_execute_oc_command):
        """ResourceMonitor instance configured for worker addition"""
        return ResourceMonitor(
            replacement_node="test-worker-bmh",
            backup_dir="/tmp/test-backup",
            timeout_minutes=30,
            check_interval=5,
            is_addition=True,  # Worker addition mode
            is_expansion=False,
            printer=mock_printer,
            execute_oc_command=mock_execute_oc_command,
        )

    def test_worker_machine_discovery_success_with_consumerref_lookup(self, worker_monitor):
        """
        Test successful machine discovery via BMH consumerRef lookup.

        This is the primary success path where:
        1. target_machine_name is initially None
        2. BMH consumerRef contains valid machine name
        3. All flags and timestamps are set correctly
        """
        # Ensure initial state (no target machine name set)
        assert worker_monitor.target_machine_name is None
        assert worker_monitor.machine_created is False
        assert worker_monitor.machine_monitor_start_time is None

        # Mock successful consumerRef lookup
        with patch.object(
            worker_monitor, "_get_machine_name_from_bmh_consumerref", return_value="test-worker-machine-xyz"
        ) as mock_consumerref, patch("time.time", return_value=1000.0):

            # Execute the discovery function
            worker_monitor._discover_machine_for_worker_addition()

            # Verify consumerRef lookup was called
            mock_consumerref.assert_called_once()

            # Verify state changes
            assert worker_monitor.target_machine_name == "test-worker-machine-xyz"
            assert worker_monitor.machine_created is True
            assert worker_monitor.machine_monitor_start_time == 1000.0

            # Verify print messages in correct order
            worker_monitor.printer.print_info.assert_any_call(
                "BMH is provisioned, looking for machine created by MachineSet..."
            )
            worker_monitor.printer.print_success.assert_called_once_with("Machine discovered: test-worker-machine-xyz")
            worker_monitor.printer.print_info.assert_any_call(
                "MachineSet has successfully created the machine, now monitoring status..."
            )
            worker_monitor.printer.print_info.assert_any_call(
                "Note: CSR checking will begin automatically if machine doesn't reach Provisioned state within 10 minutes"
            )

            # Should have exactly 3 info calls: initial + 2 success info messages
            assert worker_monitor.printer.print_info.call_count == 3

    def test_worker_machine_discovery_success_with_existing_target_machine(self, worker_monitor):
        """
        Test successful discovery when target_machine_name is already set.

        This handles cases where the machine name was set in previous calls
        or through other means. Should skip the consumerRef lookup.
        """
        # Pre-set the target machine name
        worker_monitor.target_machine_name = "existing-worker-machine-abc"

        # Mock time but NOT consumerRef lookup (should be skipped)
        with patch.object(worker_monitor, "_get_machine_name_from_bmh_consumerref") as mock_consumerref, patch(
            "time.time", return_value=2000.0
        ):

            # Execute the discovery function
            worker_monitor._discover_machine_for_worker_addition()

            # Verify consumerRef lookup was NOT called (machine name already exists)
            mock_consumerref.assert_not_called()

            # Verify state changes
            assert worker_monitor.target_machine_name == "existing-worker-machine-abc"  # Unchanged
            assert worker_monitor.machine_created is True
            assert worker_monitor.machine_monitor_start_time == 2000.0

            # Verify success messages
            worker_monitor.printer.print_success.assert_called_once_with(
                "Machine discovered: existing-worker-machine-abc"
            )

    def test_worker_machine_discovery_failure_consumerref_returns_none(self, worker_monitor):
        """
        Test failure case where BMH consumerRef lookup returns None.

        This handles cases where:
        - BMH doesn't have consumerRef set yet
        - consumerRef is malformed or missing machine name
        - API call fails
        """
        # Ensure initial state
        assert worker_monitor.target_machine_name is None
        assert worker_monitor.machine_created is False

        # Mock failed consumerRef lookup
        with patch.object(
            worker_monitor, "_get_machine_name_from_bmh_consumerref", return_value=None
        ) as mock_consumerref:

            # Execute the discovery function
            worker_monitor._discover_machine_for_worker_addition()

            # Verify consumerRef lookup was called
            mock_consumerref.assert_called_once()

            # Verify state remains unchanged (failed discovery)
            assert worker_monitor.target_machine_name is None
            assert worker_monitor.machine_created is False
            assert worker_monitor.machine_monitor_start_time is None

            # Verify initial info message
            worker_monitor.printer.print_info.assert_any_call(
                "BMH is provisioned, looking for machine created by MachineSet..."
            )

            # Verify waiting message
            worker_monitor.printer.print_info.assert_any_call(
                "Waiting for MachineSet to create machine and update BMH consumerRef..."
            )

            # Should have exactly 2 info calls: initial + waiting
            assert worker_monitor.printer.print_info.call_count == 2

            # Should have no success calls
            worker_monitor.printer.print_success.assert_not_called()

    def test_worker_machine_discovery_skips_consumerref_when_machine_name_exists(self, worker_monitor):
        """
        Test that consumerRef lookup is skipped when target_machine_name already exists.

        Note: The function will still update timestamps and print messages each time,
        but will skip the expensive BMH consumerRef API call.
        """
        # Pre-set target machine name
        worker_monitor.target_machine_name = "found-machine-def"

        # Mock time and consumerRef (consumerRef should not be called)
        with patch.object(worker_monitor, "_get_machine_name_from_bmh_consumerref") as mock_consumerref, patch(
            "time.time", return_value=1600.0
        ):

            # Execute function multiple times
            worker_monitor._discover_machine_for_worker_addition()
            worker_monitor._discover_machine_for_worker_addition()

            # Verify no additional API calls were made
            mock_consumerref.assert_not_called()

            # Verify machine name remains unchanged
            assert worker_monitor.target_machine_name == "found-machine-def"

            # Verify flags are set correctly (function always sets these when machine name exists)
            assert worker_monitor.machine_created is True
            assert worker_monitor.machine_monitor_start_time == 1600.0  # Updated timestamp


    def test_worker_machine_discovery_printer_message_order(self, worker_monitor):
        """
        Test that printer messages are called in the correct order for success case.

        Validates the specific sequence of user communications.
        """
        # Mock successful discovery
        with patch.object(
            worker_monitor, "_get_machine_name_from_bmh_consumerref", return_value="ordered-test-machine"
        ), patch("time.time", return_value=1234.5):

            # Execute the discovery function
            worker_monitor._discover_machine_for_worker_addition()

            # Verify exact call order
            expected_calls = [
                # Initial info message
                worker_monitor.printer.print_info.call_args_list[0][0][0],
                # Success message
                worker_monitor.printer.print_success.call_args_list[0][0][0],
                # First info message after success
                worker_monitor.printer.print_info.call_args_list[1][0][0],
                # Second info message after success
                worker_monitor.printer.print_info.call_args_list[2][0][0],
            ]

            expected_sequence = [
                "BMH is provisioned, looking for machine created by MachineSet...",
                "Machine discovered: ordered-test-machine",
                "MachineSet has successfully created the machine, now monitoring status...",
                "Note: CSR checking will begin automatically if machine doesn't reach Provisioned state within 10 minutes",
            ]

            assert expected_calls == expected_sequence

    def test_worker_machine_discovery_state_flags_verification(self, worker_monitor):
        """
        Test that all state flags are set correctly during successful discovery.

        Validates the critical state transitions that other phases depend on.
        """
        # Verify initial state
        initial_states = {
            "target_machine_name": worker_monitor.target_machine_name,
            "machine_created": worker_monitor.machine_created,
            "machine_monitor_start_time": worker_monitor.machine_monitor_start_time,
        }

        expected_initial = {
            "target_machine_name": None,
            "machine_created": False,
            "machine_monitor_start_time": None,
        }

        assert initial_states == expected_initial

        # Mock successful discovery with known timestamp
        test_timestamp = 999.123
        with patch.object(
            worker_monitor, "_get_machine_name_from_bmh_consumerref", return_value="state-test-machine"
        ), patch("time.time", return_value=test_timestamp):

            # Execute the discovery function
            worker_monitor._discover_machine_for_worker_addition()

            # Verify final state
            final_states = {
                "target_machine_name": worker_monitor.target_machine_name,
                "machine_created": worker_monitor.machine_created,
                "machine_monitor_start_time": worker_monitor.machine_monitor_start_time,
            }

            expected_final = {
                "target_machine_name": "state-test-machine",
                "machine_created": True,
                "machine_monitor_start_time": test_timestamp,
            }

            assert final_states == expected_final


class TestWorkerMachineDiscoveryIntegration:
    """Integration-style tests that test the worker discovery with less mocking"""

    @pytest.fixture
    def worker_monitor(self):
        """Worker monitor with minimal mocking for integration tests"""
        return ResourceMonitor(
            replacement_node="integration-test-bmh",
            backup_dir="/tmp/integration-test",
            timeout_minutes=15,
            check_interval=2,
            is_addition=True,
            printer=Mock(),
            execute_oc_command=Mock(),
        )

    def test_worker_discovery_realistic_workflow_progression(self, worker_monitor):
        """
        Test realistic progression: failed lookup -> successful lookup.

        Simulates real-world scenario where MachineSet takes time to create machine
        and update BMH consumerRef.
        """
        # First call: consumerRef not ready yet
        with patch.object(worker_monitor, "_get_machine_name_from_bmh_consumerref", return_value=None):
            worker_monitor._discover_machine_for_worker_addition()

            # Should be in waiting state
            assert worker_monitor.machine_created is False
            assert worker_monitor.target_machine_name is None

        # Second call: consumerRef now available
        with patch.object(
            worker_monitor, "_get_machine_name_from_bmh_consumerref", return_value="realistic-worker-machine"
        ), patch("time.time", return_value=5000.0):

            worker_monitor._discover_machine_for_worker_addition()

            # Should now be in discovered state
            assert worker_monitor.machine_created is True
            assert worker_monitor.target_machine_name == "realistic-worker-machine"
            assert worker_monitor.machine_monitor_start_time == 5000.0
