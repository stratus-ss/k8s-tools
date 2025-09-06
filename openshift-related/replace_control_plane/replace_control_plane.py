#!/usr/bin/env python3
"""
OpenShift Control Plane Replacement Tool - Monolithic Version

This monolithic version contains all components in a single file for easy distribution.
Generated automatically from modular components on 2025-09-05 15:17:54.

For development, use the modular version in modules/ directory.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import time
from typing import Any, Callable, Dict, Optional, Tuple

import yaml


# === PRINT_MANAGER MODULE ===


# Global debug flag
DEBUG_MODE = False


class PrintManager:

    @staticmethod
    def print_header(message):
        print(f"\n{'=' * 60}")
        print(f" {message.upper()}")
        print(f"{'=' * 60}")

    @staticmethod
    def print_info(message):
        print(f"    [INFO]  {message}")

    @staticmethod
    def print_success(message):
        print(f"    [✓]     {message}")

    @staticmethod
    def print_warning(message):
        print(f"    [⚠️]     {message}")

    @staticmethod
    def print_error(message):
        print(f"    [✗]     {message}")

    @staticmethod
    def print_step(step_num, total_steps, message):
        print(f"[{step_num}/{total_steps}] {message}")

    @staticmethod
    def print_action(message):
        if DEBUG_MODE:
            print(f"    [ACTION] {message}")


# Create a global print manager instance for convenience
printer = PrintManager()


# === UTILITIES MODULE ===


# from typing import Optional, Tuple


def _build_exec_command(pod_name: str, command: list, namespace: str, container_name: Optional[str] = None) -> list:
    if container_name:
        return ["oc", "exec", "-n", namespace, pod_name, "-c", container_name, "--", *command]
    else:
        return ["oc", "exec", "-n", namespace, pod_name, "--", *command]


def _run_pod_command(exec_command: list, discard_stderr: bool) -> subprocess.CompletedProcess:
    if discard_stderr:
        return subprocess.run(exec_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=30)
    else:
        return subprocess.run(exec_command, capture_output=True, text=True, timeout=30)


def _handle_command_result(
    result: subprocess.CompletedProcess, discard_stderr: bool, return_on_error: bool
) -> Tuple[bool, Optional[str], Optional[str]]:
    if result.returncode == 0:
        return True, result.stdout, None

    stderr = result.stderr if not discard_stderr else "Command failed with non-zero exit code"
    stdout_result: Optional[str] = None

    if return_on_error or (result.stdout and result.stdout.strip()):
        stdout_result = result.stdout

    return False, stdout_result, stderr


def _should_retry_error(attempt: int, max_retries: int, error_msg: str) -> bool:
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
    if not printer:
        return
    if attempt == 0:
        printer.print_action(f"Executing oc command: {' '.join(exec_command)}")
    else:
        printer.print_info(f"Retry attempt {attempt}/{max_retries}: {' '.join(exec_command)}")


def _handle_command_success(result, json_output, attempt, printer):
    if attempt > 0 and printer:
        printer.print_success(f"Command succeeded on retry attempt {attempt}")
    if json_output:
        return json.loads(result.stdout)
    return result.stdout.strip()


def _handle_command_failure(result, attempt, max_retries, retry_delay, printer):
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
    if not printer:
        print("ERROR: printer function not provided")
        return False

    if not execute_oc_command:
        printer.print_error("execute_oc_command function not provided")
        return False

    # Use ResourceManager's consolidated scaling logic

    # Create a temporary ResourceManager instance to use the consolidated scaling methods
    resource_manager = ResourceManager(printer=printer, execute_oc_command=execute_oc_command)

    # Delegate to the consolidated scaling method
    return resource_manager.scale_machineset_directly(machineset_name, scale_direction="down")


def find_suitable_machineset(cluster, role, machine_type, printer=None):
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
    if not machine_name and not bmh_name:
        return True

    if printer:
        printer.print_action("Verifying resource deletion to prevent MAC address conflicts...")

    success = _wait_for_resource_deletion(machine_name, bmh_name, max_wait_seconds, printer)

    if not success and printer:
        printer.print_error(f"Timeout waiting for resource deletion after {max_wait_seconds} seconds")
        printer.print_warning("Proceeding anyway, but MAC address conflicts may occur")

    return success


# === BACKUP_MANAGER MODULE ===


class BackupManager:

    def __init__(self, backup_dir=None, printer=None, execute_oc_command=None):
        self.backup_dir = backup_dir
        self.cluster_name = None
        self.printer = printer
        self.execute_oc_command = execute_oc_command

    def setup_backup_directory(self, backup_dir=None):
        # Determine backup directory path
        if backup_dir:
            self.backup_dir = backup_dir
        elif not self.backup_dir:
            # Get cluster name from OpenShift DNS
            cluster_cmd = ["get", "dns", "cluster", "-o", "jsonpath='{.spec.baseDomain}'"]
            cluster_output = self.execute_oc_command(cluster_cmd)
            if cluster_output:
                self.cluster_name = cluster_output.strip("'")
            else:
                self.printer.print_error("Failed to retrieve cluster name from OpenShift DNS")
                self.cluster_name = "unknown-cluster"
            self.backup_dir = f"/home/{os.getenv('USER', 'unknown')}/backup_yamls/{self.cluster_name}"

        self.printer.print_info(f"Backup directory: {self.backup_dir}")

        # Create directory if it doesn't exist
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
            self.printer.print_success(f"Created backup directory: {self.backup_dir}")
        else:
            self.printer.print_info(f"Using existing backup directory: {self.backup_dir}")

        return self.backup_dir

    def make_file_copy(self, current_file_path, new_file_path):
        with open(current_file_path, "r") as f:
            with open(new_file_path, "w") as f_new:
                f_new.write(f.read())

    def sanitize_metadata(self, data):
        metadata_keys_to_remove = [
            "creationTimestamp",
            "resourceVersion",
            "uid",
            "ownerReferences",
            "annotations",
            "managedFields",
            "finalizers",
        ]
        if "metadata" in data:
            for key in metadata_keys_to_remove:
                data["metadata"].pop(key, None)  # pop with None default won't raise KeyError
        return data

    def extract_bmh_fields(self, bmh_data):
        extracted = {
            "apiVersion": bmh_data.get("apiVersion"),
            "kind": bmh_data.get("kind"),
            "metadata": {
                "name": bmh_data.get("metadata", {}).get("name"),
                "namespace": bmh_data.get("metadata", {}).get("namespace"),
            },
            "spec": {
                "automatedCleaningMode": bmh_data.get("spec", {}).get("automatedCleaningMode"),
                "bmc": {
                    "address": bmh_data.get("spec", {}).get("bmc", {}).get("address"),
                    "credentialsName": bmh_data.get("spec", {}).get("bmc", {}).get("credentialsName"),
                    "disableCertificateVerification": bmh_data.get("spec", {})
                    .get("bmc", {})
                    .get("disableCertificateVerification"),
                },
                "bootMACAddress": bmh_data.get("spec", {}).get("bootMACAddress"),
                "bootMode": bmh_data.get("spec", {}).get("bootMode"),
                "externallyProvisioned": bmh_data.get("spec", {}).get("externallyProvisioned"),
                "online": bmh_data.get("spec", {}).get("online"),
                "rootDeviceHints": {
                    "deviceName": bmh_data.get("spec", {}).get("rootDeviceHints", {}).get("deviceName")
                },
                "preprovisioningNetworkDataName": bmh_data.get("spec", {}).get("preprovisioningNetworkDataName"),
                "userData": {
                    "name": bmh_data.get("spec", {}).get("userData", {}).get("name"),
                    "namespace": bmh_data.get("spec", {}).get("userData", {}).get("namespace"),
                },
            },
        }
        return extracted

    def extract_machine_fields(self, machine_data):
        extracted = {
            "apiVersion": machine_data.get("apiVersion"),
            "kind": machine_data.get("kind"),
            "metadata": {
                "labels": machine_data.get("metadata", {}).get("labels", {}),
                "name": "PLACEHOLDER_NAME",  # Will be updated by node configurator
                "namespace": machine_data.get("metadata", {}).get("namespace"),
            },
            "spec": {
                "lifecycleHooks": machine_data.get("spec", {}).get("lifecycleHooks"),
                "providerSpec": {
                    "value": {
                        "apiVersion": machine_data.get("spec", {})
                        .get("providerSpec", {})
                        .get("value", {})
                        .get("apiVersion"),
                        "customDeploy": machine_data.get("spec", {})
                        .get("providerSpec", {})
                        .get("value", {})
                        .get("customDeploy"),
                        "image": machine_data.get("spec", {}).get("providerSpec", {}).get("value", {}).get("image"),
                        "kind": machine_data.get("spec", {}).get("providerSpec", {}).get("value", {}).get("kind"),
                        "userData": machine_data.get("spec", {})
                        .get("providerSpec", {})
                        .get("value", {})
                        .get("userData"),
                    }
                },
            },
        }
        return extracted

    def backup_bmh_definition(self, bmh_name, bmh_data):
        extracted_bmh = self.extract_bmh_fields(bmh_data)
        backup_file = f"{self.backup_dir}/{bmh_name}_bmh.yaml"
        with open(backup_file, "w") as f:
            yaml.dump(extracted_bmh, f, default_flow_style=False)
        return backup_file

    def backup_machine_definition(self, machine_name, machine_data):
        extracted_machine = self.extract_machine_fields(machine_data)
        backup_file = f"{self.backup_dir}/{machine_name}_machine.yaml"
        with open(backup_file, "w") as f:
            yaml.dump(extracted_machine, f, default_flow_style=False)
        return backup_file

    def backup_secret(self, node_name, secret_suffix, backup_filename_suffix, secret_description):
        secret_name = f"{node_name}-{secret_suffix}"
        secret_json = self.execute_oc_command(
            ["get", "secret", "-n", "openshift-machine-api", secret_name, "-o", "json"],
            json_output=True,
            printer=self.printer,
        )
        if not secret_json:
            raise Exception(f"Failed to retrieve {secret_description} for {node_name}")

        secret_json_sanitized = self.sanitize_metadata(secret_json)
        backup_file = f"{self.backup_dir}/{node_name}{backup_filename_suffix}"
        with open(backup_file, "w") as f:
            yaml.dump(secret_json_sanitized, f)
        return backup_file

    def extract_nmstate_config(self, node_name):
        self.execute_oc_command(
            [
                "extract",
                "-n",
                "openshift-machine-api",
                f"secret/{node_name}-network-config-secret",
                "--to",
                self.backup_dir,
            ]
        )
        nmstate_file = f"{self.backup_dir}/{node_name}_nmstate"
        os.rename(f"{self.backup_dir}/nmstate", nmstate_file)
        return nmstate_file

    def copy_files_for_replacement(self, bad_node, bmh_name, bad_machine, replacement_node):
        # Define file copy operations: (dict_key, source_node, dest_suffix, source_suffix)
        file_operations = [
            ("nmstate", bad_node, "_nmstate", "_nmstate"),
            ("bmc_secret", bad_node, "-bmc-secret.yaml", "-bmc-secret.yaml"),
            ("bmh", bmh_name, "_bmh.yaml", "_bmh.yaml"),
            ("network_secret", bad_node, "_network-config-secret.yaml", "_network-config-secret.yaml"),
            ("machine", bad_machine, "_machine.yaml", "_machine.yaml"),
        ]

        files = {}
        for dict_key, source_node, dest_suffix, source_suffix in file_operations:
            # Define destination and source paths
            dest_path = f"{self.backup_dir}/{replacement_node}{dest_suffix}"
            source_path = f"{self.backup_dir}/{source_node}{source_suffix}"

            # Perform the copy operation
            self.make_file_copy(source_path, dest_path)
            files[dict_key] = dest_path

        return files

    def backup_template_bmh(self, failed_control_node=None, is_control_plane_expansion=False):

        if failed_control_node:
            # Control plane replacement: backup the specific failed node's BMH
            self.printer.print_action(f"Backing up BMH for failed control node: {failed_control_node}")
            bmh_data = self.execute_oc_command(
                ["get", "bmh", failed_control_node, "-n", "openshift-machine-api", "-o", "json"],
                json_output=True,
                printer=self.printer,
            )
            if not bmh_data:
                self.printer.print_error(f"Failed to retrieve BMH data for: {failed_control_node}")
                return None, False
            if not bmh_data:
                self.printer.print_error(f"Could not retrieve BMH data for: {failed_control_node}")
                return None, False

            backup_file_path = self.backup_bmh_definition(failed_control_node, bmh_data)
            self.printer.print_success(f"Control plane BMH backup saved: {backup_file_path}")
            return backup_file_path, False  # Not a worker template

        else:
            # Worker addition or control plane expansion: find appropriate template
            operation_type = "control plane expansion" if is_control_plane_expansion else "worker addition"
            try:
                bmh_json = self.execute_oc_command(
                    ["get", "bmh", "-n", "openshift-machine-api", "-o", "json"], json_output=True, printer=self.printer
                )
                if not bmh_json:
                    raise Exception("Failed to retrieve BMH list from cluster")

                if not bmh_json.get("items"):
                    self.printer.print_error("No BMH resources found in cluster")
                    return None, False

                # Find appropriate templates by role
                worker_bmh = None
                control_plane_bmh = None

                for bmh in bmh_json["items"]:
                    labels = bmh.get("metadata", {}).get("labels", {})
                    role = labels.get("installer.openshift.io/role", "unknown")

                    if role == "worker" and not worker_bmh:
                        worker_bmh = bmh
                    elif role == "control-plane" and not control_plane_bmh:
                        control_plane_bmh = bmh

                # Select template based on operation type
                if is_control_plane_expansion:
                    # For control plane expansion, prefer control plane template
                    selected_bmh = control_plane_bmh or worker_bmh
                    if not selected_bmh:
                        self.printer.print_error("No suitable control plane BMH template found")
                        return None, False
                    template_type = "control plane" if control_plane_bmh else "worker (fallback)"
                else:
                    # For worker addition, prefer worker template
                    selected_bmh = worker_bmh or control_plane_bmh
                    if not selected_bmh:
                        self.printer.print_error("No suitable BMH template found")
                        return None, False
                    template_type = "worker" if worker_bmh else "control plane (fallback)"

                template_bmh_name = selected_bmh["metadata"]["name"]
                is_worker_template = (
                    selected_bmh.get("metadata", {}).get("labels", {}).get("installer.openshift.io/role") == "worker"
                )

                self.printer.print_info(f"Using {template_type} BMH template for {operation_type}: {template_bmh_name}")
                backup_file_path = self.backup_bmh_definition(template_bmh_name, selected_bmh)
                self.printer.print_success(f"Template BMH backup saved: {backup_file_path}")
                return backup_file_path, is_worker_template

            except Exception as e:
                self.printer.print_error(f"Error finding and backing up template BMH: {e}")
                return None, False


# === NODE_CONFIGURATOR MODULE ===


# from typing import Optional


class NodeConfigurator:

    def __init__(self) -> None:
        pass

    def update_nmstate_ip(self, nmstate_file_path: str, new_ip_address: str) -> None:
        try:
            # Load the nmstate YAML file
            with open(nmstate_file_path, "r") as f:
                nmstate_data = yaml.safe_load(f)
            # Find and update the IP address in interfaces
            if "interfaces" in nmstate_data:
                for interface in nmstate_data["interfaces"]:
                    if interface.get("ipv4", {}).get("enabled") and interface.get("ipv4", {}).get("address"):
                        # Update the first IP address found (typically the main interface IP)
                        if len(interface["ipv4"]["address"]) > 0:
                            interface["ipv4"]["address"][0]["ip"] = new_ip_address
                            printer.print_info(
                                f"Updated interface '{interface.get('name', 'unknown')}' IP to: {new_ip_address}"
                            )
                            break
            # Write the updated YAML back to the file
            with open(nmstate_file_path, "w") as f:
                yaml.dump(nmstate_data, f, default_flow_style=False)
            printer.print_success(f"Updated IP address in {nmstate_file_path}")
        except Exception as e:
            printer.print_error(f"Failed to update IP in {nmstate_file_path}: {e}")

    def update_network_secret(
        self, base64_file_path: str, network_config_secret_file_path: str, replacement_node: str
    ) -> None:
        with open(base64_file_path, "r") as f:
            data = f.read()
        base64_data = base64.b64encode(data.encode()).decode()
        with open(network_config_secret_file_path, "r") as f:
            network_config_secret_data = yaml.safe_load(f)
        network_config_secret_data["data"]["nmstate"] = base64_data
        network_config_secret_data["metadata"]["name"] = f"{replacement_node}-network-config-secret"
        with open(network_config_secret_file_path, "w") as f:
            yaml.dump(network_config_secret_data, f, default_flow_style=False)

    def update_bmc_secret_name(self, bmc_secret_file_path: str, replacement_node: str) -> None:
        with open(bmc_secret_file_path, "r") as f:
            bmc_secret_data = yaml.safe_load(f)
        bmc_secret_data["metadata"]["name"] = f"{replacement_node}-bmc-secret"
        with open(bmc_secret_file_path, "w") as f:
            yaml.dump(bmc_secret_data, f, default_flow_style=False)

    def update_bmh(
        self,
        bmh_file_path: str,
        replacement_node_bmc_ip: str,
        replacement_node_mac_address: str,
        replacement_node: str,
        sushy_uid: Optional[str] = None,
        role: Optional[str] = None,
    ) -> None:
        try:
            with open(bmh_file_path, "r") as f:
                bmh_data = yaml.safe_load(f)
            # Get current BMC address
            current_address = bmh_data["spec"]["bmc"]["address"]
            # Use regex to find and replace IP address pattern (xxx.xxx.xxx.xxx)
            # Regex provided by cursor.ai
            ip_pattern = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
            # Replace the IP address in the address string
            new_address = re.sub(ip_pattern, replacement_node_bmc_ip, current_address)

            # If sushy_uid is provided, also replace the UID after Systems/
            # sushy uid replacement by cursor.ai
            if sushy_uid:
                # Find the position after Systems/ and replace everything to the end
                systems_pos = new_address.find("Systems/")
                if systems_pos != -1:
                    base_url = new_address[: systems_pos + len("Systems/")]
                    new_address = base_url + sushy_uid
                    printer.print_info(f"Updated sushy UID to: {sushy_uid}")
                else:
                    printer.print_warning("Systems/ pattern not found in BMC address, sushy UID not updated")

            bmh_data["spec"]["bmc"]["address"] = new_address
            bmh_data["spec"]["bootMACAddress"] = replacement_node_mac_address
            bmh_data["spec"]["preprovisioningNetworkDataName"] = f"{replacement_node}-network-config-secret"
            bmh_data["metadata"]["name"] = replacement_node
            # Update the BMC credentialsName to match the replacement node's secret name
            bmh_data["spec"]["bmc"]["credentialsName"] = f"{replacement_node}-bmc-secret"
            printer.print_info(f"Updated BMC credentialsName to: {replacement_node}-bmc-secret")

            # Handle role labels based on node type
            if "metadata" not in bmh_data:
                bmh_data["metadata"] = {}
            if "labels" not in bmh_data["metadata"]:
                bmh_data["metadata"]["labels"] = {}

            # Ensure userData section exists
            if "userData" not in bmh_data["spec"]:
                bmh_data["spec"]["userData"] = {}

            # Handle different roles (labels and userData configuration)
            if role == "worker":
                # For workers: remove all role-related labels to avoid conflicts
                bmh_data["metadata"]["labels"].pop("installer.openshift.io/role", None)
                bmh_data["metadata"]["labels"].pop("node-role.kubernetes.io/control-plane", None)
                bmh_data["metadata"]["labels"].pop("node-role.kubernetes.io/master", None)
                printer.print_success("Removed all role labels for worker node")

                # Set worker userData
                bmh_data["spec"]["userData"]["name"] = "worker-user-data-managed"
                bmh_data["spec"]["userData"]["namespace"] = "openshift-machine-api"
                printer.print_success("Set BMH userData to worker-user-data-managed")
            else:
                # For control plane: ensure control-plane role label exists
                bmh_data["metadata"]["labels"]["installer.openshift.io/role"] = "control-plane"
                printer.print_success("Ensured control-plane role label is present")

                # For control plane, use master userData (maintain existing behavior if any)
                if bmh_data["spec"]["userData"].get("name"):
                    # Keep existing userData name for control plane
                    printer.print_info(f"Keeping existing BMH userData: {bmh_data['spec']['userData']['name']}")
                else:
                    # Set default for control plane if none exists
                    bmh_data["spec"]["userData"]["name"] = "master-user-data-managed"
                    bmh_data["spec"]["userData"]["namespace"] = "openshift-machine-api"
                    printer.print_success("Set BMH userData to master-user-data-managed")

            with open(bmh_file_path, "w") as f:
                yaml.dump(bmh_data, f, default_flow_style=False)
            printer.print_info(f"Updated BMC IP from '{current_address}' to '{new_address}'")
        except Exception as e:
            printer.print_error(f"Failed to update BMC IP in {bmh_file_path}: {e}")

    def update_machine_yaml(
        self,
        machine_file_path: str,
        replacement_node: str,
        replacement_node_role: Optional[str] = None,
        execute_oc_command=None,
        printer=None,
    ) -> None:
        try:
            with open(machine_file_path, "r") as f:
                machine_data = yaml.safe_load(f)

            # Set default role to master if not provided
            role = replacement_node_role if replacement_node_role else "master"

            # Extract cluster name from existing machine name or labels
            current_name = machine_data["metadata"]["name"]
            if current_name == "PLACEHOLDER_NAME":
                # For expansion scenarios, extract cluster name from machine labels
                cluster_name = machine_data["metadata"]["labels"].get("machine.openshift.io/cluster-api-cluster")
                if not cluster_name:
                    raise ValueError("Cannot determine cluster name - no cluster label found in machine template")
                printer.print_info(f"Using cluster name '{cluster_name}' from machine labels")
            else:
                # Extract from existing machine name (e.g., "one-zpspd" from "one-zpspd-master-4")
                cluster_name = current_name.split("-")[0] + "-" + current_name.split("-")[1]
                printer.print_info(f"Extracted cluster name '{cluster_name}' from existing machine name")

            # Extract number from replacement_node (handles both simple names and FQDNs)
            node_number_match = re.search(r"(\d+)", replacement_node)
            if node_number_match:
                node_number = node_number_match.group(1)
                printer.print_info(f"Extracted node number '{node_number}' from replacement_node '{replacement_node}'")
            else:
                printer.print_warning(f"Could not extract number from replacement_node '{replacement_node}', using '0'")
                node_number = "0"

            machine_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] = role
            machine_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-type"] = role

            # Generate machine name and ensure it's unique
            proposed_name = f"{cluster_name}-{role}-{node_number}"
            if printer:
                printer.print_info(f"Initial proposed machine name: '{proposed_name}'")

            if execute_oc_command and printer:
                printer.print_info("Checking machine name uniqueness...")
                final_name = self._ensure_unique_machine_name(proposed_name, execute_oc_command, printer)
            else:
                # Fallback if execute_oc_command not provided
                final_name = proposed_name
                if printer:
                    printer.print_warning("Cannot verify machine name uniqueness - execute_oc_command not provided")
                    printer.print_info(f"Using proposed machine name: '{proposed_name}'")

            if printer:
                printer.print_info(f"Final machine name selected: '{final_name}'")
            machine_data["metadata"]["name"] = final_name

            # Handle lifecycle hooks based on role
            if role != "master":
                # Remove lifecycle hooks for non-master nodes
                machine_data["spec"].pop("lifecycleHooks", None)
                printer.print_info(f"Removed lifecycle hooks for {role} node")
            else:
                # Ensure lifecycle hooks exist for master nodes
                if "lifecycleHooks" not in machine_data["spec"]:
                    machine_data["spec"]["lifecycleHooks"] = {
                        "preDrain": [{"name": "EtcdQuorumOperator", "owner": "clusteroperator/etcd"}]
                    }
                    printer.print_info("Added lifecycle hooks for master node")

            # Update userData name based on role
            if role == "master":
                user_data_name = "master-user-data-managed"
            elif role == "worker":
                user_data_name = "worker-user-data-managed"
            else:
                # For other roles (like infrastructure), default to worker userData
                user_data_name = "worker-user-data-managed"
                printer.print_info(f"Using worker userData for role '{role}'")

            machine_data["spec"]["providerSpec"]["value"]["userData"]["name"] = user_data_name

            with open(machine_file_path, "w") as f:
                yaml.dump(machine_data, f, default_flow_style=False)

            printer.print_info("Updated machine configuration:")
            printer.print_info(f"  - Name: {machine_data['metadata']['name']}")
            printer.print_info(f"  - Role: {role}")
            printer.print_info(f"  - UserData: {user_data_name}")
            printer.print_info(
                f"  - LifecycleHooks: {'present' if 'lifecycleHooks' in machine_data['spec'] else 'removed'}"
            )

        except Exception as e:
            printer.print_error(f"Failed to update machine YAML {machine_file_path}: {e}")

    def _ensure_unique_machine_name(self, proposed_name: str, execute_oc_command, printer) -> str:
        try:
            # Get all existing machines using JSON output for reliable parsing
            machines_data = execute_oc_command(
                ["get", "machines", "-n", "openshift-machine-api", "-o", "json"],
                json_output=True,
                printer=None,  # Don't log this check
            )

            # Extract cluster name and role from proposed name
            parts = proposed_name.split("-")
            if len(parts) >= 3:
                cluster_name = "-".join(parts[:-2])  # Everything except role and number
                role = parts[-2]

                # Find all existing numbers for this cluster/role combination
                existing_numbers = set()
                if machines_data and machines_data.get("items"):
                    printer.print_info(f"Scanning existing machines for cluster '{cluster_name}', role '{role}'")

                    for machine in machines_data["items"]:
                        machine_name = machine["metadata"]["name"]

                        # Check if this machine matches our cluster and role
                        if machine_name.startswith(f"{cluster_name}-{role}-"):
                            try:
                                # Extract the number from the machine name
                                num_str = machine_name.split("-")[-1]
                                number = int(num_str)
                                existing_numbers.add(number)
                                printer.print_info(
                                    f"Found existing {role} machine number: {number} (name: {machine_name})"
                                )
                            except (ValueError, IndexError):
                                printer.print_warning(f"Could not parse machine number from: {machine_name}")
                                continue

                    printer.print_info(f"Existing {role} machine numbers: {sorted(existing_numbers)}")

                # Find the lowest available number (filling gaps first)
                next_number = 0
                while next_number in existing_numbers:
                    next_number += 1

                unique_name = f"{cluster_name}-{role}-{next_number}"

                if unique_name != proposed_name:
                    printer.print_info(f"Using lowest available machine number: {next_number}")
                    printer.print_info(f"Generated optimal machine name: '{unique_name}'")
                else:
                    printer.print_info(f"Proposed machine name '{proposed_name}' is optimal")

                return unique_name

            # Fallback if we can't parse the name properly
            printer.print_info(f"Using proposed machine name: '{proposed_name}'")
            return proposed_name

        except Exception as e:
            printer.print_warning(f"Could not verify machine name uniqueness: {e}")
            printer.print_info(f"Proceeding with proposed name: '{proposed_name}'")
            return proposed_name


# === ARGUMENTS_PARSER MODULE ===


class ArgumentsParser:

    @staticmethod
    def parse_arguments():
        parser = argparse.ArgumentParser(description="Replace the control plane in a Kubernetes cluster")

        parser.add_argument(
            "--backup_dir",
            type=str,
            required=False,
            help="The full path to the backup directory",
        )
        parser.add_argument(
            "--replacement_node",
            type=str,
            required=True,
            help="The name of the replacement node",
        )
        parser.add_argument(
            "--replacement_node_ip",
            type=str,
            required=True,
            help="The IP address of the replacement node",
        )
        parser.add_argument(
            "--replacement_node_bmc_ip",
            type=str,
            required=True,
            help="The IP address of the replacement node's BMC",
        )
        parser.add_argument(
            "--replacement_node_mac_address",
            type=str,
            required=True,
            help="The MAC address of the replacement node",
        )
        parser.add_argument(
            "--replacement_node_role",
            type=str,
            required=True,
            help="The role of the replacement node (master/control for control plane, worker, infrastructure)",
        )
        parser.add_argument(
            "--add_new_node",
            action="store_true",
            help="Add a new node to the OpenShift cluster",
        )
        parser.add_argument(
            "--sushy_uid",
            type=str,
            required=False,
            default=None,
            help="Optional: The sushy UID to replace in the BMC address (UUID after Systems/ in redfish URL)",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Enable debug output (shows command execution details)",
        )
        parser.add_argument(
            "--skip-etcd",
            action="store_true",
            help="Skip ETCD member removal and secret cleanup (use when ETCD operations already completed)",
        )
        parser.add_argument(
            "--expand-control-plane",
            action="store_true",
            help="Add a new control plane node (expansion) rather than replacing a failed one",
        )

        args = parser.parse_args()

        # Set global debug mode
        print_manager.DEBUG_MODE = args.debug

        return args


# === RESOURCE_MONITOR MODULE ===


class ResourceMonitor:

    def __init__(
        self,
        replacement_node,
        backup_dir,
        timeout_minutes=45,
        check_interval=25,
        is_addition=False,
        is_expansion=False,
        printer=None,
        execute_oc_command=None,
    ):
        self.replacement_node = replacement_node
        self.backup_dir = backup_dir
        self.timeout_seconds = timeout_minutes * 60
        self.check_interval = check_interval
        self.is_addition = is_addition
        self.is_expansion = is_expansion
        self.start_time = None
        self.printer = printer
        self.execute_oc_command = execute_oc_command

        # Phase tracking
        self.bmh_provisioned = False
        self.machine_created = False
        self.machine_running = False
        self.node_ready = False
        self.target_machine_name = None

        # CSR checking tracking
        self.machine_monitor_start_time = None
        self.csr_checking_enabled = False
        self.csr_check_delay_seconds = 10 * 60  # 10 minutes

    def monitor_provisioning_sequence(self):
        self.printer.print_info("Starting automated 4-phase provisioning sequence...")
        self.printer.print_info(f"Monitoring BMH: {self.replacement_node}")

        self.start_time = time.time()

        while not self.node_ready and not self._is_timeout_reached():
            self._print_progress()

            if not self.bmh_provisioned:
                self._monitor_bmh_status()
            elif not self.machine_created:
                if self.is_addition:
                    # For worker additions, MachineSet creates machine automatically - discover it
                    self._discover_machine_for_worker_addition()
                else:
                    # For control plane operations (both replacement and expansion),
                    # machine was already applied in previous step - just discover it
                    self._discover_machine_for_control_plane()
            elif not self.machine_running:
                self._monitor_machine_status()
            else:
                self._monitor_node_and_csrs()

            # Wait before next check (unless node is ready)
            if not self.node_ready:
                time.sleep(self.check_interval)

        return self._get_final_status()

    def _monitor_bmh_status(self):
        bmh_data = self.execute_oc_command(
            ["get", "bmh", self.replacement_node, "-n", "openshift-machine-api", "-o", "json"], json_output=True
        )
        if bmh_data:
            # Extract BMH state from JSON structure
            bmh_status = bmh_data.get("status", {}).get("provisioning", {}).get("state", "Unknown")

            if bmh_status == "provisioned":
                self.bmh_provisioned = True
                self.printer.print_success(f"BMH {self.replacement_node} is now Provisioned!")
                self.printer.print_success("BMH is ready for machine binding")
            elif bmh_status in ["provisioning", "ready", "available"]:
                self.printer.print_info(
                    f"BMH {self.replacement_node} is {bmh_status}, waiting for Provisioned status..."
                )
            elif bmh_status == "error":
                self.printer.print_error(
                    f"BMH {self.replacement_node} is in error state - manual intervention required"
                )
            else:
                self.printer.print_info(f"BMH {self.replacement_node} status: {bmh_status}, continuing to monitor...")
        else:
            self.printer.print_info(f"BMH {self.replacement_node} not found yet, waiting for it to appear...")

    def _discover_machine_for_worker_addition(self):
        self.printer.print_info("BMH is provisioned, looking for machine created by MachineSet...")

        # Try to get machine name from BMH consumerRef
        if not self.target_machine_name:
            self.target_machine_name = self._get_machine_name_from_bmh_consumerref()

        if self.target_machine_name:
            self.machine_created = True
            self.machine_monitor_start_time = time.time()
            self.printer.print_success(f"Machine discovered: {self.target_machine_name}")
            self.printer.print_info("MachineSet has successfully created the machine, now monitoring status...")
            self.printer.print_info(
                "Note: CSR checking will begin automatically if machine doesn't reach Provisioned state within 10 minutes"
            )
        else:
            self.printer.print_info("Waiting for MachineSet to create machine and update BMH consumerRef...")

    def _discover_machine_for_control_plane(self):
        self.printer.print_success("BMH is provisioned, now looking for applied machine...")

        # Try to get machine name from BMH consumerRef
        if not self.target_machine_name:
            self.target_machine_name = self._get_machine_name_from_bmh_consumerref()

        if self.target_machine_name:
            self.machine_created = True
            self.machine_monitor_start_time = time.time()
            self.printer.print_success(f"Machine discovered: {self.target_machine_name}")
            self.printer.print_info("Machine was successfully applied earlier, now monitoring status...")
            self.printer.print_info(
                "Note: CSR checking will begin automatically if machine doesn't reach Provisioned state within 10 minutes"
            )
        else:
            self.printer.print_info("Waiting for applied machine to bind to BMH...")

    def _get_machine_info(self):
        machines_data = self.execute_oc_command(
            ["get", "machines", "-n", "openshift-machine-api", "-o", "json"], json_output=True
        )
        machine_phase = None

        if machines_data and machines_data.get("items"):
            if not self.target_machine_name:
                # Try to get machine name from BMH consumerRef first (most reliable)
                self.target_machine_name = self._get_machine_name_from_bmh_consumerref()

                # Fallback to node number matching if BMH consumerRef not available yet
                if not self.target_machine_name:
                    self.target_machine_name = self._find_target_machine_name(machines_data["items"])

            if self.target_machine_name:
                # Find the specific machine in the data we already have
                for machine in machines_data["items"]:
                    if machine["metadata"]["name"] == self.target_machine_name:
                        machine_phase = machine.get("status", {}).get("phase", "Unknown")
                        break

        return machines_data, machine_phase

    def _handle_csr_timing_logic(self, machine_phase):
        if self.csr_checking_enabled or not self.machine_monitor_start_time:
            return

        machine_elapsed = time.time() - self.machine_monitor_start_time
        early_csr_threshold = 3 * 60  # 3 minutes

        if machine_elapsed >= self.csr_check_delay_seconds:
            # Original 10-minute logic
            self.csr_checking_enabled = True
            self.printer.print_info("⏰ 10 minutes elapsed - Now checking for CSRs while monitoring machine status...")
        elif machine_elapsed >= early_csr_threshold and machine_phase == "Provisioning":
            # Early CSR checking if machine appears stuck in provisioning
            self.csr_checking_enabled = True
            self.printer.print_info("🔧 Machine stuck in Provisioning for 3+ minutes - Starting early CSR checking...")

    def _process_machine_phase(self, machine_phase):
        csr_status = " (CSR checking active)" if self.csr_checking_enabled else ""
        self.printer.print_info(f"Machine {self.target_machine_name} phase: {machine_phase}{csr_status}")

        if machine_phase == "Running":
            self.machine_running = True
            self.printer.print_success(f"Machine {self.target_machine_name} is now Running!")
            self.printer.print_success("Machine is ready, now monitoring for node and CSRs...")
        elif machine_phase in ["Provisioning", "Provisioned"]:
            wait_msg = f"Machine {self.target_machine_name} is {machine_phase}, waiting for Running state..."
            if self.csr_checking_enabled:
                wait_msg += " (CSRs being checked and approved as needed)"
            self.printer.print_info(wait_msg)
        elif machine_phase == "Failed":
            self.printer.print_error(
                f"Machine {self.target_machine_name} is in Failed state - manual intervention required"
            )
        else:
            message = f"Machine {self.target_machine_name} phase: {machine_phase}, continuing to monitor..."
            self.printer.print_info(f"{message}{csr_status}")

    def _handle_machine_not_found(self, machines_data):
        has_machines = machines_data and machines_data.get("items")

        if has_machines and self.target_machine_name:
            self.printer.print_info(f"Machine {self.target_machine_name} not found, continuing to monitor...")
        elif has_machines:
            node_number_match = re.search(r"(\d+)", self.replacement_node)
            node_num = node_number_match.group(1) if node_number_match else "unknown"
            self.printer.print_info(f"Looking for machine with node number {node_num}...")
        else:
            self.printer.print_info("No machines found yet, waiting for machine to appear...")

    def _monitor_machine_status(self):
        # Get machine information
        machines_data, machine_phase = self._get_machine_info()

        # Handle CSR checking timing logic
        self._handle_csr_timing_logic(machine_phase)

        # Check for pending CSRs if enabled
        if self.csr_checking_enabled:
            self._approve_pending_csrs()

        # Process machine status and show progress
        if machines_data and machines_data.get("items") and self.target_machine_name and machine_phase:
            self._process_machine_phase(machine_phase)
        else:
            self._handle_machine_not_found(machines_data)

    def _monitor_node_and_csrs(self):
        # Check for pending CSRs and approve them
        self._approve_pending_csrs()

        # Check if the replacement node is Ready
        self._check_node_readiness()

    def _approve_pending_csrs(self):
        csr_data = self.execute_oc_command(["get", "csr", "-o", "json"], json_output=True)

        if csr_data and csr_data.get("items"):
            pending_csrs = []
            for csr in csr_data["items"]:
                # Check if CSR has conditions and find pending ones
                conditions = csr.get("status", {}).get("conditions", [])
                # If no conditions exist, the CSR is pending
                if not conditions:
                    csr_name = csr["metadata"]["name"]
                    pending_csrs.append(csr_name)

            if pending_csrs:
                self.printer.print_info(f"Found {len(pending_csrs)} pending CSR(s), approving...")
                for csr_name in pending_csrs:
                    result = self.execute_oc_command(["adm", "certificate", "approve", csr_name])
                    if result:
                        self.printer.print_success(f"Approved CSR: {csr_name}")
                    else:
                        self.printer.print_warning(f"Failed to approve CSR: {csr_name}")

                # Brief pause after approving CSRs
                time.sleep(3)

    def _check_node_readiness(self):
        node_data = self.execute_oc_command(["get", "node", self.replacement_node, "-o", "json"], json_output=True)
        if node_data:
            # Extract node status from JSON structure
            conditions = node_data.get("status", {}).get("conditions", [])
            node_status = "Unknown"

            # Find the Ready condition
            for condition in conditions:
                if condition.get("type") == "Ready":
                    node_status = "Ready" if condition.get("status") == "True" else "NotReady"
                    break

            self.printer.print_info(f"Node {self.replacement_node} status: {node_status}")

            if node_status == "Ready":
                self.node_ready = True
                self.printer.print_success(f"Node {self.replacement_node} is now Ready!")
            elif node_status == "NotReady":
                self.printer.print_info(f"Node {self.replacement_node} is still NotReady, continuing to monitor...")
        else:
            self.printer.print_info(f"Node {self.replacement_node} not found yet, waiting for it to appear...")

    def _find_target_machine_name(self, machines_data):
        # First try to find machine by BMH annotation (most reliable)
        for machine in machines_data:
            annotations = machine.get("metadata", {}).get("annotations", {})
            bmh_annotation = annotations.get("metal3.io/BareMetalHost")
            if bmh_annotation and self.replacement_node in bmh_annotation:
                machine_name = machine.get("metadata", {}).get("name", "")
                if machine_name:
                    self.printer.print_success(f"Found machine by BMH annotation: {machine_name}")
                    return machine_name

        # Fallback to node number matching (less reliable due to gap-filling logic)
        node_number_match = re.search(r"(\d+)", self.replacement_node)
        if node_number_match:
            node_number = node_number_match.group(1)
            self.printer.print_info(f"Looking for machine with node number {node_number}...")
            for machine in machines_data:
                machine_name = machine.get("metadata", {}).get("name", "")
                if machine_name and node_number in machine_name:
                    self.printer.print_success(f"Found machine by node number: {machine_name}")
                    return machine_name

            self.printer.print_warning(
                f"No machine found with node number {node_number} - this may be due to gap-filling logic"
            )

        return None

    def _get_machine_name_from_bmh_consumerref(self):
        try:
            bmh_output = self.execute_oc_command(
                ["get", "bmh", self.replacement_node, "-n", "openshift-machine-api", "-o", "json"],
                json_output=True,
                printer=self.printer,
            )
            if bmh_output and "spec" in bmh_output and "consumerRef" in bmh_output["spec"]:
                consumer_ref = bmh_output["spec"]["consumerRef"]
                if consumer_ref.get("kind") == "Machine" and "name" in consumer_ref:
                    machine_name = consumer_ref["name"]
                    self.printer.print_success(f"Found machine name from BMH consumerRef: {machine_name}")
                    return machine_name
            return None
        except Exception as e:
            self.printer.print_error(f"Error getting machine name from BMH consumerRef: {e}")
            return None

    def _is_timeout_reached(self):
        return (time.time() - self.start_time) >= self.timeout_seconds

    def _get_elapsed_time(self):
        return int(time.time() - self.start_time)

    def _get_remaining_time(self):
        return int(self.timeout_seconds - (time.time() - self.start_time))

    def _print_progress(self):
        elapsed_time = self._get_elapsed_time()
        remaining_time = self._get_remaining_time()

        # Add CSR checking status to progress
        csr_status = ""
        if self.machine_created and self.machine_monitor_start_time:
            machine_elapsed = int(time.time() - self.machine_monitor_start_time)
            if self.csr_checking_enabled:
                activation_reason = (
                    "3min threshold" if machine_elapsed < self.csr_check_delay_seconds else "10min timer"
                )
                csr_status = f", CSR checking: ACTIVE ({activation_reason})"
            elif machine_elapsed < self.csr_check_delay_seconds:
                early_threshold = 3 * 60
                if machine_elapsed >= early_threshold:
                    csr_status = ", CSR checking: May activate if machine stuck in Provisioning"
                else:
                    remaining_to_early = early_threshold - machine_elapsed
                    remaining_to_full = self.csr_check_delay_seconds - machine_elapsed
                    csr_status = f", CSR early check: {remaining_to_early}s, full check: {remaining_to_full}s"

        self.printer.print_info(f"Elapsed: {elapsed_time}s, Remaining: {remaining_time}s{csr_status}")

    def _get_final_status(self):
        timeout_minutes = self.timeout_seconds // 60

        if self.node_ready:
            self.printer.print_success("Complete 4-phase provisioning sequence completed successfully!")
            self.printer.print_success("✓ Phase 1: BMH became Provisioned")
            self.printer.print_success("✓ Phase 2: Machine created successfully")
            self.printer.print_success("✓ Phase 3: Machine reached Running state")
            self.printer.print_success("✓ Phase 4: CSRs approved and node is Ready")
            return True, "Phase 4: Node Ready", ""

        # Determine which phase failed and provide specific guidance
        self.printer.print_warning(f"TIMEOUT: Provisioning sequence did not complete within {timeout_minutes} minutes")

        if not self.bmh_provisioned:
            self.printer.print_warning("FAILED at Phase 1: BMH did not become Provisioned")
            self.printer.print_warning("Manual intervention required:")
            self.printer.print_info(f"1. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            self.printer.print_info(
                f"2. Check BMH details: oc describe bmh {self.replacement_node} -n openshift-machine-api"
            )
            self.printer.print_info("3. Check for hardware/networking issues")
            self.printer.print_info("4. Verify BMC credentials and connectivity")
            return False, "Phase 1: BMH Provisioned", "BMH did not become Provisioned"
        elif not self.machine_created:
            self.printer.print_warning("FAILED at Phase 2: Machine creation failed")
            self.printer.print_warning("Manual intervention required:")
            self.printer.print_info(f"1. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            self.printer.print_info("2. Manually create machine: oc apply -f <machine-yaml>")
            return False, "Phase 2: Machine Created", "Machine creation failed"
        elif not self.machine_running:
            self.printer.print_warning("FAILED at Phase 3: Machine did not reach Running state")
            self.printer.print_warning("Manual intervention required:")
            self.printer.print_info("1. Check machine status: oc get machines -n openshift-machine-api")
            self.printer.print_info(
                "2. Check machine details: oc describe machine <machine-name> -n openshift-machine-api"
            )
            self.printer.print_info("3. Check for provisioning errors in machine status")
            return False, "Phase 3: Machine Running", "Machine did not reach Running state"
        else:
            self.printer.print_warning("FAILED at Phase 4: Node did not become Ready")
            self.printer.print_warning("Manual intervention may be required:")
            self.printer.print_info(f"1. Check node status: oc get nodes {self.replacement_node}")
            self.printer.print_info("2. Check for pending CSRs: oc get csr --watch")
            self.printer.print_info("3. Manually approve CSRs if needed: oc adm certificate approve <csr-name>")
            self.printer.print_info("4. Check machine status: oc get machine -n openshift-machine-api")
            self.printer.print_info(f"5. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            return False, "Phase 4: Node Ready", "Node did not become Ready"


# === ETCD_MANAGER MODULE ===


# from typing import Optional, Tuple, Callable, Any, Dict

# Import PrintManager for type hints
# from .print_manager import PrintManager


def _get_healthy_etcd_pod(
    failed_node: str, execute_oc_command: Callable[..., Optional[Dict[str, Any]]], printer: PrintManager
) -> Optional[str]:
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

    def exit_with_runtime(message: str) -> Tuple[None, int]:
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
    if printer:
        printer.print_step(current_step, total_steps, "Re-enabling ETCD quorum guard")
    if execute_oc_command and printer:
        _enable_quorum_guard(execute_oc_command, printer)

    if format_runtime and printer:
        elapsed_time = format_runtime(start_time, time.time())
        printer.print_info(f"Total elapsed time: {elapsed_time}")
        printer.print_success("ETCD quorum guard restored - control plane expansion complete!")

    return current_step + 1


# === CONFIGURATION_MANAGER MODULE ===


def _find_machine_template(machines_data, is_worker_template, printer=None):
    if not machines_data or not machines_data.get("items"):
        raise Exception("No machines data provided or no machines found")

    template_machine_data = None

    # If we found a worker template BMH, try to find a corresponding worker machine
    if is_worker_template:
        for machine in machines_data["items"]:
            labels = machine.get("metadata", {}).get("labels", {})
            if labels.get("machine.openshift.io/cluster-api-machine-role") == "worker":
                template_machine_data = machine
                if printer:
                    printer.print_info(f"Found worker machine template: {machine['metadata']['name']}")
                break

    # If no worker machine found, use the first available machine template
    if not template_machine_data:
        template_machine_data = machines_data["items"][0]

        # If it's a control plane template and we need a worker template, modify it for worker use
        labels = template_machine_data.get("metadata", {}).get("labels", {})
        if labels.get("machine.openshift.io/cluster-api-machine-role") == "master" and is_worker_template:
            if printer:
                printer.print_info(
                    f"Adapting control plane machine template for worker use: {template_machine_data['metadata']['name']}"
                )
            # Update labels for worker role
            template_machine_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] = "worker"
            template_machine_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-type"] = "worker"
        else:
            if printer:
                printer.print_info(f"Using machine template: {template_machine_data['metadata']['name']}")

    if not template_machine_data:
        raise Exception("Could not find a machine to use as template")

    return template_machine_data


def _extract_and_copy_secrets(backup_manager, replacement_node, backup_dir, execute_oc_command, printer=None):
    # Find working control plane node
    if printer:
        printer.print_action("Retrieving control plane nodes information for secret extraction...")

    control_plane_nodes_data = execute_oc_command(
        ["get", "nodes", "-l", "node-role.kubernetes.io/control-plane", "-o", "json"], json_output=True, printer=printer
    )

    if not control_plane_nodes_data:
        raise Exception("Failed to retrieve control plane nodes data")

    control_plane_node = find_node(check_ready=True, nodes_data=control_plane_nodes_data, printer=printer)
    if not control_plane_node:
        raise Exception("No working control plane node found to extract secrets from")

    if printer:
        printer.print_info(f"Extracting secrets from control plane node: {control_plane_node}")

    # Extract secrets using BackupManager
    network_backup_file = backup_manager.backup_secret(
        control_plane_node, "network-config-secret", "_network-config-secret.yaml", "network secret"
    )
    bmc_backup_file = backup_manager.backup_secret(control_plane_node, "bmc-secret", "-bmc-secret.yaml", "BMC secret")
    temp_nmstate_file = backup_manager.extract_nmstate_config(control_plane_node)

    # Create target file paths and copy files
    config_files = {
        "network_secret": f"{backup_dir}/{replacement_node}_network-config-secret.yaml",
        "bmc_secret": f"{backup_dir}/{replacement_node}-bmc-secret.yaml",
        "nmstate": f"{backup_dir}/{replacement_node}_nmstate",
    }

    backup_manager.make_file_copy(network_backup_file, config_files["network_secret"])
    backup_manager.make_file_copy(bmc_backup_file, config_files["bmc_secret"])
    backup_manager.make_file_copy(temp_nmstate_file, config_files["nmstate"])

    if printer:
        printer.print_success(f"Extracted all configuration from {control_plane_node}")

    return config_files


def create_new_node_configs(
    backup_manager,
    backup_dir,
    template_backup_file,
    replacement_node,
    is_addition,
    is_worker_template,
    machines_data,
    printer=None,
    execute_oc_command=None,
    is_expansion=False,
):

    # 1. Load BMH template
    with open(template_backup_file, "r") as f:
        template_bmh_data = yaml.safe_load(f)
    if not template_bmh_data:
        raise Exception(f"Could not load BMH data from backup file: {template_backup_file}")

    # 2. Find machine template (for control plane replacement and expansion)
    template_machine_data = None
    if not is_addition:
        template_machine_data = _find_machine_template(machines_data, is_worker_template, printer)
        if is_expansion and printer:
            printer.print_info("Using existing control plane machine as template for expansion")
    else:
        if printer:
            printer.print_info("Skipping machine template processing - MachineSet will handle machine creation")

    # 3. Extract secrets and nmstate from working control plane node
    config_files = _extract_and_copy_secrets(backup_manager, replacement_node, backup_dir, execute_oc_command, printer)

    # 4. Create BMH configuration file
    bmh_data = backup_manager.extract_bmh_fields(template_bmh_data)
    config_files["bmh"] = f"{backup_dir}/{replacement_node}_bmh.yaml"
    with open(config_files["bmh"], "w") as f:
        yaml.dump(bmh_data, f, default_flow_style=False)

    # 5. Create machine configuration file (for control plane replacement and expansion)
    if not is_addition and template_machine_data:
        machine_data = backup_manager.extract_machine_fields(template_machine_data)
        config_files["machine"] = f"{backup_dir}/{replacement_node}_machine.yaml"
        with open(config_files["machine"], "w") as f:
            yaml.dump(machine_data, f, default_flow_style=False)
        if printer:
            if is_expansion:
                printer.print_info("Created machine configuration file for control plane expansion")
            else:
                printer.print_info("Created machine configuration file for control plane replacement")
    elif is_addition and printer:
        printer.print_info("Skipping machine creation - MachineSet will handle machine provisioning")

    if printer:
        printer.print_success(f"Created {len(config_files)} configuration files from template")
    return config_files


def configure_replacement_node(
    copied_files,
    replacement_node,
    replacement_node_ip,
    replacement_node_bmc_ip,
    replacement_node_mac_address,
    replacement_node_role,
    sushy_uid=None,
    printer=None,
    NodeConfigurator=None,
    execute_oc_command=None,
):
    configurator = NodeConfigurator()

    # Update nmstate configuration if available
    if "nmstate" in copied_files:
        printer.print_action("Updating nmstate network configuration")
        configurator.update_nmstate_ip(copied_files["nmstate"], replacement_node_ip)
        printer.print_success("Updated network configuration")

    # Update network secret if available
    if "network_secret" in copied_files and "nmstate" in copied_files:
        printer.print_action("Updating network secret configuration")
        configurator.update_network_secret(copied_files["nmstate"], copied_files["network_secret"], replacement_node)
        printer.print_success("Updated network secret")

    # Update BMC secret if available
    if "bmc_secret" in copied_files:
        printer.print_action("Updating BMC secret configuration")
        configurator.update_bmc_secret_name(copied_files["bmc_secret"], replacement_node)
        printer.print_success("Updated BMC secret name")

    # Update BMH configuration if available
    if "bmh" in copied_files:
        printer.print_action("Updating BMH configuration")
        configurator.update_bmh(
            copied_files["bmh"],
            replacement_node_bmc_ip,
            replacement_node_mac_address,
            replacement_node,
            sushy_uid,
            role=replacement_node_role,
        )
        printer.print_success("Updated BMH configuration")

    # Update machine configuration if available
    if "machine" in copied_files:
        printer.print_action("Updating machine configuration")
        configurator.update_machine_yaml(
            copied_files["machine"],
            replacement_node,
            replacement_node_role,
            execute_oc_command=execute_oc_command,
            printer=printer,
        )
        printer.print_success("Updated machine configuration")

    printer.print_success("Node configuration completed successfully")


# === RESOURCE_MANAGER MODULE ===


# from typing import Any, Callable, Dict, Optional, Tuple


class ResourceManager:

    def __init__(
        self,
        printer: Optional[Any] = None,
        execute_oc_command: Optional[Callable] = None,
        find_bmh_by_pattern: Optional[Callable] = None,
        format_runtime: Optional[Callable] = None,
    ) -> None:
        self.printer = printer
        self.execute_oc_command = execute_oc_command
        self.find_bmh_by_pattern = find_bmh_by_pattern
        self.format_runtime = format_runtime

        # Caching for performance optimization
        self._bmh_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_ttl = 300  # 5 minutes cache TTL

    def _get_bmh_data(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        current_time = time.time()

        # Check if cache is valid
        if (
            not force_refresh
            and self._bmh_cache is not None
            and self._cache_timestamp is not None
            and (current_time - self._cache_timestamp) < self._cache_ttl
        ):
            return self._bmh_cache

        # Fetch fresh data
        if self.printer:
            self.printer.print_action("Retrieving BMH data from cluster...")

        if not self.execute_oc_command:
            return None

        bmh_data = self.execute_oc_command(
            ["get", "bmh", "-n", "openshift-machine-api", "-o", "json"], json_output=True, printer=self.printer
        )

        # Update cache
        if bmh_data:
            self._bmh_cache = bmh_data
            self._cache_timestamp = current_time
            if self.printer:
                item_count = len(bmh_data.get("items", []))
                self.printer.print_success(f"Retrieved {item_count} BMH(s) from cluster")

        return bmh_data

    def _handle_operation_failure(
        self,
        error_msg: str,
        start_time: float,
        current_step: int,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], int]:
        if self.printer:
            self.printer.print_error(error_msg)
            if self.format_runtime:
                end_time = time.time()
                total_runtime = self.format_runtime(start_time, end_time)
                self.printer.print_info(f"Runtime before exit: {total_runtime}")
        return None, None, current_step

    def _handle_simple_failure(
        self,
        error_msg: str,
        start_time: float,
        current_step: int,
    ) -> Tuple[Optional[str], int]:
        if self.printer:
            self.printer.print_error(error_msg)
            if self.format_runtime:
                end_time = time.time()
                total_runtime = self.format_runtime(start_time, end_time)
                self.printer.print_info(f"Runtime before exit: {total_runtime}")
        return None, current_step

    def _find_bmh_data_by_name(self, bmh_name: str, all_bmh_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not all_bmh_data or not all_bmh_data.get("items"):
            return None

        return next((bmh for bmh in all_bmh_data["items"] if bmh["metadata"]["name"] == bmh_name), None)

    def _find_and_validate_bmh(
        self,
        bad_node: str,
        current_step: int,
        total_steps: int,
        start_time: float,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], int]:
        if self.printer:
            self.printer.print_step(current_step, total_steps, "Finding BMH and machine information")
            self.printer.print_action(f"Retrieving BMH information to find pattern matching: {bad_node}")

        # Use cached BMH data to avoid duplicate API calls
        all_bmh_data = self._get_bmh_data()

        if not all_bmh_data:
            return self._handle_operation_failure("Failed to retrieve BMH data from cluster", start_time, current_step)

        # Find BMH that matches the bad_node pattern
        if not self.find_bmh_by_pattern:
            return None, None, current_step

        bmh_name = self.find_bmh_by_pattern(bad_node, all_bmh_data, printer=self.printer)
        if not bmh_name:
            return self._handle_operation_failure(
                f"Could not find BMH matching pattern: {bad_node}", start_time, current_step
            )

        if self.printer:
            self.printer.print_success(f"Found BMH: {bmh_name}")
        return bmh_name, all_bmh_data, current_step + 1

    def _backup_bmh_and_machine_resources(
        self,
        bmh_name: str,
        all_bmh_data: Dict[str, Any],
        backup_manager: Any,
        current_step: int,
        total_steps: int,
        start_time: float,
    ) -> Tuple[Optional[str], int]:
        if self.printer:
            self.printer.print_step(current_step, total_steps, "Backing up BMH and machine definitions")

        # Extract specific BMH data from already-fetched collection (no duplicate API call)
        specific_bmh_data = self._find_bmh_data_by_name(bmh_name, all_bmh_data)
        if not specific_bmh_data:
            return self._handle_simple_failure(f"BMH {bmh_name} not found in fetched data", start_time, current_step)

        # Extract machine name from consumerRef (runtime field used only for identification)
        try:
            machine_name = specific_bmh_data["spec"]["consumerRef"]["name"]
            if self.printer:
                self.printer.print_info(f"Identified machine from BMH consumerRef: {machine_name}")
        except KeyError:
            return self._handle_simple_failure(
                f"BMH {bmh_name} does not have a consumer machine reference", start_time, current_step
            )

        # Backup BMH using extracted fields only (excludes runtime fields like consumerRef)
        if self.printer:
            self.printer.print_action(f"Backing up BMH definition: {bmh_name}")
        if backup_manager:
            bmh_backup_file = backup_manager.backup_bmh_definition(bmh_name, specific_bmh_data)
            if self.printer:
                self.printer.print_success(f"BMH backup saved: {bmh_backup_file}")

        # Backup machine (fetch machine-specific data)
        if self.printer:
            self.printer.print_action(f"Backing up machine definition: {machine_name}")
        if not self.execute_oc_command:
            return None, current_step
        machine_data = self.execute_oc_command(
            ["get", "machine", machine_name, "-n", "openshift-machine-api", "-o", "json"],
            json_output=True,
            printer=self.printer,
        )
        if not machine_data:
            return self._handle_simple_failure(
                f"Failed to retrieve machine data for: {machine_name}", start_time, current_step
            )

        if backup_manager:
            machine_backup_file = backup_manager.backup_machine_definition(machine_name, machine_data)
            if self.printer:
                self.printer.print_success(f"Machine backup saved: {machine_backup_file}")

        return machine_name, current_step + 1

    def _remove_failed_node_resources(
        self,
        bmh_name: str,
        machine_name: str,
        current_step: int,
        total_steps: int,
    ) -> int:
        if self.printer:
            self.printer.print_step(current_step, total_steps, "Removing failed node resources")

        # Remove machine first (recommended order)
        if self.printer:
            self.printer.print_action(f"Removing machine: {machine_name}")
        if self.execute_oc_command:
            self.execute_oc_command(
                ["delete", "machine", machine_name, "-n", "openshift-machine-api"], printer=self.printer
            )
        if self.printer:
            self.printer.print_success(f"Machine {machine_name} removed")

        # Remove BMH
        if self.printer:
            self.printer.print_action(f"Removing BMH: {bmh_name}")
        if self.execute_oc_command:
            self.execute_oc_command(["delete", "bmh", bmh_name, "-n", "openshift-machine-api"], printer=self.printer)
        if self.printer:
            self.printer.print_success(f"BMH {bmh_name} removed")

        if self.printer:
            self.printer.print_success("Resource cleanup completed")
        time.sleep(1)

        return current_step + 1

    def backup_and_remove_resources(
        self,
        bad_node: str,
        backup_manager: Any,
        start_time: float,
        current_step: int,
        total_steps: int,
    ) -> Tuple[Optional[str], Optional[str], int]:
        # Step 1: Find and validate BMH
        bmh_name, all_bmh_data, current_step = self._find_and_validate_bmh(
            bad_node, current_step, total_steps, start_time
        )
        if not bmh_name:  # Error occurred in validation
            return None, None, current_step

        # Step 2: Backup BMH and Machine resources
        if not all_bmh_data:
            return None, None, current_step
        machine_name, current_step = self._backup_bmh_and_machine_resources(
            bmh_name, all_bmh_data, backup_manager, current_step, total_steps, start_time
        )
        if not machine_name:  # Error occurred in backup
            return None, None, current_step

        # Step 3: Remove failed node resources
        current_step = self._remove_failed_node_resources(bmh_name, machine_name, current_step, total_steps)

        return bmh_name, machine_name, current_step

    def find_machineset_for_machine(self, machine_name: str) -> Optional[str]:
        try:
            # Get the machine data to find its owner reference
            machine_data = self.execute_oc_command(
                ["get", "machine", machine_name, "-n", "openshift-machine-api", "-o", "json"],
                json_output=True,
                printer=self.printer,
            )

            if not machine_data:
                if self.printer:
                    self.printer.print_error(f"Failed to retrieve machine data for: {machine_name}")
                return None

            # Look for MachineSet owner reference
            owner_refs = machine_data.get("metadata", {}).get("ownerReferences", [])
            for owner in owner_refs:
                if owner.get("kind") == "MachineSet":
                    machineset_name = owner.get("name")
                    if self.printer:
                        self.printer.print_info(f"Found MachineSet '{machineset_name}' for machine '{machine_name}'")
                    return machineset_name

            if self.printer:
                self.printer.print_warning(f"No MachineSet owner found for machine: {machine_name}")
            return None

        except Exception as e:
            if self.printer:
                self.printer.print_error(f"Error finding MachineSet for machine {machine_name}: {e}")
            return None

    def get_machineset_by_name(
        self, machinesets_data: Dict[str, Any], machineset_name: str
    ) -> Optional[Dict[str, Any]]:
        for ms in machinesets_data.get("items", []):
            if ms["metadata"]["name"] == machineset_name:
                return ms
        return None

    def _get_machineset_data(self, machineset_name: str) -> Optional[Dict]:
        if not self.execute_oc_command:
            return None

        machineset_data = self.execute_oc_command(
            ["get", "machineset", machineset_name, "-n", "openshift-machine-api", "-o", "json"],
            json_output=True,
            printer=self.printer,
        )

        if not machineset_data and self.printer:
            self.printer.print_error(f"Failed to retrieve MachineSet data for: {machineset_name}")

        return machineset_data

    def _calculate_new_replicas(self, current_replicas: int, scale_direction: str) -> tuple[int, str, bool]:
        if scale_direction == "up":
            return current_replicas + 1, "Scaling up", True
        elif scale_direction == "down":
            if current_replicas == 0:
                if self.printer:
                    self.printer.print_warning("MachineSet is already at 0 replicas")
                return 0, "Already at minimum", False
            return max(0, current_replicas - 1), "Scaling down", True
        else:
            if self.printer:
                self.printer.print_error(f"Invalid scale direction: {scale_direction}. Use 'up' or 'down'")
            return 0, "Invalid direction", False

    def _execute_scaling(self, machineset_name: str, new_replicas: int) -> bool:
        try:
            self.execute_oc_command(
                ["scale", "machineset", machineset_name, "-n", "openshift-machine-api", f"--replicas={new_replicas}"],
                printer=self.printer,
            )

            if self.printer:
                self.printer.print_success(
                    f"Successfully scaled MachineSet '{machineset_name}' to {new_replicas} replicas"
                )
            return True
        except Exception as e:
            if self.printer:
                self.printer.print_error(f"Failed to execute scaling: {e}")
            return False

    def scale_machineset_for_machine(self, machine_name: str, scale_direction: str = "up") -> bool:
        try:
            # Find which MachineSet owns this machine
            machineset_name = self.find_machineset_for_machine(machine_name)
            if not machineset_name:
                if self.printer:
                    self.printer.print_error(f"Could not find MachineSet for machine: {machine_name}")
                return False

            # Get the MachineSet data
            machineset_data = self._get_machineset_data(machineset_name)
            if not machineset_data:
                return False

            current_replicas = machineset_data["spec"].get("replicas", 0)
            new_replicas, action, should_continue = self._calculate_new_replicas(current_replicas, scale_direction)

            if not should_continue:
                return (
                    scale_direction == "down" and current_replicas == 0
                )  # Success if already at minimum for scale down

            if self.printer:
                self.printer.print_action(
                    f"{action} MachineSet '{machineset_name}' from {current_replicas} to {new_replicas} replicas"
                )

            return self._execute_scaling(machineset_name, new_replicas)

        except Exception as e:
            if self.printer:
                self.printer.print_error(f"Failed to scale MachineSet for machine {machine_name}: {e}")
            return False

    def scale_machineset_directly(self, machineset_name: str, scale_direction: str = "up") -> bool:
        try:
            # Get the MachineSet data
            machineset_data = self._get_machineset_data(machineset_name)
            if not machineset_data:
                return False

            current_replicas = machineset_data["spec"].get("replicas", 0)
            new_replicas, action, should_continue = self._calculate_new_replicas(current_replicas, scale_direction)

            if not should_continue:
                return (
                    scale_direction == "down" and current_replicas == 0
                )  # Success if already at minimum for scale down

            if self.printer:
                self.printer.print_action(
                    f"{action} MachineSet '{machineset_name}' from {current_replicas} to {new_replicas} replicas"
                )

            return self._execute_scaling(machineset_name, new_replicas)

        except Exception as e:
            if self.printer:
                self.printer.print_error(f"Failed to scale MachineSet {machineset_name}: {e}")
            return False

    def _apply_resource_files(self, copied_files: Dict[str, str], is_addition: bool) -> bool:
        try:
            for resource_type, file_path in copied_files.items():
                if resource_type == "nmstate":
                    continue  # nmstate is handled by network-config-secret

                # Skip machine application for worker additions - MachineSet handles machine creation
                if resource_type == "machine" and is_addition:
                    if self.printer:
                        self.printer.print_info(
                            "Skipping machine application - MachineSet will create the machine automatically"
                        )
                    continue

                if self.printer:
                    self.printer.print_action(f"Applying {resource_type}: {file_path}")
                if self.execute_oc_command:
                    self.execute_oc_command(["apply", "-f", file_path], printer=self.printer)
                if self.printer:
                    self.printer.print_success(f"Applied {resource_type}")

            if self.printer:
                self.printer.print_success("All resources applied successfully")
            return True
        except Exception as e:
            if self.printer:
                self.printer.print_error(f"Failed to apply resources: {e}")
            return False

    def _find_worker_machineset(self) -> Optional[str]:
        machinesets_data = self.execute_oc_command(
            ["get", "machineset", "-n", "openshift-machine-api", "-o", "json"],
            json_output=True,
            printer=self.printer,
        )

        if not machinesets_data:
            return None

        # Find a worker MachineSet by looking for the worker role label
        for machineset in machinesets_data.get("items", []):
            labels = machineset.get("metadata", {}).get("labels", {})
            if labels.get("machine.openshift.io/cluster-api-machine-role") == "worker":
                worker_machineset = machineset["metadata"]["name"]
                if self.printer:
                    self.printer.print_info(f"Found worker MachineSet: {worker_machineset}")
                return worker_machineset
        return None

    def _handle_worker_scaling(self) -> bool:
        if self.printer:
            self.printer.print_action("Scaling worker MachineSet to accommodate new worker")

        worker_machineset = self._find_worker_machineset()

        if worker_machineset:
            if not self.scale_machineset_directly(worker_machineset, scale_direction="up"):
                if self.printer:
                    self.printer.print_error("Failed to scale MachineSet - continuing with monitoring anyway")
                return False
            else:
                if self.printer:
                    self.printer.print_success("MachineSet scaled successfully")
                return True
        else:
            if self.printer:
                self.printer.print_error("No worker MachineSet found - continuing with monitoring anyway")
            return False

    def _create_and_monitor_resources(
        self,
        replacement_node: str,
        backup_dir: str,
        is_addition: bool,
        is_expansion: bool,
        ResourceMonitor: Any,
        start_time: float,
        handle_provisioning_failure: Callable,
    ) -> tuple[bool, Optional[str]]:
        # Create resource monitor and start monitoring
        monitor = ResourceMonitor(
            replacement_node,
            backup_dir,
            is_addition=is_addition,
            is_expansion=is_expansion,
            printer=self.printer,
            execute_oc_command=self.execute_oc_command,
        )

        try:
            success, phase_reached, error_message = monitor.monitor_provisioning_sequence()
            if success:
                if self.printer:
                    self.printer.print_success(f"Node {replacement_node} successfully provisioned and ready!")
                return True, None
            else:
                handle_provisioning_failure(
                    phase_reached,
                    error_message,
                    start_time,
                    is_addition,
                    printer=self.printer,
                    format_runtime=self.format_runtime,
                )
                return False, error_message

        except KeyboardInterrupt:
            if self.printer:
                self.printer.print_warning("\nMonitoring interrupted by user")
                self.printer.print_info("Node provisioning may still be in progress...")
                self.printer.print_info(
                    f"Check status manually with: oc get bmh {replacement_node} -n openshift-machine-api"
                )
            return False, "Monitoring interrupted by user"

    def apply_resources_and_monitor(
        self,
        copied_files: Dict[str, str],
        backup_dir: str,
        replacement_node: str,
        start_time: float,
        current_step: int,
        total_steps: int,
        is_addition: bool,
        is_expansion: bool = False,
        ResourceMonitor: Optional[Any] = None,
        handle_provisioning_failure: Optional[Callable] = None,
    ) -> Tuple[Optional[Dict[str, str]], int]:
        # Apply all resources
        step_desc = "Applying new worker configuration" if is_addition else "Applying replacement node configuration"
        if self.printer:
            self.printer.print_step(current_step, total_steps, step_desc)

        if not self._apply_resource_files(copied_files, is_addition):
            return None, current_step

        # For worker addition: scale up the MachineSet
        if is_addition:
            self._handle_worker_scaling()

        current_step += 1

        # Monitor provisioning
        step_desc = "Monitoring new worker provisioning" if is_addition else "Monitoring replacement node provisioning"
        if self.printer:
            self.printer.print_step(current_step, total_steps, step_desc)

        if not ResourceMonitor or not handle_provisioning_failure:
            if self.printer:
                self.printer.print_error("Required monitoring components not available")
            return None, current_step

        success, _ = self._create_and_monitor_resources(
            replacement_node,
            backup_dir,
            is_addition,
            is_expansion,
            ResourceMonitor,
            start_time,
            handle_provisioning_failure,
        )

        if success:
            current_step += 1
            return copied_files, current_step
        else:
            return None, current_step


# === ORCHESTRATOR MODULE ===


# from typing import Any, Dict, Optional, Tuple


class NodeOperationOrchestrator:

    def __init__(self, **dependencies: Any) -> None:
        # Core dependencies
        self.printer = dependencies["printer"]
        self.execute_oc_command = dependencies["execute_oc_command"]
        self.format_runtime = dependencies["format_runtime"]

        # Class constructors
        self.BackupManager = dependencies["BackupManager"]
        self.NodeConfigurator = dependencies["NodeConfigurator"]
        self.ResourceMonitor = dependencies["ResourceMonitor"]

        # Utility functions
        self.find_bmh_by_mac_address = dependencies["find_bmh_by_mac_address"]
        self.find_bmh_by_pattern = dependencies["find_bmh_by_pattern"]
        self.find_machineset_for_machine = dependencies["find_machineset_for_machine"]
        self.annotate_machine_for_deletion = dependencies["annotate_machine_for_deletion"]
        self.scale_down_machineset = dependencies["scale_down_machineset"]
        self.cordon_node = dependencies["cordon_node"]
        self.drain_node = dependencies["drain_node"]
        self.delete_machine = dependencies["delete_machine"]
        self.delete_bmh = dependencies["delete_bmh"]
        self.verify_resources_deleted = dependencies["verify_resources_deleted"]

        # Workflow functions
        self.configure_replacement_node = dependencies["configure_replacement_node"]
        self.handle_successful_completion = dependencies["handle_successful_completion"]
        self.create_new_node_configs = dependencies["create_new_node_configs"]
        self.handle_provisioning_failure = dependencies["handle_provisioning_failure"]

        # Resource manager class
        self.ResourceManager = dependencies["ResourceManager"]
        self.resource_manager = None  # Will be initialized when needed

        # ETCD functions
        self.handle_etcd_operations_for_replacement = dependencies["handle_etcd_operations_for_replacement"]
        self.handle_etcd_operations_for_expansion = dependencies["handle_etcd_operations_for_expansion"]
        self.re_enable_quorum_guard_after_expansion = dependencies["re_enable_quorum_guard_after_expansion"]
        self.exec_pod_command = dependencies["exec_pod_command"]

        # Additional workflow functions
        self.determine_failed_control_node = dependencies["determine_failed_control_node"]

    def _setup_operation_parameters(
        self, args: Any, is_addition: bool, is_expansion: bool
    ) -> Tuple[int, Dict[str, Any]]:
        # Different step counts for different operations
        if is_addition:
            total_steps = 6  # Worker addition: fewer steps, no ETCD operations
        elif is_expansion:
            total_steps = 9  # Control plane expansion: includes ETCD disable + re-enable steps
        else:
            total_steps = 12  # Full replacement workflow

        operation_params = {
            "replacement_node": args.replacement_node,
            "replacement_node_ip": args.replacement_node_ip,
            "replacement_node_bmc_ip": args.replacement_node_bmc_ip,
            "replacement_node_mac_address": args.replacement_node_mac_address,
            "replacement_node_role": args.replacement_node_role,
            "sushy_uid": args.sushy_uid,
        }

        return total_steps, operation_params

    def _handle_existing_mac_conflict(self, mac_address: str, total_steps: int) -> int:
        existing_bmh_info = self.find_bmh_by_mac_address(mac_address, printer=self.printer)

        if existing_bmh_info and existing_bmh_info.get("node_name"):
            self.printer.print_warning(
                f"Found existing node '{existing_bmh_info['node_name']}' with same MAC address {mac_address}"
            )
            self.printer.print_info("This node will be cordoned, drained, and removed before provisioning the new node")

            # Add 3 extra steps for the additional cleanup
            total_steps += 3

            self.printer.print_warning(f"Total steps increased to {total_steps} due to existing node cleanup")

            # Handle MachineSet scaling if it's a worker node
            if existing_bmh_info.get("machine_name"):
                self._handle_machineset_scaling(existing_bmh_info["machine_name"])

            # Cordon the existing node
            self.printer.print_info(f"Cordoning existing node: {existing_bmh_info['node_name']}")
            self.cordon_node(existing_bmh_info["node_name"], printer=self.printer)

            # Drain the existing node
            self.printer.print_info(f"Draining existing node: {existing_bmh_info['node_name']}")
            self.drain_node(existing_bmh_info["node_name"], printer=self.printer)

            # Delete existing resources
            self._delete_existing_resources(existing_bmh_info.get("machine_name"), existing_bmh_info["bmh_name"])

        return total_steps

    def _handle_machineset_scaling(self, machine_name: str) -> None:
        self.printer.print_action("Finding and scaling down associated MachineSet...")
        machineset_info = self.find_machineset_for_machine(machine_name, printer=self.printer)

        if machineset_info:
            machineset_name = machineset_info["machineset_name"]
            current_replicas = machineset_info["current_replicas"]

            self.printer.print_info(
                f"Machine '{machine_name}' belongs to MachineSet '{machineset_name}' with {current_replicas} replicas"
            )

            # Annotate machine for deletion before scaling down
            if not self.annotate_machine_for_deletion(
                machine_name, printer=self.printer, execute_oc_command=self.execute_oc_command
            ):
                self.printer.print_warning(
                    f"Failed to annotate machine '{machine_name}' - proceeding with scaling anyway"
                )

            if self.scale_down_machineset(
                machineset_name, printer=self.printer, execute_oc_command=self.execute_oc_command
            ):
                self.printer.print_success(f"Successfully scaled down MachineSet '{machineset_name}' by 1 replica")
                self.printer.print_info(
                    "This prevents the MachineSet from creating a replacement worker when this node is converted to control plane"
                )
            else:
                self.printer.print_warning(
                    f"Failed to scale down MachineSet '{machineset_name}' - you may need to manually scale down the worker MachineSet"
                )
        else:
            self.printer.print_info(
                f"Machine '{machine_name}' is not managed by any MachineSet (manually created) - skipping MachineSet operations"
            )

    def _delete_existing_resources(self, machine_name: Optional[str], bmh_name: str) -> None:
        success = True

        if machine_name:
            self.printer.print_info(f"Deleting existing machine: {machine_name}")
            if not self.delete_machine(machine_name, printer=self.printer):
                success = False

        if bmh_name:
            self.printer.print_info(f"Deleting existing BMH: {bmh_name}")
            if not self.delete_bmh(bmh_name, printer=self.printer):
                success = False

        # Verify resources are deleted to prevent conflicts
        if machine_name or bmh_name:
            self.printer.print_info("Waiting for existing resources to be deleted...")
            verification_success = self.verify_resources_deleted(
                machine_name=machine_name, bmh_name=bmh_name, printer=self.printer
            )
            if not verification_success:
                success = False

        if success:
            self.printer.print_success("Successfully cleaned up all existing resources")
        else:
            self.printer.print_warning("Some deletions failed - you may need to manually delete resources")

    def _get_template_configuration(
        self, is_addition: bool, is_expansion: bool, backup_manager: Any
    ) -> Tuple[Optional[str], Optional[bool], Optional[str]]:
        if is_addition:
            # Worker addition: find and backup worker template
            template_backup_file, is_worker_template = backup_manager.backup_template_bmh(failed_control_node=None)
            if not template_backup_file:
                self.printer.print_error("No BMH found to use as template - exiting")
                self._exit_with_runtime(time.time())
                return None, None, None
            return template_backup_file, is_worker_template, None

        elif is_expansion:
            # Control plane expansion: get template from existing control plane
            self.printer.print_info("Expansion mode: Using existing control plane as template")
            template_backup_file, is_worker_template = backup_manager.backup_template_bmh(
                failed_control_node=None, is_control_plane_expansion=True
            )
            if not template_backup_file:
                self.printer.print_error("No control plane BMH found to use as template - exiting")
                self._exit_with_runtime(time.time())
                return None, None, None
            return template_backup_file, is_worker_template, None

        else:
            # Control plane replacement: get template from failed node
            failed_node = self.determine_failed_control_node()
            if not failed_node:
                self.printer.print_error("Could not determine failed control plane node")
                self._exit_with_runtime(time.time())
                return None, None, None

            self.printer.print_info(f"Using failed control plane node as template: {failed_node}")
            template_backup_file, is_worker_template = backup_manager.backup_template_bmh(
                failed_control_node=failed_node
            )
            if not template_backup_file:
                self.printer.print_error(f"Failed to backup template from {failed_node}")
                self._exit_with_runtime(time.time())
                return None, None, None
            return template_backup_file, is_worker_template, failed_node

    def _handle_etcd_operations_step(
        self,
        is_addition: bool,
        is_expansion: bool,
        args: Any,
        failed_node: Optional[str],
        start_time: float,
        current_step: int,
        total_steps: int,
    ) -> Tuple[Optional[str], int]:
        if is_addition:
            # Worker addition: Skip ETCD operations
            self.printer.print_step(current_step, total_steps, "Skipping ETCD operations (worker addition)")
            self.printer.print_info("ETCD operations are not required for worker node addition")
            return None, current_step + 1
        elif is_expansion:
            # Control plane expansion: Only disable quorum guard
            bad_node, current_step = self.handle_etcd_operations_for_expansion(
                start_time,
                current_step,
                total_steps,
                printer=self.printer,
                execute_oc_command=self.execute_oc_command,
                format_runtime=self.format_runtime,
            )
            return bad_node, current_step
        else:
            # Control plane replacement: Full ETCD operations
            bad_node, current_step = self.handle_etcd_operations_for_replacement(
                failed_node,
                start_time,
                current_step,
                total_steps,
                printer=self.printer,
                exec_pod_command=self.exec_pod_command,
                execute_oc_command=self.execute_oc_command,
                format_runtime=self.format_runtime,
            )
            return bad_node, current_step

    def _create_configuration_files(
        self,
        is_addition: bool,
        is_expansion: bool,
        backup_manager: Any,
        backup_dir: str,
        template_backup_file: str,
        is_worker_template: bool,
        operation_params: Dict[str, Any],
        failed_node: Optional[str] = None,
        backup_bmh_name: Optional[str] = None,
        backup_machine_name: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        self.printer.print_action("Retrieving machines information for template selection...")
        machines_data = self.execute_oc_command(
            ["get", "machines", "-n", "openshift-machine-api", "-o", "json"], json_output=True, printer=self.printer
        )

        # For all operations (addition, expansion, AND replacement), create files from template
        # Extract configuration from working nodes, not failed ones
        copied_files = self.create_new_node_configs(
            backup_manager,
            backup_dir,
            template_backup_file,
            operation_params["replacement_node"],
            is_addition,
            is_worker_template,
            machines_data,
            printer=self.printer,
            execute_oc_command=self.execute_oc_command,
            is_expansion=is_expansion,
        )

        return copied_files

    def _exit_with_runtime(self, start_time: float) -> None:
        total_runtime = self.format_runtime(start_time, time.time())
        self.printer.print_error(f"Exiting... Total runtime: {total_runtime}")

    def _get_step_description(self, operation_type: str, step_name: str) -> str:
        descriptions = {
            "configure_node": {
                "replacement": "Configuring replacement node",
                "addition": "Configuring new worker node",
                "expansion": "Configuring new control plane node",
            },
            "apply_resources": {
                "replacement": "Applying resources and monitoring replacement",
                "addition": "Applying resources and monitoring worker addition",
                "expansion": "Applying resources and monitoring control plane expansion",
            },
        }

        return descriptions.get(step_name, {}).get(operation_type, f"Processing {step_name}")

    def process_node_operation(self, args: Any, is_addition: bool = False, is_expansion: bool = False) -> None:
        start_time = time.time()
        total_steps, operation_params = self._setup_operation_parameters(args, is_addition, is_expansion)
        current_step = 1
        operation_params["start_time"] = start_time

        # Step 1: Setup backup directory
        self.printer.print_step(current_step, total_steps, "Setting up backup directory")
        backup_manager = self.BackupManager(printer=self.printer, execute_oc_command=self.execute_oc_command)
        backup_dir = backup_manager.setup_backup_directory(args.backup_dir)
        current_step += 1

        # Step 2: Handle existing MAC conflicts (if any)
        total_steps = self._handle_existing_mac_conflict(operation_params["replacement_node_mac_address"], total_steps)

        # Step 3: Get template configuration
        step_desc = self._get_step_description(
            "addition" if is_addition else "expansion" if is_expansion else "replacement", "get_template"
        )
        self.printer.print_step(current_step, total_steps, "Getting template configuration")

        template_result = self._get_template_configuration(is_addition, is_expansion, backup_manager)
        if not template_result[0]:  # template_backup_file is None
            return
        template_backup_file, is_worker_template, failed_node = template_result

        # Ensure non-None values for required parameters
        if template_backup_file is None or is_worker_template is None:
            self.printer.print_error("Template configuration returned invalid values")
            return
        current_step += 1

        # Step 4: Handle ETCD operations (if needed)
        bad_node, current_step = self._handle_etcd_operations_step(
            is_addition, is_expansion, args, failed_node, start_time, current_step, total_steps
        )
        if bad_node is None and not is_addition and not is_expansion:
            return  # ETCD operations failed

        # Initialize backup variables
        backup_bmh_name, backup_machine_name = None, None

        # Step 5: Handle resource backup and removal (if needed)
        if not is_addition and not is_expansion:
            # Initialize resource manager if not already done
            if not self.resource_manager:
                self.resource_manager = self.ResourceManager(
                    printer=self.printer,
                    execute_oc_command=self.execute_oc_command,
                    find_bmh_by_pattern=self.find_bmh_by_pattern,
                    format_runtime=self.format_runtime,
                )

            assert self.resource_manager is not None  # Type guard for MyPy
            backup_bmh_name, backup_machine_name, current_step = self.resource_manager.backup_and_remove_resources(
                bad_node,  # Remove the unused failed_node parameter
                backup_manager,
                start_time,
                current_step,
                total_steps,
            )

            # Check if backup process failed
            if backup_bmh_name is None or backup_machine_name is None:
                self.printer.print_error("Resource backup failed - cannot proceed with replacement")
                return

        # Step 6: Create configuration files
        step_desc = self._get_step_description(
            "addition" if is_addition else "expansion" if is_expansion else "replacement", "create_config"
        )
        self.printer.print_step(
            current_step,
            total_steps,
            "Creating configuration files for new worker" if is_addition else "Creating configuration files",
        )

        copied_files = self._create_configuration_files(
            is_addition,
            is_expansion,
            backup_manager,
            backup_dir,
            template_backup_file,
            is_worker_template,
            operation_params,
            failed_node,
            backup_bmh_name,
            backup_machine_name,
        )
        if not copied_files:
            return
        current_step += 1

        # Step 7: Configure replacement node
        step_desc = self._get_step_description(
            "addition" if is_addition else "expansion" if is_expansion else "replacement", "configure_node"
        )
        self.printer.print_step(current_step, total_steps, step_desc)

        self.configure_replacement_node(
            copied_files,
            operation_params["replacement_node"],
            operation_params["replacement_node_ip"],
            operation_params["replacement_node_bmc_ip"],
            operation_params["replacement_node_mac_address"],
            operation_params["replacement_node_role"],
            operation_params["sushy_uid"],
            printer=self.printer,
            NodeConfigurator=self.NodeConfigurator,
            execute_oc_command=self.execute_oc_command,
        )
        current_step += 1

        # Step 8: Apply resources and monitor
        # Initialize resource manager if not already done
        if not self.resource_manager:
            self.resource_manager = self.ResourceManager(
                printer=self.printer,
                execute_oc_command=self.execute_oc_command,
                find_bmh_by_pattern=self.find_bmh_by_pattern,
                format_runtime=self.format_runtime,
            )

        assert self.resource_manager is not None  # Type guard for MyPy
        copied_files, current_step = self.resource_manager.apply_resources_and_monitor(
            copied_files,
            backup_dir,
            operation_params["replacement_node"],
            start_time,
            current_step,
            total_steps,
            is_addition=is_addition,
            is_expansion=is_expansion,
            ResourceMonitor=self.ResourceMonitor,
            handle_provisioning_failure=self.handle_provisioning_failure,
        )

        # Step 9: Re-enable quorum guard for control plane expansion
        if is_expansion:
            current_step = self.re_enable_quorum_guard_after_expansion(
                start_time,
                current_step,
                total_steps,
                printer=self.printer,
                execute_oc_command=self.execute_oc_command,
                format_runtime=self.format_runtime,
            )

        # Final step: Handle successful completion
        self.handle_successful_completion(
            operation_params["replacement_node"],
            start_time,
            is_addition,
            printer=self.printer,
            format_runtime=self.format_runtime,
        )


def handle_successful_completion(
    replacement_node: str, start_time: float, is_addition: bool, printer: Any = None, format_runtime: Any = None
) -> None:
    total_runtime = format_runtime(start_time, time.time())

    if is_addition:
        printer.print_header(f"Worker node '{replacement_node}' addition completed successfully!")
        printer.print_success("New worker node is ready and available for workloads")
        printer.print_info("The worker node should appear in the OpenShift console and be ready to accept pods")
    else:
        printer.print_header(f"Control plane node '{replacement_node}' operation completed successfully!")
        printer.print_success("The new control plane node is operational and part of the cluster")
        printer.print_info("The control plane should be fully functional with the new node")

    printer.print_info(f"Total runtime: {total_runtime}")
    printer.print_info("Operation completed successfully!")


def handle_provisioning_failure(error_msg: str, format_runtime: Any, start_time: float, printer: Any = None) -> None:
    total_runtime = format_runtime(start_time, time.time())
    printer.print_error(f"Node operation failed: {error_msg}")
    printer.print_error(f"Total runtime before failure: {total_runtime}")
    printer.print_info("Check the logs above for specific error details")
    printer.print_info("You may need to manually clean up any partially created resources")


# === GLOBAL INSTANCES ===

# Global printer instance
printer = PrintManager()
print_manager = printer  # Alias for backward compatibility


# === MAIN FUNCTION ===
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
