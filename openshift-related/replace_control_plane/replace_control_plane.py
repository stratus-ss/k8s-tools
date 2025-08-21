#!/usr/bin/env python3

import argparse
import base64
import json
import os
import re
import subprocess
import time

import yaml

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


class BackupManager:
    """Manages backup and file operations for node replacement"""

    def __init__(self, backup_dir=None):
        """
        Initialize BackupManager with backup directory path

        Args:
            backup_dir: Optional path to the backup directory. If None, will be determined automatically.
        """
        self.backup_dir = backup_dir
        self.cluster_name = None

    def setup_backup_directory(self, backup_dir=None):
        """
        Determine and create the backup directory.

        Args:
            backup_dir: Optional backup directory path. If not provided, generates default path.

        Returns:
            str: Path to the backup directory
        """
        if backup_dir:
            self.backup_dir = backup_dir
        elif not self.backup_dir:
            # Get cluster name from OpenShift DNS
            cluster_cmd = ["get", "dns", "cluster", "-o", "jsonpath='{.spec.baseDomain}'"]
            self.cluster_name = execute_oc_command(cluster_cmd).strip("'")
            self.backup_dir = f"/home/{os.getenv('USER', 'unknown')}/backup_yamls/{self.cluster_name}"

        printer.print_info(f"Backup directory: {self.backup_dir}")
        return self.create_backup_directory()

    def create_backup_directory(self):
        """
        Create a backup directory if it doesn't exist.

        Returns:
            str: Path to the backup directory
        """
        if not self.backup_dir:
            raise ValueError("Backup directory not set. Call setup_backup_directory() first.")

        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
            printer.print_success(f"Created backup directory: {self.backup_dir}")
        else:
            printer.print_info(f"Using existing backup directory: {self.backup_dir}")
        return self.backup_dir

    def make_file_copy(self, current_file_path, new_file_path):
        """
        Make a copy of a file with a new name.

        Args:
            current_file_path: Path to the source file
            new_file_path: Path to the destination file

        Returns:
            None
        """
        with open(current_file_path, "r") as f:
            with open(new_file_path, "w") as f_new:
                f_new.write(f.read())

    def sanitize_metadata(self, data):
        """
        Remove unwanted metadata fields from a Kubernetes object.

        Args:
            data: Dictionary containing Kubernetes object data

        Returns:
            dict: The same dictionary with unwanted metadata fields removed
        """
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
        """
        Extract specific fields from BareMetal Host (BMH) data for backup purposes.

        Args:
            bmh_data: Dictionary containing full BMH object data from Kubernetes

        Returns:
            dict: Dictionary containing only the essential BMH fields needed for restoration
        """
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
        """
        Extract specific fields from Machine data for backup purposes.

        Args:
            machine_data: Dictionary containing full Machine object data from Kubernetes

        Returns:
            dict: Dictionary containing only the essential Machine fields needed for restoration
        """
        extracted = {
            "apiVersion": machine_data.get("apiVersion"),
            "kind": machine_data.get("kind"),
            "metadata": {
                "labels": machine_data.get("metadata", {}).get("labels", {}),
                "name": machine_data.get("metadata", {}).get("name"),
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
        """
        Backup BMH definition to YAML file

        Args:
            bmh_name: Name of the BMH
            bmh_data: BMH data from OpenShift

        Returns:
            str: Path to the backup file
        """
        extracted_bmh = self.extract_bmh_fields(bmh_data)
        backup_file = f"{self.backup_dir}/{bmh_name}_bmh.yaml"
        with open(backup_file, "w") as f:
            yaml.dump(extracted_bmh, f, default_flow_style=False)
        return backup_file

    def backup_machine_definition(self, machine_name, machine_data):
        """
        Backup machine definition to YAML file

        Args:
            machine_name: Name of the machine
            machine_data: Machine data from OpenShift

        Returns:
            str: Path to the backup file
        """
        extracted_machine = self.extract_machine_fields(machine_data)
        backup_file = f"{self.backup_dir}/{machine_name}_machine.yaml"
        with open(backup_file, "w") as f:
            yaml.dump(extracted_machine, f, default_flow_style=False)
        return backup_file

    def backup_network_secret(self, node_name):
        """
        Backup network configuration secret

        Args:
            node_name: Name of the node

        Returns:
            str: Path to the backup file
        """
        network_secret_json = execute_oc_command(
            ["secret", "-n", "openshift-machine-api", f"{node_name}-network-config-secret"],
            json_output=True,
        )
        network_secret_json_sanitized = self.sanitize_metadata(network_secret_json)
        backup_file = f"{self.backup_dir}/{node_name}_network-config-secret.yaml"
        with open(backup_file, "w") as f:
            yaml.dump(network_secret_json_sanitized, f)
        return backup_file

    def backup_bmc_secret(self, node_name):
        """
        Backup BMC secret

        Args:
            node_name: Name of the node

        Returns:
            str: Path to the backup file
        """
        bmc_secret_json = execute_oc_command(
            ["secret", "-n", "openshift-machine-api", f"{node_name}-bmc-secret"],
            json_output=True,
        )
        bmc_secret_json_sanitized = self.sanitize_metadata(bmc_secret_json)
        backup_file = f"{self.backup_dir}/{node_name}-bmc-secret.yaml"
        with open(backup_file, "w") as f:
            yaml.dump(bmc_secret_json_sanitized, f)
        return backup_file

    def extract_nmstate_config(self, node_name):
        """
        Extract nmstate configuration from secret

        Args:
            node_name: Name of the node

        Returns:
            str: Path to the nmstate file
        """
        execute_oc_command(
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
        """
        Copy all configuration files for replacement node

        Args:
            bad_node: Name of the failed node
            bmh_name: Name of the BMH
            bad_machine: Name of the failed machine
            replacement_node: Name of the replacement node

        Returns:
            dict: Dictionary with paths to copied files
        """
        files = {}

        # Copy nmstate file
        files["nmstate"] = f"{self.backup_dir}/{replacement_node}_nmstate"
        self.make_file_copy(f"{self.backup_dir}/{bad_node}_nmstate", files["nmstate"])

        # Copy BMC secret
        files["bmc_secret"] = f"{self.backup_dir}/{replacement_node}-bmc-secret.yaml"
        self.make_file_copy(f"{self.backup_dir}/{bad_node}-bmc-secret.yaml", files["bmc_secret"])

        # Copy BMH file
        files["bmh"] = f"{self.backup_dir}/{replacement_node}_bmh.yaml"
        self.make_file_copy(f"{self.backup_dir}/{bmh_name}_bmh.yaml", files["bmh"])

        # Copy network config secret
        files["network_secret"] = f"{self.backup_dir}/{replacement_node}_network-config-secret.yaml"
        self.make_file_copy(f"{self.backup_dir}/{bad_node}_network-config-secret.yaml", files["network_secret"])

        # Copy machine file
        files["machine"] = f"{self.backup_dir}/{replacement_node}_machine.yaml"
        self.make_file_copy(f"{self.backup_dir}/{bad_machine}_machine.yaml", files["machine"])

        return files


class NodeConfigurator:
    """Manages configuration updates for replacement nodes"""

    def __init__(self):
        """Initialize NodeConfigurator"""
        pass

    def update_nmstate_ip(self, nmstate_file_path, new_ip_address):
        """
        Update the IP address in an nmstate YAML file.

        Args:
            nmstate_file_path: Path to the nmstate YAML file
            new_ip_address: New IP address to set

        Returns:
            None
        """
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

    def update_network_secret(self, base64_file_path, network_config_secret_file_path, replacement_node):
        """
        Take the nmstate file and create a base64 encoded string and replaces the data: section.

        Updates the data section in the network-config-secret.yaml file and also updates 
        the name of the secret to the replacement node.
        """
        with open(base64_file_path, "r") as f:
            data = f.read()
        base64_data = base64.b64encode(data.encode()).decode()
        with open(network_config_secret_file_path, "r") as f:
            network_config_secret_data = yaml.safe_load(f)
        network_config_secret_data["data"]["nmstate"] = base64_data
        network_config_secret_data["metadata"]["name"] = f"{replacement_node}-network-config-secret"
        with open(network_config_secret_file_path, "w") as f:
            yaml.dump(network_config_secret_data, f, default_flow_style=False)

    def update_bmc_secret_name(self, bmc_secret_file_path, replacement_node):
        """
        Take the bmc-secret.yaml file and update the name of the secret to the replacement node
        """
        with open(bmc_secret_file_path, "r") as f:
            bmc_secret_data = yaml.safe_load(f)
        bmc_secret_data["metadata"]["name"] = f"{replacement_node}-bmc-secret"
        with open(bmc_secret_file_path, "w") as f:
            yaml.dump(bmc_secret_data, f, default_flow_style=False)

    def update_bmh(
        self, bmh_file_path, replacement_node_bmc_ip, replacement_node_mac_address, replacement_node, sushy_uid=None
    ):
        """
        Take the bmh.yaml file and update only the IP address portion of the BMC address.
        It also replaces the bootMACAddress with the replacement node's mac address
        And finally it updates the preprovisioningNetworkDataName to the replacement node's network-config-secret
        Updates the BMC credentialsName to match the replacement node's secret name.
        Optionally updates the sushy UID in the redfish URL.
        Ensures the installer.openshift.io/role: control-plane label is present.

        Args:
            bmh_file_path: Path to the BMH YAML file
            replacement_node_bmc_ip: New IP address to replace in the BMC address
            replacement_node_mac_address: MAC address of the replacement node
            replacement_node: Name of the replacement node
            sushy_uid: Optional UID to replace in the redfish Systems/ path

        Returns:
            None
        """
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

            # Update the BMC address
            bmh_data["spec"]["bmc"]["address"] = new_address
            # Update the bootMACAddress
            bmh_data["spec"]["bootMACAddress"] = replacement_node_mac_address
            # Update the preprovisioningNetworkDataName
            bmh_data["spec"]["preprovisioningNetworkDataName"] = f"{replacement_node}-network-config-secret"
            bmh_data["metadata"]["name"] = replacement_node
            # Update the BMC credentialsName to match the replacement node's secret name
            bmh_data["spec"]["bmc"]["credentialsName"] = f"{replacement_node}-bmc-secret"
            printer.print_info(f"Updated BMC credentialsName to: {replacement_node}-bmc-secret")

            # Ensure the control-plane role label exists
            if "metadata" not in bmh_data:
                bmh_data["metadata"] = {}
            if "labels" not in bmh_data["metadata"]:
                bmh_data["metadata"]["labels"] = {}
            bmh_data["metadata"]["labels"]["installer.openshift.io/role"] = "control-plane"
            printer.print_info("Ensured control-plane role label is present")

            with open(bmh_file_path, "w") as f:
                yaml.dump(bmh_data, f, default_flow_style=False)
            printer.print_info(f"Updated BMC IP from '{current_address}' to '{new_address}'")
        except Exception as e:
            printer.print_error(f"Failed to update BMC IP in {bmh_file_path}: {e}")

    def update_machine_yaml(self, machine_file_path, replacement_node, replacement_node_role=None):
        """
        Update the machine YAML file with replacement node information and role-specific configurations.

        Args:
            machine_file_path: Path to the machine YAML file
            replacement_node: Name of the replacement node (e.g., "ocp-control3")
            replacement_node_role: Optional role for the replacement node (defaults to "master")

        Returns:
            None
        """
        try:
            with open(machine_file_path, "r") as f:
                machine_data = yaml.safe_load(f)

            # Set default role to master if not provided
            role = replacement_node_role if replacement_node_role else "master"

            # Extract cluster name from existing machine name (e.g., "one-zpspd" from "one-zpspd-master-4")
            current_name = machine_data["metadata"]["name"]
            cluster_name = current_name.split("-")[0] + "-" + current_name.split("-")[1]

            # Extract number from replacement_node (handles both simple names and FQDNs)
            # Examples: "ocp-control3" → "3", "ocp-control3.domain.com" → "3", "control5" → "5"
            node_number_match = re.search(r"(\d+)", replacement_node)
            if node_number_match:
                node_number = node_number_match.group(1)
                printer.print_info(f"Extracted node number '{node_number}' from replacement_node '{replacement_node}'")
            else:
                printer.print_warning(f"Could not extract number from replacement_node '{replacement_node}', using '0'")
                node_number = "0"

            # Update metadata labels for role and type
            machine_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] = role
            machine_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-type"] = role

            # Update metadata name to match the pattern: {cluster_name}-{role}-{number}
            machine_data["metadata"]["name"] = f"{cluster_name}-{role}-{node_number}"

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

            # Save the updated machine data
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


class ArgumentsParser:
    """Handles command-line argument parsing for node replacement operations"""

    @staticmethod
    def parse_arguments():
        """
        Parse command-line arguments and return configuration

        Returns:
            argparse.Namespace: Parsed arguments
        """
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

        args = parser.parse_args()

        # Set global debug mode
        global DEBUG_MODE
        DEBUG_MODE = args.debug

        return args


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


class ResourceMonitor:
    """
    Handles 4-phase provisioning monitoring for OpenShift resources.

    Phases:
    1. BMH Available - Wait for BareMetalHost to reach Available state
    2. Machine Created - Create and verify Machine resource
    3. Machine Running - Wait for Machine to reach Running state
    4. Node Ready - Monitor CSRs and wait for Node to be Ready
    """

    def __init__(self, replacement_node, backup_dir, timeout_minutes=45, check_interval=15):
        """
        Initialize ResourceMonitor for 4-phase provisioning.

        Args:
            replacement_node (str): Name of the replacement node
            backup_dir (str): Directory containing backup files
            timeout_minutes (int): Total timeout for monitoring (default: 20 minutes)
            check_interval (int): Seconds between status checks (default: 15 seconds)
        """
        self.replacement_node = replacement_node
        self.backup_dir = backup_dir
        self.timeout_seconds = timeout_minutes * 60
        self.check_interval = check_interval
        self.start_time = None

        # Phase tracking
        self.bmh_available = False
        self.machine_created = False
        self.machine_running = False
        self.node_ready = False
        self.target_machine_name = None

        # CSR checking tracking
        self.machine_monitor_start_time = None
        self.csr_checking_enabled = False
        self.csr_check_delay_seconds = 10 * 60  # 10 minutes

    def monitor_provisioning_sequence(self):
        """
        Execute complete 4-phase provisioning sequence.

        Returns:
            tuple: (success: bool, phase_reached: str, error_message: str)
        """
        printer.print_info("Starting automated 4-phase provisioning sequence...")
        printer.print_info(f"Monitoring BMH: {self.replacement_node}")

        self.start_time = time.time()

        while not self.node_ready and not self._is_timeout_reached():
            self._print_progress()

            if not self.bmh_available:
                self._monitor_bmh_status()
            elif not self.machine_created:
                self._create_machine()
            elif not self.machine_running:
                self._monitor_machine_status()
            else:
                self._monitor_node_and_csrs()

            # Wait before next check (unless node is ready)
            if not self.node_ready:
                time.sleep(self.check_interval)

        return self._get_final_status()

    def _monitor_bmh_status(self):
        """Phase 1: Monitor BMH until Available state"""
        bmh_output = execute_oc_command(
            ["get", "bmh", self.replacement_node, "-n", "openshift-machine-api", "--no-headers"]
        )
        if bmh_output:
            # BMH output format: NAME STATE CONSUMER ONLINE ERROR AGE
            bmh_status = bmh_output.strip().split()[1] if len(bmh_output.strip().split()) > 1 else "Unknown"
            printer.print_info(f"BMH {self.replacement_node} status: {bmh_status}")

            if bmh_status == "available":
                self.bmh_available = True
                printer.print_success(f"BMH {self.replacement_node} is now Available!")
                printer.print_info("BMH is ready for machine binding")
            elif bmh_status in ["provisioning", "provisioned", "externally-provisioned"]:
                printer.print_info(f"BMH {self.replacement_node} is {bmh_status}, waiting for Available status...")
            elif bmh_status == "error":
                printer.print_error(f"BMH {self.replacement_node} is in error state - manual intervention required")
            else:
                printer.print_info(f"BMH {self.replacement_node} status: {bmh_status}, continuing to monitor...")
        else:
            printer.print_info(f"BMH {self.replacement_node} not found yet, waiting for it to appear...")

    def _create_machine(self):
        """Phase 2: Create machine resource"""
        printer.print_success("BMH is available, now creating machine...")
        printer.print_info(f"Applying machine: oc apply -f {self.backup_dir}/{self.replacement_node}_machine.yaml")
        execute_oc_command(["apply", "-f", f"{self.backup_dir}/{self.replacement_node}_machine.yaml"])

        self.machine_created = True
        self.machine_monitor_start_time = time.time()  # Start tracking machine phase monitoring time
        printer.print_success("Machine created successfully!")
        printer.print_info("Now monitoring for machine to reach Running state...")
        printer.print_info(
            "Note: CSR checking will begin automatically if machine doesn't reach Provisioned state within 10 minutes"
        )

        # Brief pause to let machine creation propagate
        time.sleep(5)

    def _monitor_machine_status(self):
        """Phase 3: Monitor machine until Running state"""
        # monitoring loop created by cursor.ai
        # Check if we should enable CSR checking after 10 minutes
        if (
            not self.csr_checking_enabled
            and self.machine_monitor_start_time
            and (time.time() - self.machine_monitor_start_time) >= self.csr_check_delay_seconds
        ):
            self.csr_checking_enabled = True
            printer.print_info("⏰ 10 minutes elapsed - Now checking for CSRs while monitoring machine status...")

        # Check for pending CSRs if enabled (after 10 minutes)
        if self.csr_checking_enabled:
            self._approve_pending_csrs()

        # Get the actual machine name from the generated YAML
        machine_list_output = execute_oc_command(["get", "machines", "-n", "openshift-machine-api", "--no-headers"])
        if machine_list_output:
            machine_lines = machine_list_output.strip().split("\n")

            if not self.target_machine_name:
                self.target_machine_name = self._find_target_machine_name(machine_lines)

            if self.target_machine_name:
                machine_output = execute_oc_command(
                    ["get", "machine", self.target_machine_name, "-n", "openshift-machine-api", "--no-headers"]
                )
                if machine_output:
                    # Machine output format: NAME PHASE TYPE REGION ZONE AGE
                    machine_phase = (
                        machine_output.strip().split()[1] if len(machine_output.strip().split()) > 1 else "Unknown"
                    )

                    # Show CSR status in machine monitoring logs if enabled
                    csr_status = " (CSR checking active)" if self.csr_checking_enabled else ""
                    printer.print_info(f"Machine {self.target_machine_name} phase: {machine_phase}{csr_status}")

                    if machine_phase == "Running":
                        self.machine_running = True
                        printer.print_success(f"Machine {self.target_machine_name} is now Running!")
                        printer.print_info("Machine is ready, now monitoring for node and CSRs...")
                    elif machine_phase in ["Provisioning", "Provisioned"]:
                        wait_msg = (
                            f"Machine {self.target_machine_name} is {machine_phase}, waiting for Running state..."
                        )
                        if self.csr_checking_enabled:
                            wait_msg += " (CSRs being checked and approved as needed)"
                        printer.print_info(wait_msg)
                    elif machine_phase == "Failed":
                        printer.print_error(
                            f"Machine {self.target_machine_name} is in Failed state - manual intervention required"
                        )
                    else:
                        message = f"Machine {self.target_machine_name} phase: {machine_phase}, continuing to monitor..."
                        printer.print_info(f"{message}{csr_status}")
                else:
                    printer.print_info(f"Machine {self.target_machine_name} not found, continuing to monitor...")
            else:
                node_number_match = re.search(r"(\d+)", self.replacement_node)
                node_num = node_number_match.group(1) if node_number_match else 'unknown'
                printer.print_info(f"Looking for machine with node number {node_num}...")
        else:
            printer.print_info("No machines found yet, waiting for machine to appear...")

    def _monitor_node_and_csrs(self):
        """Phase 4: Monitor CSRs and node readiness"""
        # Check for pending CSRs and approve them
        self._approve_pending_csrs()

        # Check if the replacement node is Ready
        self._check_node_readiness()

    def _approve_pending_csrs(self):
        """Discover and approve pending CSRs"""
        csr_output = execute_oc_command(["get", "csr", "--no-headers"])
        if csr_output:
            pending_csrs = []
            for line in csr_output.strip().split("\n"):
                if line and "Pending" in line:
                    csr_name = line.split()[0]
                    pending_csrs.append(csr_name)

            if pending_csrs:
                printer.print_info(f"Found {len(pending_csrs)} pending CSR(s), approving...")
                for csr_name in pending_csrs:
                    result = execute_oc_command(["adm", "certificate", "approve", csr_name])
                    if result:
                        printer.print_success(f"Approved CSR: {csr_name}")
                    else:
                        printer.print_warning(f"Failed to approve CSR: {csr_name}")

                # Brief pause after approving CSRs
                time.sleep(3)

    def _check_node_readiness(self):
        """Check if replacement node is Ready"""
        node_output = execute_oc_command(["get", "nodes", self.replacement_node, "--no-headers"])
        if node_output:
            # Node output format: NAME STATUS ROLES AGE VERSION
            node_status = node_output.strip().split()[1] if len(node_output.strip().split()) > 1 else "Unknown"
            printer.print_info(f"Node {self.replacement_node} status: {node_status}")

            if node_status == "Ready":
                self.node_ready = True
                printer.print_success(f"Node {self.replacement_node} is now Ready!")
            elif node_status == "NotReady":
                printer.print_info(f"Node {self.replacement_node} is still NotReady, continuing to monitor...")
        else:
            printer.print_info(f"Node {self.replacement_node} not found yet, waiting for it to appear...")

    def _find_target_machine_name(self, machine_lines):
        """Find machine name based on replacement node number"""
        node_number_match = re.search(r"(\d+)", self.replacement_node)
        if node_number_match:
            node_number = node_number_match.group(1)
            for line in machine_lines:
                if line and node_number in line:
                    machine_name = line.split()[0]
                    return machine_name
        return None

    def _is_timeout_reached(self):
        """Check if monitoring timeout has been reached"""
        return (time.time() - self.start_time) >= self.timeout_seconds

    def _get_elapsed_time(self):
        """Get elapsed time since monitoring started"""
        return int(time.time() - self.start_time)

    def _get_remaining_time(self):
        """Get remaining time before timeout"""
        return int(self.timeout_seconds - (time.time() - self.start_time))

    def _print_progress(self):
        """Print current progress and timing information"""
        elapsed_time = self._get_elapsed_time()
        remaining_time = self._get_remaining_time()

        # Add CSR checking status to progress
        csr_status = ""
        if self.machine_created and self.machine_monitor_start_time:
            machine_elapsed = int(time.time() - self.machine_monitor_start_time)
            if self.csr_checking_enabled:
                csr_status = f", CSR checking: ACTIVE (started at {self.csr_check_delay_seconds//60}min)"
            elif machine_elapsed < self.csr_check_delay_seconds:
                remaining_to_csr = self.csr_check_delay_seconds - machine_elapsed
                csr_status = f", CSR checking starts in: {remaining_to_csr}s"

        printer.print_info(f"Elapsed: {elapsed_time}s, Remaining: {remaining_time}s{csr_status}")

    def _get_final_status(self):
        """
        Get final monitoring status and error messages.

        Returns:
            tuple: (success: bool, phase_reached: str, error_message: str)
        """
        timeout_minutes = self.timeout_seconds // 60

        if self.node_ready:
            printer.print_success("Complete 4-phase provisioning sequence completed successfully!")
            printer.print_success("✓ Phase 1: BMH became Available")
            printer.print_success("✓ Phase 2: Machine created successfully")
            printer.print_success("✓ Phase 3: Machine reached Running state")
            printer.print_success("✓ Phase 4: CSRs approved and node is Ready")
            return True, "Phase 4: Node Ready", ""

        # Determine which phase failed and provide specific guidance
        printer.print_warning(f"TIMEOUT: Provisioning sequence did not complete within {timeout_minutes} minutes")

        if not self.bmh_available:
            printer.print_warning("FAILED at Phase 1: BMH did not become Available")
            printer.print_warning("Manual intervention required:")
            printer.print_info(f"1. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            printer.print_info(
                f"2. Check BMH details: oc describe bmh {self.replacement_node} -n openshift-machine-api"
            )
            printer.print_info("3. Check for hardware/networking issues")
            printer.print_info("4. Verify BMC credentials and connectivity")
            return False, "Phase 1: BMH Available", "BMH did not become Available"
        elif not self.machine_created:
            printer.print_warning("FAILED at Phase 2: Machine creation failed")
            printer.print_warning("Manual intervention required:")
            printer.print_info(f"1. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            printer.print_info("2. Manually create machine: oc apply -f <machine-yaml>")
            return False, "Phase 2: Machine Created", "Machine creation failed"
        elif not self.machine_running:
            printer.print_warning("FAILED at Phase 3: Machine did not reach Running state")
            printer.print_warning("Manual intervention required:")
            printer.print_info("1. Check machine status: oc get machines -n openshift-machine-api")
            printer.print_info("2. Check machine details: oc describe machine <machine-name> -n openshift-machine-api")
            printer.print_info("3. Check for provisioning errors in machine status")
            return False, "Phase 3: Machine Running", "Machine did not reach Running state"
        else:
            printer.print_warning("FAILED at Phase 4: Node did not become Ready")
            printer.print_warning("Manual intervention may be required:")
            printer.print_info(f"1. Check node status: oc get nodes {self.replacement_node}")
            printer.print_info("2. Check for pending CSRs: oc get csr --watch")
            printer.print_info("3. Manually approve CSRs if needed: oc adm certificate approve <csr-name>")
            printer.print_info("4. Check machine status: oc get machine -n openshift-machine-api")
            printer.print_info(f"5. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            return False, "Phase 4: Node Ready", "Node did not become Ready"


def main():
    """
    Main function to orchestrate OpenShift control plane node replacement.

    This function performs a 12-step process to safely remove a failed control plane node
    and prepare for its replacement:
    1. Set up backup directory
    2. Identify failed control node
    3. Process ETCD cluster recovery (remove failed member)
    4. Disable quorum guard
    5. Clean up ETCD secrets
    6. Create resource backups (BMH, secrets)
    7. Remove failed resources (BMH, machine)
    8. Validate removal
    9. Create replacement node configuration files
    10. Configure replacement node settings (IPs, MAC address, secrets)
    11. 4-phase automated provisioning (using ResourceMonitor)
    12. Re-enable ETCD quorum guard for cluster stability

    Args:
        None (uses command-line arguments)

    Returns:
        None
    """
    printer.print_header("OpenShift Control Plane Replacement Tool")

    # Start tracking total runtime
    start_time = time.time()
    printer.print_info(f"Script started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Parse command-line arguments
    args = ArgumentsParser.parse_arguments()
    replacement_node = args.replacement_node
    replacement_node_ip = args.replacement_node_ip
    replacement_node_bmc_ip = args.replacement_node_bmc_ip
    replacement_node_mac_address = args.replacement_node_mac_address
    # Normalize the role (e.g., "control" -> "master" for OpenShift compatibility)
    replacement_node_role = normalize_node_role(args.replacement_node_role)
    # sushy_uid is optional - will be None if not provided
    sushy_uid = args.sushy_uid
    printer.print_step(1, 11, "Setting up backup directory")
    # Initialize backup manager and set up backup directory
    backup_manager = BackupManager()
    backup_dir = backup_manager.setup_backup_directory(args.backup_dir)

    printer.print_step(2, 11, "Identifying failed control node")
    failed_node = determine_failed_control_node()
    if not failed_node:
        printer.print_error("No failed control node found - exiting")
        end_time = time.time()
        total_runtime = format_runtime(start_time, end_time)
        printer.print_info(f"Runtime before exit: {total_runtime}")
        return
    printer.print_success(f"Identified failed node: {failed_node}")

    printer.print_step(3, 11, "Processing ETCD cluster recovery")
    all_etcd_pods = execute_oc_command(["pods", "-n", "openshift-etcd", "-l", "app=etcd"], json_output=True)
    running_etcd_pod_names = [
        item["metadata"]["name"]
        for item in all_etcd_pods.get("items", [])
        if item.get("status", {}).get("phase") == "Running"
    ]
    # We want to remove the failed node from the list of running etcd pods
    # So that we can execute a command on the remaining etcd pods
    running_etcd_pod_names = [pod_name for pod_name in running_etcd_pod_names if failed_node not in pod_name]

    etcd_pod = running_etcd_pod_names[0]
    printer.print_info(f"Entering pod: {etcd_pod}")
    failed_etcd_endpoint_json = json.loads(
        exec_pod_command(
            etcd_pod,
            ["etcdctl", "endpoint", "health", "--write-out=json"],
            "openshift-etcd",
            "etcd",
            discard_stderr=True,
        )
    )

    for endpoint in failed_etcd_endpoint_json:
        if endpoint["health"] is False:
            etcd_failed_url = endpoint["endpoint"]
            break
        else:
            etcd_failed_url = None
    if not etcd_failed_url:
        printer.print_error("No failed ETCD endpoint found - exiting")
        end_time = time.time()
        total_runtime = format_runtime(start_time, end_time)
        printer.print_info(f"Runtime before exit: {total_runtime}")
        return
    printer.print_info(f"This ETCD endpoint has failed: {etcd_failed_url}")
    etcd_member_list_json = json.loads(
        exec_pod_command(
            etcd_pod,
            ["etcdctl", "member", "list", "--write-out=json"],
            "openshift-etcd",
            "etcd",
            discard_stderr=True,
        )
    )
    for member in etcd_member_list_json["members"]:
        if etcd_failed_url in member["clientURLs"]:
            etcd_failed_member_id_decimal = member["ID"]
            break
    if not etcd_failed_member_id_decimal:
        printer.print_error("No failed ETCD member ID found - exiting")
        end_time = time.time()
        total_runtime = format_runtime(start_time, end_time)
        printer.print_info(f"Runtime before exit: {total_runtime}")
        return

    # Convert decimal ID to hex (equivalent to bash: printf '%x' $ID)
    etcd_failed_member_id = format(int(etcd_failed_member_id_decimal), "x")
    printer.print_info(f"Failed ETCD member ID (hex): {etcd_failed_member_id}")
    etcd_member_remove_json = json.loads(
        exec_pod_command(
            etcd_pod,
            ["etcdctl", "member", "remove", etcd_failed_member_id, "--write-out=json"],
            "openshift-etcd",
            "etcd",
            discard_stderr=True,
        )
    )
    printer.print_info(f"ETCD member remove output: {etcd_member_remove_json}")
    time.sleep(3)

    printer.print_step(4, 11, "Disabling quorum guard")
    printer.print_action("Disabling ETCD quorum guard")
    execute_oc_command(
        [
            "patch",
            "etcd/cluster",
            "--type=merge",
            "-p",
            '{"spec": {"unsupportedConfigOverrides": {"useUnsupportedUnsafeNonHANonProductionUnstableEtcd": true}}}',
        ]
    )
    printer.print_info("Waiting 120 seconds for ETCD cluster recovery...")
    time.sleep(120)
    printer.print_success("Quorum guard disabled")

    # Show elapsed time after major ETCD operations
    elapsed_time = format_runtime(start_time, time.time())
    printer.print_info(f"Elapsed time so far: {elapsed_time}")

    bad_node_json = execute_oc_command(["nodes", "-l", "node-role.kubernetes.io/control-plane"], json_output=True)
    for node in bad_node_json["items"]:
        if failed_node in node["metadata"]["name"]:
            bad_node = node["metadata"]["name"]
            break
    printer.print_step(5, 11, "Cleaning up ETCD secrets")
    printer.print_info(f"Removing secrets for failed node: {bad_node}")
    secrets = execute_oc_command(["secrets", "-n", "openshift-etcd"], json_output=True)
    deleted_secrets = 0
    for secret in secrets["items"]:
        if bad_node in secret["metadata"]["name"]:
            execute_oc_command(["delete", "secret", secret["metadata"]["name"], "-n", "openshift-etcd"])
            printer.print_success(f"Deleted secret: {secret['metadata']['name']}")
            deleted_secrets += 1
            # Small delay between secret deletions to avoid overwhelming the API
            time.sleep(0.5)
    printer.print_success(f"Deleted {deleted_secrets} ETCD secrets")

    machine_json = execute_oc_command(
        [
            "bmh",
            "-n",
            "openshift-machine-api",
            "-l",
            "installer.openshift.io/role=control-plane",
        ],
        json_output=True,
    )
    for machine in machine_json["items"]:
        if bad_node in machine["metadata"]["name"]:
            bad_machine = machine["spec"]["consumerRef"]["name"]
            bmh_name = machine["metadata"]["name"]
            break
    if not bad_machine:
        printer.print_error("No machine found - exiting")
        end_time = time.time()
        total_runtime = format_runtime(start_time, end_time)
        printer.print_info(f"Runtime before exit: {total_runtime}")
        return

    if not bmh_name:
        printer.print_error("No BMH found - exiting")
        end_time = time.time()
        total_runtime = format_runtime(start_time, end_time)
        printer.print_info(f"Runtime before exit: {total_runtime}")
        return

    printer.print_info(f"Found machine: {bad_machine}")
    printer.print_info(f"Found BMH: {bmh_name}")
    printer.print_step(6, 11, "Creating resource backups")

    printer.print_action(f"Backing up BMH definition: {bmh_name}")
    # backup the bmh definition
    bmh_data = execute_oc_command(["bmh", bmh_name, "-n", "openshift-machine-api"], json_output=True)
    bmh_machine_id = bmh_data["spec"]["consumerRef"]["name"]
    bmh_backup_file = backup_manager.backup_bmh_definition(bmh_name, bmh_data)
    printer.print_success(f"BMH backup saved: {bmh_backup_file}")

    printer.print_action(f"Backing up machine definition: {bad_machine}")
    # backup the machine definition
    machine_data = execute_oc_command(["machine", bmh_machine_id, "-n", "openshift-machine-api"], json_output=True)
    machine_backup_file = backup_manager.backup_machine_definition(bad_machine, machine_data)
    printer.print_success(f"Machine backup saved: {machine_backup_file}")

    # backup the network configuration secret
    printer.print_action("Backing up network configuration secret")
    network_backup_file = backup_manager.backup_network_secret(bad_node)
    printer.print_success(f"Network secret backup saved: {network_backup_file}")

    printer.print_action("Extracting nmstate configuration")
    nmstate_file = backup_manager.extract_nmstate_config(bad_node)
    printer.print_success(f"nmstate file extracted: {nmstate_file}")

    printer.print_action("Backing up BMC secret")
    bmc_backup_file = backup_manager.backup_bmc_secret(bad_node)
    printer.print_success(f"BMC secret backup saved: {bmc_backup_file}")

    # Brief pause after backup operations
    printer.print_info("Backup operations complete, preparing for resource deletion...")
    time.sleep(1)

    printer.print_step(7, 11, "Removing failed resources")

    printer.print_action(f"Removing BMH: {bmh_name}")
    printer.print_info(f"BMH removal initiated: {bmh_name}")

    printer.print_warning("This may take 5+ minutes as the machine gets wiped and powered off...")
    execute_oc_command(["delete", "bmh", bmh_name, "-n", "openshift-machine-api"])

    # Wait for BMH deletion to begin processing
    printer.print_info("Waiting for BMH deletion to initiate...")
    time.sleep(5)

    printer.print_action(f"Removing machine: {bad_machine}")
    execute_oc_command(["delete", "machine", "-n", "openshift-machine-api", bad_machine])
    printer.print_success(f"Machine removal completed: {bad_machine}")

    # Wait for machine deletion to propagate
    printer.print_info("Waiting for machine deletion to propagate...")
    time.sleep(3)

    printer.print_step(8, 11, "Validating resource removal")

    # Validate BMH removal
    bmh_output = execute_oc_command(["bmh", "-n", "openshift-machine-api", bmh_name], json_output=True)
    if bmh_output is None:
        printer.print_success(f"BMH {bmh_name} not found (successfully removed)")
    elif bmh_output.get("items"):
        printer.print_warning(f"BMH {bmh_name} still exists")
    else:
        printer.print_success(f"BMH {bmh_name} successfully removed")

    # Brief pause between validation checks
    time.sleep(1)

    # Validate machine removal
    machine_output = execute_oc_command(["machine", "-n", "openshift-machine-api", bad_machine], json_output=True)
    if machine_output is None:
        printer.print_success(f"Machine {bad_machine} not found (successfully removed)")
    elif machine_output.get("items"):
        printer.print_warning(f"Machine {bad_machine} still exists")
    else:
        printer.print_success(f"Machine {bad_machine} successfully removed")

    # Brief pause between validation checks
    time.sleep(1)

    # Validate node removal
    node_output = execute_oc_command(["nodes", failed_node], json_output=True)
    if node_output is None:
        printer.print_success(f"Node {failed_node} not found (successfully removed)")
    elif node_output.get("items"):
        printer.print_warning(f"Node {failed_node} still exists")
    else:
        printer.print_success(f"Node {failed_node} successfully removed")

    printer.print_step(9, 11, "Creating replacement node configuration files")
    printer.print_info("Copying and preparing configuration files for replacement node")

    # Copy all configuration files for replacement node
    copied_files = backup_manager.copy_files_for_replacement(bad_node, bmh_name, bad_machine, replacement_node)
    printer.print_success(f"Copied {len(copied_files)} configuration files for replacement node")

    # Brief pause after file operations
    printer.print_info("Configuration files copied, proceeding with updates...")
    time.sleep(1)

    printer.print_step(10, 11, "Configuring replacement node settings")

    # Initialize node configurator for updating configuration files
    node_configurator = NodeConfigurator()

    printer.print_info(f"Updating IP, and secret name in {copied_files['network_secret']}")
    node_configurator.update_nmstate_ip(copied_files["nmstate"], replacement_node_ip)
    node_configurator.update_network_secret(
        copied_files["nmstate"],
        copied_files["network_secret"],
        replacement_node,
    )

    printer.print_info(f"Updating secret name in {copied_files['bmc_secret']}")
    node_configurator.update_bmc_secret_name(copied_files["bmc_secret"], replacement_node)

    printer.print_info(f"Updating machine configuration in {copied_files['machine']}")
    node_configurator.update_machine_yaml(copied_files["machine"], replacement_node, replacement_node_role)

    bmh_updates = (
        "BMC IP, bootMACAddress, preprovisioningNetworkDataName, credentialsName, and control-plane role label"
    )
    if sushy_uid:
        bmh_updates += ", sushy UID"
    printer.print_info(f"Updating {bmh_updates} in {copied_files['bmh']}")
    node_configurator.update_bmh(
        copied_files["bmh"],
        replacement_node_bmc_ip,
        replacement_node_mac_address,
        replacement_node,
        sushy_uid,
    )

    # Brief pause after all configuration updates to ensure file writes are complete
    printer.print_info("Configuration updates complete, preparing to apply resources...")
    time.sleep(1)

    # apply the secrets
    printer.print_info(f"Applying secrets: oc apply -f {backup_dir}/{replacement_node}*secret*.yaml")
    execute_oc_command(["apply", "-f", f"{backup_dir}/{replacement_node}*secret*.yaml"])

    # Wait for secrets to be processed
    printer.print_info("Waiting for secrets to be created and propagated...")
    time.sleep(5)

    # apply the bmh first
    printer.print_info(f"Applying BMH: oc apply -f {backup_dir}/{replacement_node}_bmh.yaml")
    execute_oc_command(["apply", "-f", f"{backup_dir}/{replacement_node}_bmh.yaml"])

    printer.print_step(11, 12, "Automated 4-phase provisioning sequence")

    # Show elapsed time before starting provisioning monitoring
    elapsed_time = format_runtime(start_time, time.time())
    printer.print_info(f"Elapsed time before provisioning monitoring: {elapsed_time}")

    # Initialize ResourceMonitor for 4-phase provisioning
    monitor = ResourceMonitor(
        replacement_node=replacement_node, backup_dir=backup_dir, timeout_minutes=20, check_interval=15
    )

    # Execute 4-phase monitoring sequence
    success, phase_reached, error_message = monitor.monitor_provisioning_sequence()

    # Step 12: Re-enable quorum guard
    if success:
        printer.print_step(12, 12, "Re-enabling ETCD quorum guard")
        printer.print_action("Re-enabling ETCD quorum guard for cluster stability")
        execute_oc_command(
            [
                "patch",
                "etcd/cluster",
                "--type=merge",
                "-p",
                '{"spec": {"unsupportedConfigOverrides": null}}',
            ]
        )

        # Wait for the patch to be applied
        printer.print_info("Waiting 2 seconds for quorum guard patch to be applied...")
        time.sleep(2)

        # Verify that the quorum guard is properly re-enabled
        printer.print_info("Verifying quorum guard re-enablement...")
        etcd_config = execute_oc_command(["get", "etcd/cluster", "-o", "json"], json_output=False)
        if etcd_config:
            try:
                etcd_json = json.loads(etcd_config)
                unsupported_overrides = etcd_json.get("spec", {}).get("unsupportedConfigOverrides")

                if unsupported_overrides is None or unsupported_overrides == {}:
                    printer.print_success("✅ ETCD quorum guard re-enabled successfully!")
                    printer.print_info("Cluster is now back to normal quorum protection")
                else:
                    printer.print_warning(
                        f"⚠️  Quorum guard may not be fully re-enabled. Current overrides: {unsupported_overrides}"
                    )
                    printer.print_info("Please verify manually: oc get etcd/cluster -o yaml")
            except json.JSONDecodeError as e:
                printer.print_warning(f"Unable to verify quorum guard status: {e}")
                printer.print_info("Please verify manually: oc get etcd/cluster -o yaml")
        else:
            printer.print_warning("Unable to retrieve ETCD configuration for verification")
            printer.print_info("Please verify manually: oc get etcd/cluster -o yaml")

        # Show successful completion
        printer.print_header("Control Plane Replacement Complete")
        printer.print_success("Automated cleanup completed successfully!")
        printer.print_success("Replacement node files created and configured:")
        printer.print_success(f"  - Node IP: {replacement_node_ip}")
        printer.print_success(f"  - BMC IP: {replacement_node_bmc_ip}")
        printer.print_success("  - Network config secret updated with base64 encoded nmstate")
        printer.print_success("  - BMC secret name updated")
        printer.print_success("  - 4-phase provisioning sequence completed (BMH → Machine → Running → Node)")
        printer.print_success("  - CSRs automatically approved and node provisioned")
        printer.print_success("  - ETCD quorum guard re-enabled for cluster stability")
        printer.print_info("The replacement node should now be ready for use!")

        # Show total runtime
        end_time = time.time()
        total_runtime = format_runtime(start_time, end_time)
        printer.print_success(f"Total runtime: {total_runtime}")
        printer.print_info(f"Script completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        printer.print_header("End of Automated Process")
    else:
        # Handle provisioning failure
        printer.print_header("Provisioning Failed")
        printer.print_error(f"4-phase provisioning failed at {phase_reached}")
        printer.print_error(f"Error: {error_message}")
        printer.print_warning("The cluster quorum guard remains DISABLED until manual intervention")
        printer.print_warning("Manual steps required to complete the replacement:")
        printer.print_info("1. Follow the troubleshooting guidance provided above")
        printer.print_info("2. Once the node is Ready, re-enable quorum guard manually:")
        printer.print_info(
            '   oc patch etcd/cluster --type=merge -p \'{"spec": {"unsupportedConfigOverrides": null}}\''
        )

        # Show total runtime even on failure
        end_time = time.time()
        total_runtime = format_runtime(start_time, end_time)
        printer.print_info(f"Total runtime before failure: {total_runtime}")
        printer.print_info(f"Script ended at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        printer.print_header("Manual Intervention Required")


if __name__ == "__main__":
    main()
