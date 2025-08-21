#!/usr/bin/env python3
"""Node Configurator module for OpenShift Control Plane Replacement Tool."""

import base64
import re
import yaml

from .print_manager import printer


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
