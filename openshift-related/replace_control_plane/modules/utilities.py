#!/usr/bin/env python3
"""Utilities module for OpenShift Control Plane Replacement Tool."""

import json
import subprocess
import time
from typing import Optional, Tuple

from .print_manager import printer


def _build_exec_command(pod_name: str, command: list, namespace: str, container_name: Optional[str] = None) -> list:
    """Build the oc exec command list.

    Args:
        pod_name: Name of the pod to execute command in
        command: List of command arguments to execute
        namespace: Kubernetes namespace
        container_name: Optional container name (if pod has multiple containers)

    Returns:
        List of command arguments for subprocess.run
    """
    if container_name:
        return ["oc", "exec", "-n", namespace, pod_name, "-c", container_name, "--", *command]
    else:
        return ["oc", "exec", "-n", namespace, pod_name, "--", *command]


def _run_pod_command(exec_command: list, discard_stderr: bool) -> subprocess.CompletedProcess:
    """Execute the pod command with appropriate stderr handling.

    Args:
        exec_command: The command to execute
        discard_stderr: If True, discard stderr output

    Returns:
        subprocess.CompletedProcess object
    """
    if discard_stderr:
        return subprocess.run(exec_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=30)
    else:
        return subprocess.run(exec_command, capture_output=True, text=True, timeout=30)


def _handle_command_result(
    result: subprocess.CompletedProcess, discard_stderr: bool, return_on_error: bool
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Handle the result of a pod command execution.

    Args:
        result: The subprocess result
        discard_stderr: If True, stderr was discarded
        return_on_error: If True, return stdout even on error

    Returns:
        Tuple of (success, stdout_result, error_message)
    """
    if result.returncode == 0:
        return True, result.stdout, None

    stderr = result.stderr if not discard_stderr else "Command failed with non-zero exit code"
    stdout_result: Optional[str] = None

    if return_on_error or (result.stdout and result.stdout.strip()):
        stdout_result = result.stdout

    return False, stdout_result, stderr


def _should_retry_error(attempt: int, max_retries: int, error_msg: str) -> bool:
    """Determine if an error should trigger a retry.

    Args:
        attempt: Current attempt number
        max_retries: Maximum retry attempts
        error_msg: Error message to check

    Returns:
        True if should retry, False otherwise
    """
    return attempt < max_retries and _is_retryable_error(error_msg)


def exec_pod_command(
    pod_name,
    command,
    namespace,
    container_name=None,
    discard_stderr=False,
    return_on_error=False,
    max_retries=3,
    retry_delay=2,
):
    """
    Execute a command in a pod and return the output with retry logic.

    Args:
        pod_name: Name of the pod to execute command in
        command: List of command arguments to execute
        namespace: Kubernetes namespace
        container_name: Optional container name (if pod has multiple containers)
        discard_stderr: If True, discard stderr output
        return_on_error: If True, return stdout even when command exits with non-zero code
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Seconds to wait between retries (default: 2)

    Returns:
        Command stdout as string, or None if command failed after all retries
    """
    exec_command = _build_exec_command(pod_name, command, namespace, container_name)
    last_error = None

    for attempt in range(max_retries + 1):  # +1 for the initial attempt
        try:
            # Log the attempt
            if attempt == 0:
                printer.print_action(f"Executing pod command: {' '.join(exec_command)}")
            else:
                printer.print_info(f"Retry attempt {attempt}/{max_retries}: {' '.join(exec_command)}")

            result = _run_pod_command(exec_command, discard_stderr)
            success, stdout_result, error_msg = _handle_command_result(result, discard_stderr, return_on_error)

            if success:
                if attempt > 0:
                    printer.print_success(f"Command succeeded on retry attempt {attempt}")
                return stdout_result

            # Handle failure
            last_error = error_msg

            if _should_retry_error(attempt, max_retries, error_msg):
                printer.print_warning(f"Command failed with retryable error, waiting {retry_delay}s before retry...")
                if not discard_stderr:
                    printer.print_info(f"Error: {error_msg.strip()}")
                time.sleep(retry_delay)
                retry_delay *= 1.5  # Exponential backoff with factor of 1.5
                continue
            else:
                # Not retryable or out of retries
                if not discard_stderr:
                    printer.print_error(f"Command failed: {error_msg}")
                return stdout_result

        except subprocess.TimeoutExpired:
            last_error = "Command timed out after 30 seconds"
            if attempt < max_retries:
                printer.print_warning(f"Command timed out, waiting {retry_delay}s before retry...")
                time.sleep(retry_delay)
                retry_delay *= 1.5  # Exponential backoff with factor of 1.5
                continue
            else:
                printer.print_error(last_error)
                return None
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                printer.print_warning(f"Exception occurred, waiting {retry_delay}s before retry...")
                printer.print_info(f"Exception: {e}")
                time.sleep(retry_delay)
                retry_delay *= 1.5  # Exponential backoff with factor of 1.5
                continue
            else:
                printer.print_error(f"Exception during command execution: {e}")
                return None

    # Should not reach here, but just in case
    printer.print_error(f"Command failed after {max_retries} retries. Last error: {last_error}")
    return None


def _is_retryable_error(stderr_text):
    """Check if the error is worth retrying."""
    if not stderr_text:
        return False

    # Common API server connectivity issues that warrant retry
    retryable_patterns = [
        "keepalive ping failed",
        "connection refused",
        "timeout",
        "connection reset",
        "temporary failure in name resolution",
        "service unavailable",
        "internal server error",
        "too many requests",
        "server is currently unable to handle the request",
        "dial tcp.*connect: connection refused",
        "dial tcp.*i/o timeout",
        "context deadline exceeded",
    ]

    stderr_lower = stderr_text.lower()
    return any(pattern in stderr_lower for pattern in retryable_patterns)


def _log_retry_attempt(printer, attempt, max_retries, exec_command):
    """Log retry attempt information."""
    if not printer:
        return
    if attempt == 0:
        printer.print_action(f"Executing oc command: {' '.join(exec_command)}")
    else:
        printer.print_info(f"Retry attempt {attempt}/{max_retries}: {' '.join(exec_command)}")


def _handle_command_success(result, json_output, attempt, printer):
    """Handle successful command execution."""
    if attempt > 0 and printer:
        printer.print_success(f"Command succeeded on retry attempt {attempt}")
    if json_output:
        return json.loads(result.stdout)
    return result.stdout.strip()


def _handle_command_failure(result, attempt, max_retries, retry_delay, printer):
    """Handle command failure and determine if retry should occur."""
    stderr = result.stderr
    if attempt < max_retries and _is_retryable_error(stderr):
        if printer:
            printer.print_warning(f"Command failed with retryable error, waiting {retry_delay}s before retry...")
            printer.print_info(f"Error: {stderr.strip()}")
        time.sleep(retry_delay)
        return True, stderr  # Should retry
    else:
        # Not retryable or out of retries
        if printer:
            printer.print_error(f"Command failed: {stderr}")
        return False, stderr  # Should not retry


def _handle_exception(exception, attempt, max_retries, retry_delay, printer):
    """Handle exceptions during command execution."""
    error_str = str(exception)
    if attempt < max_retries:
        if printer:
            printer.print_warning(f"Exception occurred, waiting {retry_delay}s before retry...")
            printer.print_info(f"Exception: {exception}")
        time.sleep(retry_delay)
        return True, error_str  # Should retry
    else:
        if printer:
            printer.print_error(f"Exception during command execution: {exception}")
        return False, error_str  # Should not retry


def execute_oc_command(command, json_output=False, printer=None, max_retries=3, retry_delay=2):
    """
    Execute an OpenShift CLI command with retry logic for API failures.

    Args:
        command: List of command arguments to execute (excluding 'oc')
        json_output: If True, add JSON output flag and parse result as JSON
        printer: Printer instance for output
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Seconds to wait between retries (default: 2)

    Returns:
        str or dict: Command output as string, or parsed JSON dict if json_output=True.
                    Returns None on command failure after all retries.
    """

    exec_command = ["oc"] + command
    last_error = None

    for attempt in range(max_retries + 1):  # +1 for the initial attempt
        try:
            _log_retry_attempt(printer, attempt, max_retries, exec_command)
            result = subprocess.run(exec_command, capture_output=True, text=True)

            # Success case
            if result.returncode == 0:
                return _handle_command_success(result, json_output, attempt, printer)

            # Failure case - check if retryable
            should_retry, last_error = _handle_command_failure(result, attempt, max_retries, retry_delay, printer)
            if not should_retry:
                return None

        except json.JSONDecodeError as e:
            if printer:
                printer.print_error(f"Failed to parse JSON output: {e}")
            return None
        except Exception as e:
            should_retry, last_error = _handle_exception(e, attempt, max_retries, retry_delay, printer)
            if not should_retry:
                return None

    # Should not reach here, but just in case
    if printer:
        printer.print_error(f"Command failed after {max_retries} retries. Last error: {last_error}")
    return None


def normalize_node_role(user_role):
    """
    Normalize user-provided node role to OpenShift internal role names.

    Args:
        user_role: Role provided by user (e.g., "control", "master", "worker", "infrastructure")

    Returns:
        str: Normalized role for use in OpenShift labels and configurations
    """
    # Map user-friendly "control" to OpenShift's internal "master"
    role_mapping = {
        "control": "master",
        "control-plane": "master",
    }

    # Return mapped role or original role if no mapping exists
    normalized = role_mapping.get(user_role.lower(), user_role)

    if normalized != user_role:
        printer.print_info(f"Role '{user_role}' normalized to '{normalized}' for OpenShift compatibility")

    return normalized


def format_runtime(start_time, end_time):
    """
    Format runtime duration in a human-readable way.

    Args:
        start_time (float): Start timestamp from time.time()
        end_time (float): End timestamp from time.time()

    Returns:
        str: Formatted runtime string (e.g., "5m 23s", "1h 15m 30s")
    """
    total_seconds = int(end_time - start_time)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def determine_failed_control_node():
    """
    Identify a control plane node that is in NotReady state.

    Returns:
        str or None: Name of the failed control node, or None if all nodes are ready
    """
    nodes_data = execute_oc_command(
        ["get", "nodes", "-l", "node-role.kubernetes.io/control-plane", "-o", "json"], json_output=True, printer=printer
    )
    if not nodes_data or not nodes_data.get("items"):
        if printer:
            printer.print_error("Failed to retrieve control plane nodes data")
        return None

    control_plane_nodes = []
    failed_nodes = []

    for node in nodes_data["items"]:
        node_name = node["metadata"]["name"]
        node_status = node["status"]["conditions"]
        control_plane_nodes.append(node_name)

        for condition in node_status:
            if condition["type"] == "Ready":
                if condition["status"] != "True":
                    failed_nodes.append(node_name)
                    printer.print_warning(f"Found failed control node: {node_name}")
                break

    if printer:
        printer.print_info(f"Found {len(control_plane_nodes)} control plane nodes:")
        for node in control_plane_nodes:
            status = "FAILED" if node in failed_nodes else "Ready"
            printer.print_info(f"  • {node} ({status})")

    if not failed_nodes:
        if printer:
            printer.print_warning("All control plane nodes appear healthy!")
            printer.print_warning("For control plane EXPANSION (adding a new node), use --expand-control-plane")
            printer.print_warning(
                "For control plane REPLACEMENT (replacing a failed node), ensure the failed node shows as NotReady"
            )

    return failed_nodes[0] if failed_nodes else None


def find_node(
    pattern=None,
    check_ready=False,
    node_selector="node-role.kubernetes.io/control-plane",
    nodes_data=None,
    printer=None,
):
    """
    Generic function to find a node based on various criteria.

    Args:
        pattern: String pattern to search for in node names (optional)
        check_ready: If True, only return nodes in Ready state (optional)
        node_selector: Node selector label (default: control-plane)
        nodes_data: Pre-fetched nodes data, if None will fetch from cluster
        printer: Printer instance for logging (optional)

    Returns:
        str or None: Full node name that matches criteria, or None if not found
    """
    # Fetch nodes data if not provided
    if nodes_data is None:
        nodes_data = execute_oc_command(
            ["get", "nodes", "-l", node_selector, "-o", "json"], json_output=True, printer=printer
        )

    if not nodes_data or not nodes_data.get("items"):
        if printer:
            data_source = "provided" if nodes_data is not None else "fetched"
            printer.print_warning(f"No nodes data available from {data_source} source")
        return None

    for node in nodes_data["items"]:
        node_name = node["metadata"]["name"]

        # Apply pattern filter if specified
        if pattern is not None and pattern not in node_name:
            continue

        # Apply ready state filter if specified
        if check_ready:
            node_ready = False
            node_conditions = node.get("status", {}).get("conditions", [])
            for condition in node_conditions:
                if condition["type"] == "Ready" and condition["status"] == "True":
                    node_ready = True
                    break
            if not node_ready:
                continue

        # Node matches all criteria
        return node_name

    return None


def find_bmh_by_pattern(pattern, bmh_data, printer=None):
    """
    Find a BMH that matches a pattern in its name.

    Args:
        pattern: String pattern to search for in BMH names
        bmh_data: BMH data from 'oc get bmh -o json'
        printer: Printer instance for logging (optional)

    Returns:
        str or None: Full BMH name that matches pattern, or None if not found
    """
    if not bmh_data or not bmh_data.get("items"):
        if printer:
            printer.print_warning("No BMH data available for pattern matching")
        return None

    for bmh in bmh_data["items"]:
        bmh_name = bmh["metadata"]["name"]
        if pattern in bmh_name:
            if printer:
                printer.print_info(f"Found BMH matching pattern '{pattern}': {bmh_name}")
            return bmh_name

    if printer:
        printer.print_warning(f"No BMH found matching pattern: {pattern}")
    return None


def find_bmh_by_mac_address(mac_address, bmh_data=None, printer=None):
    """
    Find a BMH that matches a specific MAC address.

    Args:
        mac_address: MAC address to search for in BMH bootMACAddress field
        bmh_data: BMH data from 'oc get bmh -o json', if None will fetch from cluster
        printer: Printer instance for logging (optional)

    Returns:
        dict or None: {'bmh_name': str, 'node_name': str} if found, None if not found
    """
    if not bmh_data:
        # Fetch BMH data if not provided
        bmh_data = execute_oc_command(
            ["get", "bmh", "-n", "openshift-machine-api", "-o", "json"], json_output=True, printer=printer
        )

    if not bmh_data or not bmh_data.get("items"):
        if printer:
            printer.print_warning("No BMH data available for MAC address search")
        return None

    # Normalize MAC address for comparison (remove colons, convert to lowercase)
    normalized_search_mac = mac_address.replace(":", "").replace("-", "").lower()

    for bmh in bmh_data["items"]:
        bmh_name = bmh["metadata"]["name"]
        bmh_mac = bmh["spec"].get("bootMACAddress", "")

        if bmh_mac:
            # Normalize BMH MAC address for comparison
            normalized_bmh_mac = bmh_mac.replace(":", "").replace("-", "").lower()

            if normalized_search_mac == normalized_bmh_mac:
                # Try to find the corresponding node name
                node_name = None

                # Check if there's a consumer ref (Machine) associated with this BMH
                consumer_ref = bmh["spec"].get("consumerRef")
                if consumer_ref and consumer_ref.get("name"):
                    machine_name = consumer_ref["name"]

                    # Try to find the node associated with this machine
                    machine_data = execute_oc_command(
                        ["get", "machine", machine_name, "-n", "openshift-machine-api", "-o", "json"],
                        json_output=True,
                        printer=printer,
                    )
                    if machine_data and machine_data.get("status", {}).get("nodeRef", {}).get("name"):
                        node_name = machine_data["status"]["nodeRef"]["name"]

                if printer:
                    printer.print_success(f"Found BMH '{bmh_name}' with MAC address '{bmh_mac}'")
                    if node_name:
                        printer.print_info(f"Associated node: {node_name}")
                    else:
                        printer.print_warning("No associated node found for this BMH")

                return {
                    "bmh_name": bmh_name,
                    "node_name": node_name,
                    "mac_address": bmh_mac,
                    "machine_name": consumer_ref["name"] if consumer_ref else None,
                }

    if printer:
        printer.print_info(f"No BMH found with MAC address: {mac_address}")
    return None


def cordon_node(node_name, printer=None):
    """
    Cordon a Kubernetes node to prevent new pods from being scheduled.

    Args:
        node_name: Name of the node to cordon
        printer: Printer instance for logging (optional)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if printer:
            printer.print_action(f"Cordoning node: {node_name}")

        result = execute_oc_command(["adm", "cordon", node_name], printer=printer)

        if result is not None:
            if printer:
                printer.print_success(f"Successfully cordoned node: {node_name}")
            return True
        else:
            if printer:
                printer.print_error(f"Failed to cordon node: {node_name}")
            return False

    except Exception as e:
        if printer:
            printer.print_error(f"Exception while cordoning node {node_name}: {e}")
        return False


def drain_node(node_name, ignore_daemonsets=True, delete_emptydir_data=True, printer=None):
    """
    Drain a Kubernetes node to safely evict all pods.

    Args:
        node_name: Name of the node to drain
        ignore_daemonsets: Whether to ignore DaemonSets during drain (default: True)
        delete_emptydir_data: Whether to delete pods with emptyDir volumes (default: True)
        printer: Printer instance for logging (optional)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if printer:
            printer.print_action(f"Draining node: {node_name}")

        drain_cmd = ["adm", "drain", node_name, "--force"]

        if ignore_daemonsets:
            drain_cmd.append("--ignore-daemonsets")

        if delete_emptydir_data:
            drain_cmd.append("--delete-emptydir-data")

        result = execute_oc_command(drain_cmd, printer=printer)

        if result is not None:
            if printer:
                printer.print_success(f"Successfully drained node: {node_name}")
            return True
        else:
            if printer:
                printer.print_error(f"Failed to drain node: {node_name}")
            return False

    except Exception as e:
        if printer:
            printer.print_error(f"Exception while draining node {node_name}: {e}")
        return False


def _get_machineset_data(machineset_name, printer=None):
    """Get MachineSet data and return with replica count."""
    machineset_data = execute_oc_command(
        ["get", "machineset", machineset_name, "-n", "openshift-machine-api", "-o", "json"],
        json_output=True,
        printer=printer,
    )
    if machineset_data:
        current_replicas = machineset_data["spec"].get("replicas", 0)
        return {"machineset_name": machineset_name, "current_replicas": current_replicas}
    return None


def _find_machineset_from_owner_refs(machine_data, printer=None):
    """Check owner references for MachineSet."""
    owner_refs = machine_data.get("metadata", {}).get("ownerReferences", [])
    for owner in owner_refs:
        if owner.get("kind") == "MachineSet":
            machineset_name = owner.get("name")
            if printer:
                printer.print_info(f"Found MachineSet owner reference: {machineset_name}")

            result = _get_machineset_data(machineset_name, printer)
            if result and printer:
                printer.print_success(
                    f"Found actual MachineSet '{machineset_name}' with {result['current_replicas']} replicas"
                )
            return result
    return None


def _find_machineset_from_labels(machine_data, printer=None):
    """Check labels for MachineSet reference."""
    labels = machine_data.get("metadata", {}).get("labels", {})
    machineset_name = labels.get("machine.openshift.io/cluster-api-machineset")

    if not machineset_name:
        return None

    result = _get_machineset_data(machineset_name, printer)
    if result:
        if printer:
            printer.print_success(
                f"Found MachineSet from labels '{machineset_name}' with {result['current_replicas']} replicas"
            )
    elif printer:
        printer.print_warning(f"MachineSet {machineset_name} from labels not found")

    return result


def find_machineset_for_machine(machine_name, printer=None):
    """
    Find the MachineSet that actually manages a specific Machine.

    This function first checks for actual ownership via owner references, then
    falls back to label-based detection only for MachineSet-managed machines.

    Args:
        machine_name: Name of the machine to find the managing MachineSet for
        printer: Printer instance for logging (optional)

    Returns:
        dict or None: {'machineset_name': str, 'current_replicas': int} if found, None if not found
    """
    try:
        # Step 1: Get machine data
        machine_data = execute_oc_command(
            ["get", "machine", machine_name, "-n", "openshift-machine-api", "-o", "json"],
            json_output=True,
            printer=printer,
        )

        if not machine_data:
            if printer:
                printer.print_error(f"Machine {machine_name} not found")
            return None

        # Step 2: Check owner references first (most reliable method)
        result = _find_machineset_from_owner_refs(machine_data, printer)
        if result:
            return result

        # Step 3: Try direct MachineSet reference from labels (backup method)
        result = _find_machineset_from_labels(machine_data, printer)
        if result:
            return result

        # Step 4: Machine is NOT part of any MachineSet (manually created)
        if printer:
            printer.print_info(f"Machine '{machine_name}' is not managed by any MachineSet (manually created)")

        return None

    except Exception as e:
        if printer:
            printer.print_error(f"Failed to find MachineSet for {machine_name}: {e}")
        return None


def annotate_machine_for_deletion(machine_name, printer=None, execute_oc_command=None):
    """
    Annotate a machine with the delete-machine annotation for graceful removal.

    Args:
        machine_name: Name of the machine to annotate
        printer: Printer instance for logging (optional)
        execute_oc_command: Function to execute oc commands

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not printer:
            print("ERROR: printer function not provided")
            return False

        if not execute_oc_command:
            printer.print_error("execute_oc_command function not provided")
            return False

        printer.print_action(f"Annotating machine '{machine_name}' for deletion")

        # Annotate the machine for deletion
        result = execute_oc_command(
            [
                "annotate",
                "machine",
                machine_name,
                "-n",
                "openshift-machine-api",
                "machine.openshift.io/delete-machine=true",
            ],
            printer=printer,
        )

        if result is not None:
            printer.print_success(f"Successfully annotated machine '{machine_name}' for deletion")
            return True
        else:
            printer.print_error(f"Failed to annotate machine '{machine_name}' for deletion")
            return False

    except Exception as e:
        if printer:
            printer.print_error(f"Failed to annotate machine '{machine_name}' for deletion: {e}")
        return False


def scale_down_machineset(machineset_name, printer=None, execute_oc_command=None):
    """
    Scale down a MachineSet by 1 replica.

    This is a wrapper function that maintains backward compatibility while using
    the consolidated scaling logic from ResourceManager.

    Args:
        machineset_name: Name of the MachineSet to scale down
        printer: Printer instance for logging (optional)
        execute_oc_command: Function to execute oc commands

    Returns:
        bool: True if successful, False otherwise
    """
    if not printer:
        print("ERROR: printer function not provided")
        return False

    if not execute_oc_command:
        printer.print_error("execute_oc_command function not provided")
        return False

    # Use ResourceManager's consolidated scaling logic
    from .resource_manager import ResourceManager

    # Create a temporary ResourceManager instance to use the consolidated scaling methods
    resource_manager = ResourceManager(printer=printer, execute_oc_command=execute_oc_command)

    # Delegate to the consolidated scaling method
    return resource_manager.scale_machineset_directly(machineset_name, scale_direction="down")


def find_suitable_machineset(cluster, role, machine_type, printer=None):
    """
    Find a suitable MachineSet for a manually created machine based on cluster, role, and type.

    This is used when a machine was created manually but we still want to scale down
    the appropriate MachineSet to maintain cluster balance.

    Args:
        cluster: Cluster name from machine labels
        role: Machine role (worker, master, etc.)
        machine_type: Machine type
        printer: Printer instance for logging

    Returns:
        dict or None: {'machineset_name': str, 'current_replicas': int} if found, None otherwise
    """
    try:
        if printer:
            printer.print_info(
                f"Searching for MachineSet with cluster='{cluster}', role='{role}', type='{machine_type}'"
            )

        # Get all MachineSets
        machinesets_data = execute_oc_command(
            ["get", "machinesets", "-n", "openshift-machine-api", "-o", "json"], json_output=True, printer=printer
        )

        if not machinesets_data or not machinesets_data.get("items"):
            if printer:
                printer.print_warning("No MachineSets found in cluster")
            return None

        # Find MachineSets that match the machine characteristics
        matching_machinesets = []
        for ms in machinesets_data["items"]:
            ms_labels = ms.get("metadata", {}).get("labels", {})
            ms_cluster = ms_labels.get("machine.openshift.io/cluster-api-cluster")
            ms_role = ms_labels.get("machine.openshift.io/cluster-api-machine-role")
            ms_type = ms_labels.get("machine.openshift.io/cluster-api-machine-type")

            if ms_cluster == cluster and ms_role == role and ms_type == machine_type:
                matching_machinesets.append(ms)
                if printer:
                    printer.print_info(f"Found matching MachineSet: {ms['metadata']['name']}")

        if not matching_machinesets:
            if printer:
                printer.print_warning(
                    f"No MachineSets found matching cluster='{cluster}', role='{role}', type='{machine_type}'"
                )
            return None

        # Use the first matching MachineSet (typically there's only one per role)
        selected_ms = matching_machinesets[0]
        ms_name = selected_ms["metadata"]["name"]
        current_replicas = selected_ms["spec"].get("replicas", 0)

        if printer:
            printer.print_success(f"Found suitable MachineSet: '{ms_name}' with {current_replicas} replicas")

        return {"machineset_name": ms_name, "current_replicas": current_replicas}

    except Exception as e:
        if printer:
            printer.print_error(f"Exception while finding suitable MachineSet: {e}")
        return None


def delete_machine(machine_name, printer=None):
    """
    Delete a Machine resource.

    Args:
        machine_name: Name of the machine to delete
        printer: Printer instance for logging

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if printer:
            printer.print_action(f"Deleting machine '{machine_name}'...")

        execute_oc_command(
            ["delete", "machine", machine_name, "-n", "openshift-machine-api", "--wait=true"], printer=printer
        )

        if printer:
            printer.print_success(f"Successfully deleted machine '{machine_name}'")

        return True

    except Exception as e:
        if printer:
            printer.print_error(f"Failed to delete machine '{machine_name}': {e}")
        return False


def delete_bmh(bmh_name, printer=None):
    """
    Delete a BareMetalHost (BMH) resource.

    Args:
        bmh_name: Name of the BMH to delete
        printer: Printer instance for logging

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if printer:
            printer.print_action(f"Deleting BareMetalHost '{bmh_name}'...")

        execute_oc_command(["delete", "bmh", bmh_name, "-n", "openshift-machine-api", "--wait=true"], printer=printer)

        if printer:
            printer.print_success(f"Successfully deleted BareMetalHost '{bmh_name}'")

        return True

    except Exception as e:
        if printer:
            printer.print_error(f"Failed to delete BareMetalHost '{bmh_name}': {e}")
        return False


def _check_resource_exists(resource_type, resource_name, printer=None):
    """
    Check if a specific resource still exists.

    Args:
        resource_type: Type of resource ('machine' or 'bmh')
        resource_name: Name of the resource
        printer: Optional printer for logging

    Returns:
        bool: True if resource exists, False otherwise
    """
    try:
        result = execute_oc_command(
            ["get", resource_type, resource_name, "-n", "openshift-machine-api", "--no-headers"],
            printer=None,  # Suppress output for polling
        )
        if result and result.strip():
            if printer:
                resource_label = "Machine" if resource_type == "machine" else "BareMetalHost"
                printer.print_info(f"{resource_label} '{resource_name}' still exists, waiting...")
            return True
        return False
    except Exception:
        # Resource doesn't exist - this is what we want
        return False


def _wait_for_resource_deletion(machine_name, bmh_name, max_wait_seconds, printer):
    """
    Wait for resources to be deleted within the specified timeout.

    Args:
        machine_name: Machine name to check (or None)
        bmh_name: BMH name to check (or None)
        max_wait_seconds: Maximum wait time
        printer: Printer for logging

    Returns:
        bool: True if all resources deleted, False if timeout
    """
    import time

    start_time = time.time()

    while time.time() - start_time < max_wait_seconds:
        resources_exist = False

        # Check machine deletion
        if machine_name and _check_resource_exists("machine", machine_name, printer):
            resources_exist = True

        # Check BMH deletion
        if bmh_name and _check_resource_exists("bmh", bmh_name, printer):
            resources_exist = True

        if not resources_exist:
            if printer:
                printer.print_success("All specified resources have been successfully deleted")
            return True

        time.sleep(5)  # Wait 5 seconds before checking again

    return False


def verify_resources_deleted(machine_name=None, bmh_name=None, max_wait_seconds=120, printer=None):
    """
    Verify that machine and/or BMH resources are fully deleted.

    Args:
        machine_name: Name of machine to verify deletion (optional)
        bmh_name: Name of BMH to verify deletion (optional)
        max_wait_seconds: Maximum time to wait for deletion
        printer: Printer instance for logging

    Returns:
        bool: True if all specified resources are deleted, False otherwise
    """
    if not machine_name and not bmh_name:
        return True

    if printer:
        printer.print_action("Verifying resource deletion to prevent MAC address conflicts...")

    success = _wait_for_resource_deletion(machine_name, bmh_name, max_wait_seconds, printer)

    if not success and printer:
        printer.print_error(f"Timeout waiting for resource deletion after {max_wait_seconds} seconds")
        printer.print_warning("Proceeding anyway, but MAC address conflicts may occur")

    return success
