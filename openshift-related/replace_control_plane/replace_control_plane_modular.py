#!/usr/bin/env python3
"""
OpenShift Control Plane Replacement Tool - Modular Version

This is the main entry point for the OpenShift Control Plane Replacement Tool.
It imports and uses modularized components for better maintainability and testing.

For a single-file monolithic version, use the build target:
    make build-monolith
"""

from modules import (
    ArgumentsParser,
    printer,
    determine_failed_control_node,
    format_runtime,
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
    exec_pod_command,
    BackupManager,
    NodeConfigurator,
    ResourceMonitor,
    normalize_node_role,
)
from modules.orchestrator import NodeOperationOrchestrator, handle_successful_completion, handle_provisioning_failure
from modules.resource_manager import ResourceManager
from modules.configuration_manager import create_new_node_configs, configure_replacement_node
from modules.etcd_manager import (
    handle_etcd_operations_for_replacement,
    handle_etcd_operations_for_expansion,
    re_enable_quorum_guard_after_expansion,
)


def main():
    """
    Main function to orchestrate OpenShift node operations.

    This function can perform two types of operations:

    1. Control plane node replacement (default behavior):
       - 12-step process to safely remove a failed control plane node and prepare replacement
       - Includes ETCD cluster recovery, quorum guard management, and full provisioning

    2. Worker node addition (--add_new_node flag):
       - Simplified process to add a new worker node to the cluster
       - Creates BMH, Machine, and associated secrets without ETCD operations

    Args:
        None (uses command-line arguments)

    Returns:
        None
    """
    # Parse command-line arguments first to determine operation mode
    args = ArgumentsParser.parse_arguments()

    # Normalize the role (e.g., "control" -> "master" for OpenShift compatibility)
    if hasattr(args, "replacement_node_role") and args.replacement_node_role:
        args.replacement_node_role = normalize_node_role(args.replacement_node_role)

    # Prepare dependencies for modules
    dependencies = {
        "printer": printer,
        "determine_failed_control_node": determine_failed_control_node,
        "format_runtime": format_runtime,
        "execute_oc_command": execute_oc_command,
        "find_bmh_by_pattern": find_bmh_by_pattern,
        "find_bmh_by_mac_address": find_bmh_by_mac_address,
        "find_machineset_for_machine": find_machineset_for_machine,
        "annotate_machine_for_deletion": annotate_machine_for_deletion,
        "scale_down_machineset": scale_down_machineset,
        "cordon_node": cordon_node,
        "drain_node": drain_node,
        "delete_machine": delete_machine,
        "delete_bmh": delete_bmh,
        "verify_resources_deleted": verify_resources_deleted,
        "exec_pod_command": exec_pod_command,
        "BackupManager": BackupManager,
        "NodeConfigurator": NodeConfigurator,
        "ResourceMonitor": ResourceMonitor,
        "handle_successful_completion": handle_successful_completion,
        "handle_provisioning_failure": handle_provisioning_failure,
        "ResourceManager": ResourceManager,
        "create_new_node_configs": create_new_node_configs,
        "configure_replacement_node": configure_replacement_node,
        "handle_etcd_operations_for_replacement": handle_etcd_operations_for_replacement,
        "handle_etcd_operations_for_expansion": handle_etcd_operations_for_expansion,
        "re_enable_quorum_guard_after_expansion": re_enable_quorum_guard_after_expansion,
    }

    # Create orchestrator with all dependencies
    orchestrator = NodeOperationOrchestrator(**dependencies)

    if args.add_new_node:
        printer.print_header("OpenShift Worker Node Addition Tool")
        orchestrator.process_node_operation(args, is_addition=True)
    elif getattr(args, "expand_control_plane", False):
        printer.print_header("OpenShift Control Plane Expansion Tool")
        orchestrator.process_node_operation(args, is_addition=False, is_expansion=True)
    else:
        printer.print_header("OpenShift Control Plane Replacement Tool")
        orchestrator.process_node_operation(args, is_addition=False, is_expansion=False)


if __name__ == "__main__":
    main()
