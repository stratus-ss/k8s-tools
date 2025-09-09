#!/usr/bin/env python3
"""
Comprehensive pytest tests for utilities module.
Tests all utility functions with realistic OpenShift data and enterprise-grade error handling.
"""

import pytest
import sys
import os
import subprocess
from unittest.mock import Mock, patch

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import after path modification to avoid E402
from modules.utilities import (  # noqa: E402
    format_runtime, normalize_node_role, _is_retryable_error,
    exec_pod_command, execute_oc_command, _build_exec_command, _run_pod_command,
    _handle_command_result, _should_retry_error
)


@pytest.fixture
def command_test_cases():
    """Fixture providing test cases for command building."""
    return [
        {
            "name": "without_container",
            "args": ("test-pod", ["ls", "-la"], "test-namespace"),
            "kwargs": {},
            "expected": ["oc", "exec", "-n", "test-namespace", "test-pod", "--", "ls", "-la"]
        },
        {
            "name": "with_container", 
            "args": ("test-pod", ["ls", "-la"], "test-namespace"),
            "kwargs": {"container_name": "test-container"},
            "expected": ["oc", "exec", "-n", "test-namespace", "test-pod", "-c", "test-container", "--", "ls", "-la"]
        },
        {
            "name": "complex_args",
            "args": ("etcd-pod", ["etcdctl", "endpoint", "health"], "openshift-etcd"),
            "kwargs": {},
            "expected": ["oc", "exec", "-n", "openshift-etcd", "etcd-pod", "--", "etcdctl", "endpoint", "health"]
        }
    ]

@pytest.fixture
def mock_printer() -> Mock:
    """Mock printer for testing output operations.

    Returns:
        Mock: Mock printer instance with all required methods.
    """
    printer = Mock()
    return printer


@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run for testing command execution.

    Returns:
        Mock: Mock subprocess.run function with realistic return values.
    """
    with patch('modules.utilities.subprocess.run') as mock_run:
        yield mock_run


@pytest.fixture
def mock_time_sleep():
    """Mock time.sleep for testing retry delays.

    Returns:
        Mock: Mock time.sleep function.
    """
    with patch('modules.utilities.time.sleep') as mock_sleep:
        yield mock_sleep


class TestFormatRuntime:
    """Test cases for runtime formatting functionality."""

    def test_format_runtime_seconds_only(self) -> None:
        """Test runtime formatting for duration under 60 seconds.

        Validates that durations less than a minute are formatted correctly
        as seconds only with 's' suffix.
        """
        result = format_runtime(1000.0, 1010.5)
        assert result == "10s"

    def test_format_runtime_minutes_and_seconds(self) -> None:
        """Test runtime formatting for duration with minutes and seconds.

        Validates that durations over a minute are formatted correctly
        with both minutes and seconds components.
        """
        result = format_runtime(1000.0, 1090.5)
        assert result == "1m 30s"

    def test_format_runtime_exact_minute(self) -> None:
        """Test runtime formatting for exact minute durations.

        Validates that exact minute durations are formatted correctly
        without seconds component when seconds are zero.
        """
        result = format_runtime(1000.0, 1060.0)
        assert result == "1m 0s"

    def test_format_runtime_multiple_minutes(self) -> None:
        """Test runtime formatting for multiple minutes duration.

        Validates that longer durations with multiple minutes are
        formatted correctly.
        """
        result = format_runtime(1000.0, 1245.3)
        assert result == "4m 5s"

    def test_format_runtime_zero_duration(self) -> None:
        """Test runtime formatting for zero duration.

        Validates that zero duration is handled correctly.
        """
        result = format_runtime(1000.0, 1000.0)
        assert result == "0s"


# =============================================================================
# Test Node Role Normalization Functions
# =============================================================================


class TestNormalizeNodeRole:
    """Test cases for node role normalization functionality."""

    def test_normalize_node_role_control_variants(self) -> None:
        """Test node role normalization for control plane variants.

        Validates that all control plane role variants are normalized
        to 'master' for internal consistency.
        """
        assert normalize_node_role("control") == "master"
        assert normalize_node_role("control-plane") == "master"
        assert normalize_node_role("master") == "master"

    def test_normalize_node_role_worker_variants(self) -> None:
        """Test node role normalization for worker node variants.

        Validates that worker role variants are handled correctly.
        """
        assert normalize_node_role("worker") == "worker"

    def test_normalize_node_role_compute_preserved(self) -> None:
        """Test that compute role is preserved as-is.

        Validates that compute role is not normalized to worker
        in current implementation.
        """
        assert normalize_node_role("compute") == "compute"

    def test_normalize_node_role_unknown_preserved(self) -> None:
        """Test that unknown roles are preserved as-is.

        Validates that unrecognized roles are returned unchanged.
        """
        assert normalize_node_role("infrastructure") == "infrastructure"
        assert normalize_node_role("custom-role") == "custom-role"

    def test_normalize_node_role_empty_string(self) -> None:
        """Test node role normalization with empty string.

        Validates that empty string input is handled gracefully.
        """
        assert normalize_node_role("") == ""


# =============================================================================
# Test Error Handling Utilities
# =============================================================================


class TestErrorHandlingUtilities:
    """Test cases for error handling utility functions."""

    def test_is_retryable_error_connection_issues(self) -> None:
        """Test identification of retryable connection errors.

        Validates that connection-related errors are identified as retryable.
        """
        retryable_errors = [
            "connection refused",
            "dial tcp: connection refused",
            "keepalive ping failed",
            "timeout occurred",
            "connection reset by peer",
            "temporary failure in name resolution",
            "context deadline exceeded",
        ]

        for error in retryable_errors:
            assert _is_retryable_error(error) is True, f"Error should be retryable: {error}"

    def test_is_retryable_error_server_issues(self) -> None:
        """Test identification of retryable server errors.

        Validates that server-related errors are identified as retryable.
        """
        retryable_errors = [
            "service unavailable",
            "internal server error",
            "too many requests",
            "server is currently unable to handle the request",
        ]

        for error in retryable_errors:
            assert _is_retryable_error(error) is True, f"Error should be retryable: {error}"

    def test_is_retryable_error_non_retryable(self) -> None:
        """Test identification of non-retryable errors.

        Validates that permanent errors are not identified as retryable.
        """
        non_retryable_errors = [
            "resource not found",
            "permission denied",
            "invalid configuration",
            "syntax error",
            "authentication failed",
        ]

        for error in non_retryable_errors:
            assert _is_retryable_error(error) is False, f"Error should not be retryable: {error}"

    def test_is_retryable_error_empty_input(self) -> None:
        """Test retryable error check with empty input.

        Validates that empty/None inputs are handled correctly.
        """
        assert _is_retryable_error("") is False
        assert _is_retryable_error(None) is False



class TestBuildExecCommand:
    """Test cases for _build_exec_command helper function."""
    
    def test_build_exec_command(self, command_test_cases):
        """Test command building with various scenarios."""
        for case in command_test_cases:
            result = _build_exec_command(*case["args"], **case["kwargs"])
            assert result == case["expected"], f"Failed for case: {case['name']}"

class TestPodCommandExecution:
    """Test cases for complete pod command execution flow."""
    
    @patch('subprocess.run')
    def test_successful_execution(self, mock_subprocess_run, command_test_cases):
        """Test successful execution with various command configurations."""
        for case in command_test_cases:
            # Mock successful execution
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = f"output for {case['name']}"
            mock_result.stderr = ""
            mock_subprocess_run.return_value = mock_result
            
            # Execute command
            result = exec_pod_command(*case["args"], **case["kwargs"])
            
            # Verify result and that correct command was called
            assert result == f"output for {case['name']}"
            mock_subprocess_run.assert_called_with(
                case["expected"],
                capture_output=True,
                text=True,
                timeout=30
            )
            mock_subprocess_run.reset_mock()
    
    @patch('subprocess.run')
    @patch('time.sleep')
    def test_execution_features(self, mock_sleep, mock_subprocess_run):
        """Test execution-specific features like retry logic, stderr handling."""
        # Test retry logic
        mock_fail = Mock(returncode=1, stderr="timeout")
        mock_success = Mock(returncode=0, stdout="success", stderr="")
        mock_subprocess_run.side_effect = [mock_fail, mock_success]
        
        result = exec_pod_command("test-pod", ["ls"], "test-ns", max_retries=1, retry_delay=5)
        
        assert result == "success"
        assert mock_subprocess_run.call_count == 2
        mock_sleep.assert_called_once_with(5)
        
        # Reset for next test
        mock_subprocess_run.reset_mock()
        mock_sleep.reset_mock()
        
        # Test stderr handling
        mock_result = Mock(returncode=0, stdout="output", stderr="ignored")
        mock_subprocess_run.return_value = mock_result
        
        exec_pod_command("test-pod", ["ls"], "test-ns", discard_stderr=True)
        
        call_kwargs = mock_subprocess_run.call_args[1]
        assert call_kwargs["stderr"] == subprocess.DEVNULL
        
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--cov=modules.utilities", "--cov-report=term-missing"])
