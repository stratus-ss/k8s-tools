#!/usr/bin/env python3
"""Print Manager module for OpenShift Control Plane Replacement Tool."""

# Global debug flag
DEBUG_MODE = False


class PrintManager:
    """Manages all output formatting and printing for the application"""

    @staticmethod
    def print_header(message):
        """Print a section header with visual separation"""
        print(f"\n{'=' * 60}")
        print(f" {message.upper()}")
        print(f"{'=' * 60}")

    @staticmethod
    def print_info(message):
        """Print informational message"""
        print(f"    [INFO]  {message}")

    @staticmethod
    def print_success(message):
        """Print success message"""
        print(f"    [✓]     {message}")

    @staticmethod
    def print_warning(message):
        """Print warning message"""
        print(f"    [⚠️]     {message}")

    @staticmethod
    def print_error(message):
        """Print error message"""
        print(f"    [✗]     {message}")

    @staticmethod
    def print_step(step_num, total_steps, message):
        """Print numbered step"""
        print(f"[{step_num}/{total_steps}] {message}")

    @staticmethod
    def print_action(message):
        """Print action being performed (only in debug mode)"""
        if DEBUG_MODE:
            print(f"    [ACTION] {message}")


# Create a global print manager instance for convenience
printer = PrintManager()
