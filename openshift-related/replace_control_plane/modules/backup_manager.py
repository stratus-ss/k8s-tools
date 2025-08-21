#!/usr/bin/env python3
"""Backup Manager module for OpenShift Control Plane Replacement Tool."""

import os
import yaml

from .print_manager import printer
from .utilities import execute_oc_command


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
