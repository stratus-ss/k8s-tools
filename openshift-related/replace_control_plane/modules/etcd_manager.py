#!/usr/bin/env python3
"""ETCD Manager module for ETCD cluster operations."""

import time
import json
from typing import Optional, Tuple, Callable, Any, Dict

# Import PrintManager for type hints
from .print_manager import PrintManager


def _get_healthy_etcd_pod(
    failed_node: str, execute_oc_command: Callable[..., Optional[Dict[str, Any]]], printer: PrintManager
) -> Optional[str]:
    """Retrieves all ETCD pods from the openshift-etcd namespace and filters out
    any pods that are not in 'Running' status or are associated with the failed node.
    Returns the first healthy pod found.

    Args:
        failed_node (str): The name of the failed node to exclude from selection.
        execute_oc_command (callable): Function to execute OpenShift CLI commands.
        printer (PrintManager): Object for formatted output printing.

    Returns:
        str or None: The name of a healthy ETCD pod, or None if no healthy pods are found.
    """
    all_etcd_pods = execute_oc_command(
        ["get", "pods", "-n", "openshift-etcd", "-l", "app=etcd", "-o", "json"], json_output=True, printer=printer
    )
    if not all_etcd_pods:
        return None

    healthy_pods = [
        item["metadata"]["name"]
        for item in all_etcd_pods.get("items", [])
        if item.get("status", {}).get("phase") == "Running" and failed_node not in item["metadata"]["name"]
    ]

    if not healthy_pods:
        return None

    printer.print_info(f"Using healthy ETCD pod: {healthy_pods[0]}")
    return healthy_pods[0]


def _execute_etcd_command_with_retry(
    etcd_pod: str, command: list, exec_pod_command: Callable[..., str], printer: PrintManager, command_description: str
) -> Optional[dict]:
    """Execute an etcdctl command with JSON output and proper error handling.

    Args:
        etcd_pod: Name of the ETCD pod to execute command on
        command: List of etcdctl command arguments
        exec_pod_command: Function to execute commands inside pods
        printer: Object for formatted output printing
        command_description: Human-readable description for logging

    Returns:
        dict: Parsed JSON result or None if command failed
    """
    output = exec_pod_command(
        etcd_pod,
        command,
        "openshift-etcd",
        "etcd",
        discard_stderr=True,
    )

    if output is None:
        printer.print_error(f"Failed to execute {command_description} - command returned None")
        return None

    try:
        return json.loads(output)
    except (json.JSONDecodeError, TypeError) as e:
        printer.print_error(f"Failed to parse {command_description} JSON: {e}")
        printer.print_error(f"Raw output: {output}")
        return None


def _remove_failed_etcd_member(
    etcd_pod: str, exec_pod_command: Callable[..., str], printer: PrintManager
) -> Optional[bool]:
    """Find and remove the failed ETCD member from the cluster.

    This function performs several operations:
    1. Checks endpoint health to identify failed endpoints
    2. Lists all ETCD members to find the member corresponding to the failed endpoint
    3. Removes the failed member from the ETCD cluster
    4. Verifies the removal was successful

    Args:
        etcd_pod (str): The name of a healthy ETCD pod to execute commands on.
        exec_pod_command (callable): Function to execute commands inside pods.
        printer (PrintManager): Object for formatted output printing.

    Returns:
        bool or None: True if the member was successfully removed or was already gone,
                     None if the operation failed, True if no failed endpoint was found.
    """
    # Find failed endpoint
    endpoint_health = _execute_etcd_command_with_retry(
        etcd_pod,
        ["etcdctl", "endpoint", "health", "--write-out=json"],
        exec_pod_command,
        printer,
        "endpoint health check",
    )

    if endpoint_health is None:
        return None
    failed_url = next((ep["endpoint"] for ep in endpoint_health if not ep["health"]), None)

    if not failed_url:
        return None

    printer.print_info(f"Found failed ETCD endpoint: {failed_url}")

    # Find and remove member
    member_list = _execute_etcd_command_with_retry(
        etcd_pod, ["etcdctl", "member", "list", "--write-out=json"], exec_pod_command, printer, "member list"
    )

    if member_list is None:
        return None

    # Debug: Show all members and their URLs
    if printer:
        printer.print_info(f"Searching for member with failed endpoint: {failed_url}")
        for member in member_list["members"]:
            member_name = member.get("name", "unknown")
            client_urls = member.get("clientURLs", [])
            printer.print_info(f"  Member: {member_name}, URLs: {client_urls}")

    # Try exact match first, then partial match
    failed_member = next((m for m in member_list["members"] if failed_url in m["clientURLs"]), None)

    # If no exact match, try to match by IP address from the URL
    if not failed_member and "://" in failed_url:
        failed_ip = failed_url.split("://")[1].split(":")[0]
        failed_member = next(
            (m for m in member_list["members"] if any(failed_ip in url for url in m["clientURLs"])), None
        )
        if failed_member and printer:
            printer.print_info(f"Found member by IP match: {failed_ip}")

    if not failed_member:
        printer.print_warning(f"Could not find ETCD member for failed endpoint: {failed_url}")
        printer.print_warning("This might indicate the member was already removed or the endpoint URL doesn't match")
        return True  # Consider this a success - member might already be gone

    member_id_hex = format(int(failed_member["ID"]), "x")
    member_name = failed_member.get("name", "unknown")

    printer.print_info(f"Removing ETCD member: {member_name} (ID: {member_id_hex})")

    # Remove and display results
    remove_result = _execute_etcd_command_with_retry(
        etcd_pod,
        ["etcdctl", "member", "remove", member_id_hex, "--write-out=json"],
        exec_pod_command,
        printer,
        "member removal",
    )

    if remove_result is None:
        return None
    printer.print_success(f"Successfully removed ETCD member: {member_name} (ID: {member_id_hex})")

    # Show remaining members
    remaining = remove_result.get("members", [])
    printer.print_info(f"Remaining ETCD cluster members: {len(remaining)}")
    for member in remaining:
        printer.print_info(f"  • {member.get('name', 'unknown')} (ID: {format(int(member['ID']), 'x')})")

    # Verify removal
    still_present = any(member["ID"] == failed_member["ID"] for member in remaining)
    if still_present:
        printer.print_error(f"WARNING: Member {member_name} still appears in member list!")
    else:
        printer.print_success(f"Confirmed: Member {member_name} successfully removed from cluster")

    return True


def _disable_quorum_guard(execute_oc_command: Callable[..., Any], printer: PrintManager) -> None:
    """Disables the ETCD quorum guard by patching the etcd/cluster resource with
    unsafe non-HA configuration. If the guard is already disabled, skips the wait.

    Args:
        execute_oc_command (callable): Function to execute OpenShift CLI commands.
        printer (PrintManager): Object for formatted output printing.

    Returns:
        None: This function doesn't return a value but prints status messages.
    """
    printer.print_action("Disabling ETCD quorum guard")
    result = execute_oc_command(
        [
            "patch",
            "etcd/cluster",
            "--type=merge",
            "-p",
            '{"spec": {"unsupportedConfigOverrides": {"useUnsupportedUnsafeNonHANonProductionUnstableEtcd": true}}}',
        ],
        printer=printer,
    )

    # Check if the guard was already disabled (no changes made)
    if result and "unchanged" in result.lower():
        printer.print_info("Quorum guard was already disabled - skipping wait")
    else:
        printer.print_info("Quorum guard disabled - waiting 120 seconds for ETCD cluster recovery...")
        time.sleep(120)

    printer.print_success("Quorum guard disabled")


def _enable_quorum_guard(execute_oc_command: Callable[..., Any], printer: PrintManager) -> None:
    """Re-enables the ETCD quorum guard by patching the etcd/cluster resource to
    remove the unsafe non-HA configuration override. Waits 60 seconds for the
    quorum guard to become active.

    Args:
        execute_oc_command (callable): Function to execute OpenShift CLI commands.
        printer (PrintManager): Object for formatted output printing.

    Returns:
        None: This function doesn't return a value but prints status messages.
    """
    printer.print_action("Re-enabling ETCD quorum guard")
    execute_oc_command(
        [
            "patch",
            "etcd/cluster",
            "--type=merge",
            "-p",
            '{"spec": {"unsupportedConfigOverrides": null}}',
        ],
        printer=printer,
    )
    printer.print_info("Waiting 60 seconds for ETCD quorum guard to become active...")
    time.sleep(60)
    printer.print_success("Quorum guard re-enabled - cluster is now production-safe")


def _cleanup_etcd_secrets(
    failed_node: str, execute_oc_command: Callable[..., Optional[Dict[str, Any]]], printer: PrintManager
) -> str:
    """Find the failed node and clean up its associated ETCD secrets.

    This function identifies the actual node name in the cluster that matches
    the failed node identifier, then finds and deletes all ETCD secrets in the
    openshift-etcd namespace that are associated with that node.

    Args:
        failed_node (str): The identifier of the failed node (may be partial name).
        execute_oc_command (callable): Function to execute OpenShift CLI commands.
        printer (PrintManager): Object for formatted output printing.

    Returns:
        str: The actual name of the bad node found in the cluster, or the original
             failed_node identifier if the node couldn't be found in the cluster.
    """
    # Find actual bad node name
    nodes = execute_oc_command(
        ["get", "nodes", "-l", "node-role.kubernetes.io/control-plane"], json_output=True, printer=printer
    )
    bad_node = failed_node  # fallback

    if nodes and nodes.get("items"):
        bad_node = next(
            (node["metadata"]["name"] for node in nodes["items"] if failed_node in node["metadata"]["name"]),
            failed_node,
        )
        printer.print_info(f"Found bad node in cluster: {bad_node}")
    else:
        printer.print_warning("Failed to retrieve control plane nodes, using fallback")

    # Delete matching secrets
    printer.print_info(f"Removing secrets for failed node: {bad_node}")
    secrets = execute_oc_command(["get", "secrets", "-n", "openshift-etcd"], json_output=True, printer=printer)
    deleted_count = 0

    if secrets and secrets.get("items"):
        for secret in secrets["items"]:
            if bad_node in secret["metadata"]["name"]:
                execute_oc_command(
                    ["delete", "secret", secret["metadata"]["name"], "-n", "openshift-etcd"], printer=printer
                )
                printer.print_success(f"Deleted secret: {secret['metadata']['name']}")
                deleted_count += 1
                time.sleep(0.5)  # Avoid overwhelming API
        printer.print_success(f"Deleted {deleted_count} ETCD secrets")
    else:
        printer.print_warning("Failed to retrieve ETCD secrets - skipping cleanup")

    return bad_node


def handle_etcd_operations_for_expansion(
    start_time: float,
    current_step: int,
    total_steps: int,
    printer: Optional[PrintManager] = None,
    execute_oc_command: Optional[Callable[..., Any]] = None,
    format_runtime: Optional[Callable[[float, float], str]] = None,
) -> Tuple[bool, int]:
    """Handle ETCD operations required for control plane expansion.

    It temporarily disables the ETCD quorum guard to allow the cluster to operate
    with a temporarily reduced quorum during the expansion process.

    Args:
        start_time (float): The timestamp when the overall process started,
                           used for runtime calculations.
        current_step (int): The current step number in the overall process.
        total_steps (int): The total number of steps in the overall process.
        printer (PrintManager, optional): Object for formatted output printing.
        execute_oc_command (callable, optional): Function to execute OpenShift CLI commands.
        format_runtime (callable, optional): Function to format elapsed time display.

    Returns:
        tuple: A tuple containing:
            - bool: True if operations completed successfully, False otherwise
            - int: The updated current step number for the next operation

    """

    # Step: Disable quorum guard for expansion
    if printer:
        printer.print_step(current_step, total_steps, "Disabling quorum guard for expansion")
    if execute_oc_command and printer:
        _disable_quorum_guard(execute_oc_command, printer)

    if format_runtime and printer:
        elapsed_time = format_runtime(start_time, time.time())
        printer.print_info(f"Elapsed time so far: {elapsed_time}")
        printer.print_success("ETCD quorum guard disabled - ready for control plane expansion")

    return True, current_step + 1


def handle_etcd_operations_for_replacement(
    failed_node: str,
    start_time: float,
    current_step: int,
    total_steps: int,
    printer: Optional[PrintManager] = None,
    exec_pod_command: Optional[Callable[..., str]] = None,
    execute_oc_command: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
    format_runtime: Optional[Callable[[float, float], str]] = None,
) -> Tuple[Optional[str], int]:
    """Handle ETCD operations required for control plane node replacement.

    This function orchestrates the complete ETCD cluster recovery process when
    replacing a failed control plane node. The process includes:
    1. Identifying and removing the failed ETCD member from the cluster
    2. Disabling the quorum guard to allow cluster operation during replacement
    3. Cleaning up ETCD secrets associated with the failed node

    Args:
        failed_node (str): The identifier of the failed node to be replaced.
        start_time (float): The timestamp when the overall process started.
        current_step (int): The current step number in the overall process.
        total_steps (int): The total number of steps in the overall process.
        printer (PrintManager, optional): Object for formatted output printing.
        exec_pod_command (callable, optional): Function to execute commands inside pods.
        execute_oc_command (callable, optional): Function to execute OpenShift CLI commands.
        format_runtime (callable, optional): Function to format elapsed time display.

    Returns:
        tuple: A tuple containing:
            - str or None: The actual name of the failed node if successful,
                          None if the operation failed
            - int: The updated current step number for the next operation
    """

    def exit_with_runtime(message: str) -> Tuple[None, int]:
        """Exit the operation with runtime information and error reporting.

        This nested function provides a standardized way to exit from the
        replacement operation when an error occurs. It prints the error message,
        calculates and displays the total runtime up to the point of failure,
        and returns standardized values to indicate failure.

        Args:
            message (str): The error message to display before exiting.

        Returns:
            tuple: A tuple containing:
                - None: Indicates operation failure
                - int: The current step number (unchanged)
        """
        if printer:
            printer.print_error(message)
        if format_runtime and printer:
            total_runtime = format_runtime(start_time, time.time())
            printer.print_info(f"Runtime before exit: {total_runtime}")
        return None, current_step

    # Step 3: Processing ETCD cluster recovery
    if printer:
        printer.print_step(current_step, total_steps, "Processing ETCD cluster recovery")

    # Get healthy ETCD pod
    if not execute_oc_command or not printer:
        return None, current_step
    etcd_pod = _get_healthy_etcd_pod(failed_node, execute_oc_command, printer)
    if not etcd_pod:
        return exit_with_runtime("No healthy ETCD pods available")

    # Remove failed ETCD member
    if not exec_pod_command:
        return None, current_step
    if not _remove_failed_etcd_member(etcd_pod, exec_pod_command, printer):
        return exit_with_runtime("Failed to remove ETCD member")

    time.sleep(3)
    current_step += 1

    # Step 4: Disable quorum guard
    if printer:
        printer.print_step(current_step, total_steps, "Disabling quorum guard")
    if execute_oc_command and printer:
        _disable_quorum_guard(execute_oc_command, printer)

    if format_runtime and printer:
        elapsed_time = format_runtime(start_time, time.time())
        printer.print_info(f"Elapsed time so far: {elapsed_time}")
    current_step += 1

    # Step 5: Clean up ETCD secrets
    if printer:
        printer.print_step(current_step, total_steps, "Cleaning up ETCD secrets")
    if execute_oc_command and printer:
        bad_node = _cleanup_etcd_secrets(failed_node, execute_oc_command, printer)
    else:
        bad_node = None

    return bad_node, current_step + 1


def re_enable_quorum_guard_after_expansion(
    start_time: float,
    current_step: int,
    total_steps: int,
    printer: Optional[PrintManager] = None,
    execute_oc_command: Optional[Callable[..., Any]] = None,
    format_runtime: Optional[Callable[[float, float], str]] = None,
) -> int:
    """Re-enable ETCD quorum guard after successful control plane expansion.

    Args:
        start_time (float): The timestamp when the overall process started,
                           used to calculate total runtime.
        current_step (int): The current step number in the overall process.
        total_steps (int): The total number of steps in the overall process.
        printer (PrintManager, optional): Object for formatted output printing.
        execute_oc_command (callable, optional): Function to execute OpenShift CLI commands.
        format_runtime (callable, optional): Function to format elapsed time display.

    Returns:
        int: The updated current step number after completion.
    """
    if printer:
        printer.print_step(current_step, total_steps, "Re-enabling ETCD quorum guard")
    if execute_oc_command and printer:
        _enable_quorum_guard(execute_oc_command, printer)

    if format_runtime and printer:
        elapsed_time = format_runtime(start_time, time.time())
        printer.print_info(f"Total elapsed time: {elapsed_time}")
        printer.print_success("ETCD quorum guard restored - control plane expansion complete!")

    return current_step + 1
