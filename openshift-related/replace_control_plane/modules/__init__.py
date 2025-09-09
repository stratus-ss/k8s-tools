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
- orchestrator: High-level workflow orchestration and completion handling
- resource_manager: Resource backup, removal, and application operations
- configuration_manager: Configuration file creation and management
- etcd_manager: ETCD cluster operations and member management
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
    find_bmh_by_pattern,
    find_bmh_by_mac_address,
    find_machineset_for_machine,
    annotate_machine_for_deletion,
    scale_down_machineset,
    cordon_node,
    drain_node,
    delete_machine,
    delete_bmh,
    verify_resources_deleted,
    format_runtime,
    normalize_node_role,
    find_node,
)

# Import new modular functions
from .orchestrator import (
    NodeOperationOrchestrator,
    handle_successful_completion,
    handle_provisioning_failure,
)
from .resource_manager import ResourceManager
from .configuration_manager import (
    create_new_node_configs,
    configure_replacement_node,
)
from .etcd_manager import (
    handle_etcd_operations_for_replacement,
    handle_etcd_operations_for_expansion,
    re_enable_quorum_guard_after_expansion,
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
    "find_bmh_by_pattern",
    "find_bmh_by_mac_address",
    "find_machineset_for_machine",
    "annotate_machine_for_deletion",
    "scale_down_machineset",
    "cordon_node",
    "drain_node",
    "delete_machine",
    "delete_bmh",
    "verify_resources_deleted",
    "format_runtime",
    "normalize_node_role",
    "find_node",
    # New modular functions
    "NodeOperationOrchestrator",
    "handle_successful_completion",
    "handle_provisioning_failure",
    "ResourceManager",
    "create_new_node_configs",
    "configure_replacement_node",
    "handle_etcd_operations_for_replacement",
    "handle_etcd_operations_for_expansion",
    "re_enable_quorum_guard_after_expansion",
]
