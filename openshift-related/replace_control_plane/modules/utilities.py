#!/usr/bin/env python3
"""Utilities module for OpenShift Control Plane Replacement Tool."""

import json
import subprocess

from .print_manager import printer


def exec_pod_command(
    pod_name,
    command,
    namespace,
    container_name=None,
    discard_stderr=False,
    return_on_error=False,
):
    """
    Execute a command in a pod and return the output.

    Args:
        pod_name: Name of the pod to execute command in
        command: List of command arguments to execute
        namespace: Kubernetes namespace
        container_name: Optional container name (if pod has multiple containers)
        discard_stderr: If True, discard stderr output
        return_on_error: If True, return stdout even when command exits with non-zero code

    Returns:
        Command stdout as string, or None if command failed and return_on_error=False
    """
    try:
        if container_name:
            exec_command = [
                "oc",
                "exec",
                "-n",
                namespace,
                pod_name,
                "-c",
                container_name,
                "--",
                *command,
            ]
        else:
            exec_command = ["oc", "exec", "-n", namespace, pod_name, "--", *command]
        printer.print_action(f"Executing pod command: {' '.join(exec_command)}")
        if discard_stderr:
            result = subprocess.run(
                exec_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        else:
            result = subprocess.run(exec_command, capture_output=True, text=True)
        if result.returncode != 0:
            if not discard_stderr:  # Only print stderr if we're not discarding it
                printer.print_error(f"Command failed: {result.stderr}")
            # Return stdout if explicitly requested, or if stdout contains data
            if return_on_error or (result.stdout and result.stdout.strip()):
                return result.stdout
            return None
        return result.stdout
    except Exception as e:
        printer.print_error(f"Exception during command execution: {e}")
        return None


def execute_oc_command(command, json_output=False):
    """
    Execute an OpenShift CLI command and return the output.

    Args:
        command: List of command arguments to execute (excluding 'oc')
        json_output: If True, add JSON output flag and parse result as JSON

    Returns:
        str or dict: Command output as string, or parsed JSON dict if json_output=True.
                    Returns None on command failure.
    """
    try:
        if json_output:
            exec_command = ["oc", "get", "-o", "json", *command]
        else:
            exec_command = ["oc", *command]
        printer.print_action(f"Executing oc command: {' '.join(exec_command)}")
        result = subprocess.run(exec_command, capture_output=True, text=True)
        if result.returncode != 0:
            printer.print_error(f"Command failed: {result.stderr}")
            return None
        if json_output:
            return json.loads(result.stdout)
        return result.stdout
    except Exception as e:
        printer.print_error(f"Exception during command execution: {e}")
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

    Args:
        None

    Returns:
        str or None: Name of the failed control node, or None if all nodes are ready
    """
    nodes_data = execute_oc_command(["nodes", "-l node-role.kubernetes.io/control-plane"], json_output=True)
    for node in nodes_data["items"]:
        node_name = node["metadata"]["name"]
        node_status = node["status"]["conditions"]
        for condition in node_status:
            if condition["type"] == "Ready" and condition["status"] != "True":
                printer.print_warning(f"Found failed control node: {node_name}")
                return node_name
    return None
