#!/usr/bin/env python3
"""Backup Manager module for OpenShift Control Plane Replacement Tool."""

import os
import yaml


class BackupManager:
    """Manages backup and file operations for node replacement"""

    def __init__(self, backup_dir=None, printer=None, execute_oc_command=None):
        """
        Initialize BackupManager with backup directory path

        Args:
            backup_dir: Optional path to the backup directory. If None, will be determined automatically.
            printer: Printer instance for output
            execute_oc_command: Function to execute oc commands
        """
        self.backup_dir = backup_dir
        self.cluster_name = None
        self.printer = printer
        self.execute_oc_command = execute_oc_command

    def setup_backup_directory(self, backup_dir=None):
        """
        Determine and create the backup directory.

        Args:
            backup_dir: Optional backup directory path. If not provided, generates default path.

        Returns:
            str: Path to the backup directory
        """
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

        Excludes runtime/managed fields like consumerRef, status, and metadata fields
        that are managed by Kubernetes/OpenShift to ensure clean restoration.

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
        """
        Backup BMH definition to YAML file

        Note: This function extracts only essential fields for backup purposes.
        Runtime fields like consumerRef, status, etc. are excluded to ensure
        clean restoration without conflicts.

        Args:
            bmh_name: Name of the BMH
            bmh_data: BMH data from OpenShift (may contain runtime fields)

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

    def backup_secret(self, node_name, secret_suffix, backup_filename_suffix, secret_description):
        """
        General function to backup any OpenShift secret

        Args:
            node_name: Name of the node
            secret_suffix: Suffix for the secret name (e.g., 'network-config-secret', 'bmc-secret')
            backup_filename_suffix: Suffix for the backup filename
            secret_description: Human-readable description for error messages

        Returns:
            str: Path to the backup file
        """
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
        """
        Extract nmstate configuration from secret

        Args:
            node_name: Name of the node

        Returns:
            str: Path to the nmstate file
        """
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
        """
        Find and back up appropriate BMH template.

        Args:
            failed_control_node: Name of failed control plane node (for replacement),
                                 None for worker addition or control plane expansion
            is_control_plane_expansion: If True, this is control plane expansion; if False, worker addition

        Returns:
            tuple: (backup_file_path, is_worker_template) or (None, False) if not found
        """

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
