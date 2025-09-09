#!/usr/bin/env python3
"""Node Configurator module for OpenShift Control Plane Replacement Tool."""

import base64
import re
import yaml
from typing import Optional

from .print_manager import printer


class NodeConfigurator:
    """Manages configuration updates for replacement nodes."""

    def __init__(self) -> None:
        """Initialize NodeConfigurator.

        Creates a new NodeConfigurator instance for managing node replacement
        configuration updates.
        """
        pass

    def update_nmstate_ip(self, nmstate_file_path: str, new_ip_address: str) -> None:
        """Update the IP address in an nmstate YAML file.

        This method loads an nmstate YAML configuration file, finds the first IPv4
        interface with an enabled IP configuration, and updates its IP address to
        the specified new address. The updated configuration is then saved back to
        the file.

        Args:
            nmstate_file_path (str): Path to the nmstate YAML file to update.
            new_ip_address (str): New IP address to set for the interface.

        Raises:
            Exception: If the file cannot be read, parsed, or written to.
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

    def update_network_secret(
        self, base64_file_path: str, network_config_secret_file_path: str, replacement_node: str
    ) -> None:
        """Update the network configuration secret with base64 encoded nmstate data.

        This method reads the nmstate configuration file, encodes its content as base64,
        and updates the network configuration secret YAML file with this encoded data.
        It also updates the secret name to match the replacement node.

        Args:
            base64_file_path (str): Path to the nmstate file to be base64 encoded.
            network_config_secret_file_path (str): Path to the network config secret YAML file.
            replacement_node (str): Name of the replacement node to use in the secret name.

        Raises:
            Exception: If any file operations fail or YAML parsing errors occur.
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

    def update_bmc_secret_name(self, bmc_secret_file_path: str, replacement_node: str) -> None:
        """Update the BMC secret name to match the replacement node.

        This method loads the BMC secret YAML file and updates the secret name
        to follow the pattern '{replacement_node}-bmc-secret'.

        Args:
            bmc_secret_file_path (str): Path to the BMC secret YAML file.
            replacement_node (str): Name of the replacement node to use in the secret name.

        Raises:
            Exception: If the file cannot be read, parsed, or written to.
        """
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
        """Update BareMetalHost (BMH) configuration for node replacement.

        This method updates multiple aspects of a BMH YAML file:
        - BMC IP address in the BMC address URL
        - Boot MAC address for the replacement node
        - Network configuration secret name
        - BMC credentials secret name
        - Role-specific labels and userData configuration
        - Optional sushy UID in redfish URLs

        Args:
            bmh_file_path (str): Path to the BMH YAML file to update.
            replacement_node_bmc_ip (str): New BMC IP address for the replacement node.
            replacement_node_mac_address (str): MAC address of the replacement node's boot interface.
            replacement_node (str): Name of the replacement node.
            sushy_uid (str, optional): UID to replace in the redfish Systems/ path.
            role (str, optional): Node role ('master'/'control-plane' vs 'worker').
                                Defaults to control-plane behavior if not specified.

        Raises:
            Exception: If the file cannot be read, parsed, or written to.
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
        """Update machine YAML configuration for node replacement.

        This method updates a machine YAML file with replacement node information,
        handling role-specific configurations including lifecycle hooks, userData
        references, and cluster naming conventions.

        Args:
            machine_file_path (str): Path to the machine YAML file to update.
            replacement_node (str): Name of the replacement node (e.g., "ocp-control3").
                                  Can be a simple name or FQDN, number will be extracted.
            replacement_node_role (str, optional): Role for the replacement node.
                                                  Defaults to "master" if not specified.
            execute_oc_command (callable, optional): Function to execute oc commands for name uniqueness checking.
            printer (PrintManager, optional): Printer instance for logging updates.

        Raises:
            Exception: If the file cannot be read, parsed, or written to, or if
                      cluster name extraction fails.
        """
        # Use global printer if none provided
        if printer is None:
            from .print_manager import printer as global_printer
            printer = global_printer
            
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
        """
        Generate a unique machine name by finding the lowest available number for the role.

        This ensures proper resource management by filling gaps in numbering sequence
        before creating higher-numbered machines.

        Args:
            proposed_name: The initially proposed machine name
            execute_oc_command: Function to execute oc commands
            printer: Printer instance for logging

        Returns:
            str: A unique machine name using the lowest available number
        """
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
