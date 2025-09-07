#!/usr/bin/env python3
"""
Tests for the ResourceMonitor BMH status monitoring functionality.

These tests focus on the critical BMH state interpretation and decision-making logic
in _monitor_bmh_status() which handles different BMH provisioning states.

Lines tested: 103-125 in resource_monitor.py (BMH status monitoring)
"""

import sys
import os

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from unittest.mock import Mock  # noqa: E402

from modules.resource_monitor import ResourceMonitor  # noqa: E402


class TestResourceMonitorBMHMonitoring:
    """Test the BMH status monitoring and state interpretation logic"""

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
            replacement_node="test-bmh-node",
            backup_dir="/tmp/test-backup",
            timeout_minutes=30,
            check_interval=5,
            is_addition=False,
            is_expansion=False,
            printer=mock_printer,
            execute_oc_command=mock_execute_oc_command,
        )

    def test_bmh_provisioned_state_success(self, resource_monitor):
        """
        Test BMH in 'provisioned' state triggers success and sets bmh_provisioned flag.

        This is the critical success path - BMH has completed provisioning
        and is ready for machine binding.
        """
        # Mock BMH data with 'provisioned' state
        bmh_data = {"status": {"provisioning": {"state": "provisioned"}}}
        resource_monitor.execute_oc_command.return_value = bmh_data

        # Verify initial state
        assert resource_monitor.bmh_provisioned is False

        # Execute BMH monitoring
        resource_monitor._monitor_bmh_status()

        # Verify success state is set
        assert resource_monitor.bmh_provisioned is True

        # Verify correct API call was made
        resource_monitor.execute_oc_command.assert_called_once_with(
            ["get", "bmh", "test-bmh-node", "-n", "openshift-machine-api", "-o", "json"], json_output=True
        )

        # Verify success messages were printed
        resource_monitor.printer.print_success.assert_any_call("BMH test-bmh-node is now Provisioned!")
        resource_monitor.printer.print_success.assert_any_call("BMH is ready for machine binding")
        assert resource_monitor.printer.print_success.call_count == 2

    def test_bmh_provisioning_state_waiting(self, resource_monitor):
        """
        Test BMH in 'provisioning' state shows waiting message and continues monitoring.

        This represents the BMH actively being provisioned by Ironic.
        """
        # Mock BMH data with 'provisioning' state
        bmh_data = {"status": {"provisioning": {"state": "provisioning"}}}
        resource_monitor.execute_oc_command.return_value = bmh_data

        # Execute BMH monitoring
        resource_monitor._monitor_bmh_status()

        # Verify bmh_provisioned flag remains False (still waiting)
        assert resource_monitor.bmh_provisioned is False

        # Verify appropriate waiting message
        resource_monitor.printer.print_info.assert_called_once_with(
            "BMH test-bmh-node is provisioning, waiting for Provisioned status..."
        )

    def test_bmh_ready_state_waiting(self, resource_monitor):
        """
        Test BMH in 'ready' state shows waiting message.

        This represents BMH that is ready to be provisioned but hasn't started yet.
        """
        # Mock BMH data with 'ready' state
        bmh_data = {"status": {"provisioning": {"state": "ready"}}}
        resource_monitor.execute_oc_command.return_value = bmh_data

        # Execute BMH monitoring
        resource_monitor._monitor_bmh_status()

        # Verify still waiting
        assert resource_monitor.bmh_provisioned is False

        # Verify appropriate waiting message
        resource_monitor.printer.print_info.assert_called_once_with(
            "BMH test-bmh-node is ready, waiting for Provisioned status..."
        )

    def test_bmh_available_state_waiting(self, resource_monitor):
        """
        Test BMH in 'available' state shows waiting message.

        This represents BMH that is available for allocation.
        """
        # Mock BMH data with 'available' state
        bmh_data = {"status": {"provisioning": {"state": "available"}}}
        resource_monitor.execute_oc_command.return_value = bmh_data

        # Execute BMH monitoring
        resource_monitor._monitor_bmh_status()

        # Verify still waiting
        assert resource_monitor.bmh_provisioned is False

        # Verify appropriate waiting message
        resource_monitor.printer.print_info.assert_called_once_with(
            "BMH test-bmh-node is available, waiting for Provisioned status..."
        )

    def test_bmh_error_state_shows_error(self, resource_monitor):
        """
        Test BMH in 'error' state shows error message requiring manual intervention.

        This is a critical failure state that requires user action.
        """
        # Mock BMH data with 'error' state
        bmh_data = {"status": {"provisioning": {"state": "error"}}}
        resource_monitor.execute_oc_command.return_value = bmh_data

        # Execute BMH monitoring
        resource_monitor._monitor_bmh_status()

        # Verify still not provisioned (error state)
        assert resource_monitor.bmh_provisioned is False

        # Verify error message was shown
        resource_monitor.printer.print_error.assert_called_once_with(
            "BMH test-bmh-node is in error state - manual intervention required"
        )

    def test_bmh_unknown_state_shows_generic_message(self, resource_monitor):
        """
        Test BMH in unknown/unexpected state shows generic monitoring message.

        This handles any other BMH states not explicitly handled.
        """
        # Mock BMH data with unknown state
        bmh_data = {"status": {"provisioning": {"state": "some-unknown-state"}}}
        resource_monitor.execute_oc_command.return_value = bmh_data

        # Execute BMH monitoring
        resource_monitor._monitor_bmh_status()

        # Verify still not provisioned
        assert resource_monitor.bmh_provisioned is False

        # Verify generic monitoring message
        resource_monitor.printer.print_info.assert_called_once_with(
            "BMH test-bmh-node status: some-unknown-state, continuing to monitor..."
        )

    def test_bmh_missing_provisioning_section_defaults_to_unknown(self, resource_monitor):
        """
        Test BMH data missing provisioning section defaults to 'Unknown' state.

        This handles malformed or incomplete BMH data.
        """
        # Mock BMH data missing provisioning section
        bmh_data = {
            "status": {
                # Missing provisioning section
            }
        }
        resource_monitor.execute_oc_command.return_value = bmh_data

        # Execute BMH monitoring
        resource_monitor._monitor_bmh_status()

        # Verify still not provisioned
        assert resource_monitor.bmh_provisioned is False

        # Verify default 'Unknown' state message
        resource_monitor.printer.print_info.assert_called_once_with(
            "BMH test-bmh-node status: Unknown, continuing to monitor..."
        )

    def test_bmh_missing_status_section_defaults_to_unknown(self, resource_monitor):
        """
        Test BMH data missing entire status section defaults to 'Unknown' state.

        This handles severely malformed BMH data that has some structure but no status.
        """
        # Mock BMH data missing status section but not empty (so it passes "if bmh_data")
        bmh_data = {
            "metadata": {"name": "test-bmh-node"}
            # Missing status section entirely
        }
        resource_monitor.execute_oc_command.return_value = bmh_data

        # Execute BMH monitoring
        resource_monitor._monitor_bmh_status()

        # Verify still not provisioned
        assert resource_monitor.bmh_provisioned is False

        # Verify default 'Unknown' state message
        resource_monitor.printer.print_info.assert_called_once_with(
            "BMH test-bmh-node status: Unknown, continuing to monitor..."
        )

    def test_bmh_not_found_shows_waiting_message(self, resource_monitor):
        """
        Test when BMH is not found (None/empty response) shows appropriate waiting message.

        This handles the case where BMH hasn't been created yet or API call fails.
        """
        # Mock execute_oc_command returning None (BMH not found)
        resource_monitor.execute_oc_command.return_value = None

        # Execute BMH monitoring
        resource_monitor._monitor_bmh_status()

        # Verify still not provisioned
        assert resource_monitor.bmh_provisioned is False

        # Verify BMH not found message
        resource_monitor.printer.print_info.assert_called_once_with(
            "BMH test-bmh-node not found yet, waiting for it to appear..."
        )

    def test_bmh_empty_response_shows_waiting_message(self, resource_monitor):
        """
        Test when BMH returns empty dict shows appropriate waiting message.

        This handles API responses that are empty but not None.
        """
        # Mock execute_oc_command returning empty dict
        resource_monitor.execute_oc_command.return_value = {}

        # Execute BMH monitoring
        resource_monitor._monitor_bmh_status()

        # Verify still not provisioned
        assert resource_monitor.bmh_provisioned is False

        # Since empty dict evaluates to False, should show "not found" message
        resource_monitor.printer.print_info.assert_called_once_with(
            "BMH test-bmh-node not found yet, waiting for it to appear..."
        )

    def test_api_call_parameters_are_correct(self, resource_monitor):
        """
        Test that the API call uses correct parameters for BMH fetch.

        This validates the OpenShift API call structure.
        """
        # Mock successful response
        bmh_data = {"status": {"provisioning": {"state": "provisioned"}}}
        resource_monitor.execute_oc_command.return_value = bmh_data

        # Execute BMH monitoring
        resource_monitor._monitor_bmh_status()

        # Verify correct API call parameters
        expected_cmd = ["get", "bmh", "test-bmh-node", "-n", "openshift-machine-api", "-o", "json"]
        resource_monitor.execute_oc_command.assert_called_once_with(expected_cmd, json_output=True)


class TestBMHStateTransitions:
    """Test BMH state transitions and edge cases"""

    @pytest.fixture
    def resource_monitor(self):
        """ResourceMonitor with mocked dependencies for state testing"""
        return ResourceMonitor(
            replacement_node="transition-test-bmh",
            backup_dir="/tmp/test",
            timeout_minutes=10,
            check_interval=1,
            printer=Mock(),
            execute_oc_command=Mock(),
        )

    def test_multiple_calls_maintain_state_consistency(self, resource_monitor):
        """
        Test that multiple calls to _monitor_bmh_status maintain consistent state.

        This ensures the method is idempotent and doesn't have side effects.
        """
        # Mock BMH in provisioned state
        bmh_data = {"status": {"provisioning": {"state": "provisioned"}}}
        resource_monitor.execute_oc_command.return_value = bmh_data

        # Call multiple times
        resource_monitor._monitor_bmh_status()
        first_call_state = resource_monitor.bmh_provisioned

        resource_monitor._monitor_bmh_status()
        second_call_state = resource_monitor.bmh_provisioned

        # Verify state remains consistent
        assert first_call_state is True
        assert second_call_state is True
        assert first_call_state == second_call_state

    def test_state_progression_from_provisioning_to_provisioned(self, resource_monitor):
        """
        Test realistic state progression from provisioning -> provisioned.

        This simulates a real BMH provisioning workflow.
        """
        # First call: BMH is provisioning
        provisioning_data = {"status": {"provisioning": {"state": "provisioning"}}}
        resource_monitor.execute_oc_command.return_value = provisioning_data
        resource_monitor._monitor_bmh_status()

        # Verify intermediate state
        assert resource_monitor.bmh_provisioned is False

        # Second call: BMH becomes provisioned
        provisioned_data = {"status": {"provisioning": {"state": "provisioned"}}}
        resource_monitor.execute_oc_command.return_value = provisioned_data
        resource_monitor._monitor_bmh_status()

        # Verify final state
        assert resource_monitor.bmh_provisioned is True

    def test_case_sensitivity_of_bmh_states(self, resource_monitor):
        """
        Test that BMH state comparison is case-sensitive.

        This ensures exact matching of BMH states as returned by OpenShift API.
        """
        # Test uppercase 'PROVISIONED' - should NOT match
        uppercase_data = {"status": {"provisioning": {"state": "PROVISIONED"}}}
        resource_monitor.execute_oc_command.return_value = uppercase_data
        resource_monitor._monitor_bmh_status()

        # Should NOT be considered provisioned (case sensitive)
        assert resource_monitor.bmh_provisioned is False

        # Should show generic message for unknown state
        resource_monitor.printer.print_info.assert_called_with(
            "BMH transition-test-bmh status: PROVISIONED, continuing to monitor..."
        )
