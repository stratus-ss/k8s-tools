#!/usr/bin/env python3
"""
OpenShift Control Plane Replacement Tool - Modular Components.

This package contains the modular components of the OpenShift Control Plane
Replacement Tool, broken down into logical modules for better maintainability
and testing.

Modules:
- print_manager: Handles all output formatting and printing
- utilities: Common utility functions for OpenShift operations
- backup_manager: Manages backup and file operations
- node_configurator: Handles configuration updates for replacement nodes
- arguments_parser: Command-line argument parsing
- resource_monitor: 4-phase provisioning monitoring
"""

from .arguments_parser import ArgumentsParser
from .backup_manager import BackupManager
from .node_configurator import NodeConfigurator
from .print_manager import PrintManager, printer, DEBUG_MODE
from .resource_monitor import ResourceMonitor
from .utilities import (
    determine_failed_control_node,
    exec_pod_command,
    execute_oc_command,
    format_runtime,
    normalize_node_role,
)

__all__ = [
    "ArgumentsParser",
    "BackupManager",
    "NodeConfigurator",
    "PrintManager",
    "printer",
    "DEBUG_MODE",
    "ResourceMonitor",
    "determine_failed_control_node",
    "exec_pod_command",
    "execute_oc_command",
    "format_runtime",
    "normalize_node_role",
]
