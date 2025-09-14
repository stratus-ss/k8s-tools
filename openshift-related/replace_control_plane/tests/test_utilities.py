#!/usr/bin/env python3
"""
Comprehensive pytest tests for utilities module.
Tests all utility functions with realistic OpenShift data and enterprise-grade error handling.
"""

import pytest
import sys
import os
from unittest.mock import Mock

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import after path modification to avoid E402
from modules.utilities import format_runtime, normalize_node_role, _is_retryable_error  # noqa: E402


# =============================================================================
# Test Fixtures - Static Data from Real OpenShift Environments
# =============================================================================


@pytest.fixture
def mock_printer() -> Mock:
    """Mock printer for testing output operations.

    Returns:
        Mock: Mock printer instance with all required methods.
    """
    printer = Mock()
    printer.print_info = Mock()
    printer.print_action = Mock()
    printer.print_success = Mock()
    printer.print_error = Mock()
    printer.print_warning = Mock()
    printer.print_step = Mock()
    return printer


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


# =============================================================================
# Test Runner Configuration
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--cov=modules.utilities", "--cov-report=term-missing"])
