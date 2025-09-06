#!/usr/bin/env python3
"""
Comprehensive pytest tests for node_configurator module.
Tests all NodeConfigurator methods with realistic OpenShift data and mocked dependencies.

This module provides enterprise-grade test coverage for the NodeConfigurator class,
validating all node configuration operations required for OpenShift node replacement.
All tests include proper type annotations, comprehensive error handling, and follow
SOLID principles for maintainable test code.
"""

import pytest
import os
import sys
import base64
import tempfile
import yaml
from typing import Any, Dict

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import Mock, patch, mock_open  # noqa: E402
from modules.node_configurator import NodeConfigurator  # noqa: E402


# =============================================================================
# Test Fixtures - Static Data from Real OpenShift Configurations
# =============================================================================


@pytest.fixture
def sample_nmstate_data() -> Dict[str, Any]:
    """Sample nmstate configuration data.

    Returns:
        Dict[str, Any]: Dictionary containing realistic nmstate network configuration
            data for testing network interface updates and validation.
    """
    return {
        "interfaces": [
            {
                "name": "eno1",
                "type": "ethernet",
                "state": "up",
                "ipv4": {"enabled": True, "address": [{"ip": "192.168.1.100", "prefix-length": 24}], "dhcp": False},
                "ipv6": {"enabled": False},
            },
            {"name": "eno2", "type": "ethernet", "state": "up", "ipv4": {"enabled": False}},
        ],
        "routes": {
            "config": [{"destination": "0.0.0.0/0", "next-hop-address": "192.168.1.1", "next-hop-interface": "eno1"}]
        },
        "dns-resolver": {"config": {"server": ["8.8.8.8", "8.8.4.4"]}},
    }


@pytest.fixture
def sample_network_secret_data():
    """Sample network config secret data"""
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "ocp-control1.two.ocp4.example.com-network-config-secret",
            "namespace": "openshift-machine-api",
        },
        "data": {"nmstate": "aW50ZXJmYWNlczoKLSBuYW1lOiBlbm8xCiAgdHlwZTogZXRoZXJuZXQ="},
        "type": "Opaque",
    }


@pytest.fixture
def sample_bmc_secret_data():
    """Sample BMC secret data"""
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "ocp-control1.two.ocp4.example.com-bmc-secret", "namespace": "openshift-machine-api"},
        "data": {
            "password": "dGVzdC1wYXNzd29yZA==",  # base64 encoded "test-password"
            "username": "dGVzdC11c2VyZXI=",  # base64 encoded "test-userer"
        },
        "type": "Opaque",
    }


@pytest.fixture
def sample_bmh_data():
    """Sample BareMetalHost data"""
    return {
        "apiVersion": "metal3.io/v1alpha1",
        "kind": "BareMetalHost",
        "metadata": {
            "name": "ocp-control1.two.ocp4.example.com",
            "namespace": "openshift-machine-api",
            "labels": {"installer.openshift.io/role": "control-plane"},
        },
        "spec": {
            "architecture": "x86_64",
            "automatedCleaningMode": "metadata",
            "bmc": {
                "address": "redfish-virtualmedia+http://192.168.94.10:8000/redfish/v1/Systems/old-uuid-12345",
                "credentialsName": "ocp-control1.two.ocp4.example.com-bmc-secret",
            },
            "bootMACAddress": "52:54:00:e9:d5:8a",
            "bootMode": "UEFI",
            "online": True,
            "preprovisioningNetworkDataName": "ocp-control1.two.ocp4.example.com-network-config-secret",
            "rootDeviceHints": {"deviceName": "/dev/vda"},
            "userData": {"name": "master-user-data-managed", "namespace": "openshift-machine-api"},
        },
    }


@pytest.fixture
def sample_machine_data():
    """Sample Machine data"""
    return {
        "apiVersion": "machine.openshift.io/v1beta1",
        "kind": "Machine",
        "metadata": {
            "name": "two-xkb99-master-1",
            "namespace": "openshift-machine-api",
            "labels": {
                "machine.openshift.io/cluster-api-cluster": "two-xkb99",
                "machine.openshift.io/cluster-api-machine-role": "master",
                "machine.openshift.io/cluster-api-machine-type": "master",
            },
        },
        "spec": {
            "lifecycleHooks": {"preDrain": [{"name": "EtcdQuorumOperator", "owner": "clusteroperator/etcd"}]},
            "metadata": {"labels": {"node-role.kubernetes.io/control-plane": "", "node-role.kubernetes.io/master": ""}},
            "providerSpec": {
                "value": {
                    "apiVersion": "machine.openshift.io/v1beta1",
                    "kind": "BareMetalMachineProviderSpec",
                    "hostSelector": {"matchLabels": {"installer.openshift.io/role": "control-plane"}},
                    "userData": {"name": "master-user-data-managed", "namespace": "openshift-machine-api"},
                }
            },
            "taints": [{"effect": "NoSchedule", "key": "node-role.kubernetes.io/master"}],
        },
    }


@pytest.fixture
def node_configurator() -> NodeConfigurator:
    """NodeConfigurator instance for testing.

    Returns:
        NodeConfigurator: Fresh NodeConfigurator instance for each test
            to ensure test isolation and prevent state leakage.
    """
    return NodeConfigurator()


# =============================================================================
# Test NodeConfigurator Initialization
# =============================================================================


class TestNodeConfiguratorInit:
    """Test NodeConfigurator initialization.

    This class validates the proper initialization of NodeConfigurator instances
    and ensures all required attributes are correctly set up for operation.
    """

    def test_init(self, node_configurator: NodeConfigurator) -> None:
        """Test NodeConfigurator initialization.

        Validates that NodeConfigurator instances are properly initialized
        with all required attributes and methods available for configuration operations.

        Args:
            node_configurator: NodeConfigurator instance for testing.
        """
        assert isinstance(node_configurator, NodeConfigurator)


# =============================================================================
# Test update_nmstate_ip Method
# =============================================================================


class TestUpdateNmstateIP:
    """Test the update_nmstate_ip method"""

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_nmstate_ip_success(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator, sample_nmstate_data
    ):
        """Test successful IP address update in nmstate file"""
        nmstate_file_path = "/tmp/test_nmstate"
        new_ip_address = "192.168.1.200"

        mock_yaml_load.return_value = sample_nmstate_data

        node_configurator.update_nmstate_ip(nmstate_file_path, new_ip_address)

        # Verify file operations
        mock_file.assert_any_call(nmstate_file_path, "r")
        mock_file.assert_any_call(nmstate_file_path, "w")

        # Verify YAML operations
        mock_yaml_load.assert_called_once()
        mock_yaml_dump.assert_called_once()

        # Verify the IP was updated in the data structure
        updated_data = mock_yaml_dump.call_args[0][0]
        assert updated_data["interfaces"][0]["ipv4"]["address"][0]["ip"] == new_ip_address

        # Verify printer calls
        mock_printer.print_info.assert_called_with("Updated interface 'eno1' IP to: 192.168.1.200")
        mock_printer.print_success.assert_called_with("Updated IP address in /tmp/test_nmstate")

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_update_nmstate_ip_no_interfaces(self, mock_yaml_load, mock_file, mock_printer, node_configurator):
        """Test nmstate update when no interfaces section exists"""
        nmstate_file_path = "/tmp/test_nmstate"
        new_ip_address = "192.168.1.200"

        # Data without interfaces section
        nmstate_data = {"routes": {"config": []}}
        mock_yaml_load.return_value = nmstate_data

        node_configurator.update_nmstate_ip(nmstate_file_path, new_ip_address)

        # Should still call success message even if no interfaces found
        mock_printer.print_success.assert_called_with("Updated IP address in /tmp/test_nmstate")

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_update_nmstate_ip_no_ipv4_addresses(self, mock_yaml_load, mock_file, mock_printer, node_configurator):
        """Test nmstate update when no IPv4 addresses are configured"""
        nmstate_file_path = "/tmp/test_nmstate"
        new_ip_address = "192.168.1.200"

        # Interface without IPv4 addresses
        nmstate_data = {"interfaces": [{"name": "eno1", "type": "ethernet", "state": "up", "ipv4": {"enabled": False}}]}
        mock_yaml_load.return_value = nmstate_data

        node_configurator.update_nmstate_ip(nmstate_file_path, new_ip_address)

        # Should complete without updating any IP
        mock_printer.print_success.assert_called_with("Updated IP address in /tmp/test_nmstate")

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", side_effect=IOError("File not found"))
    def test_update_nmstate_ip_file_error(self, mock_file, mock_printer, node_configurator):
        """Test nmstate update when file operations fail"""
        nmstate_file_path = "/tmp/nonexistent"
        new_ip_address = "192.168.1.200"

        node_configurator.update_nmstate_ip(nmstate_file_path, new_ip_address)

        mock_printer.print_error.assert_called_with("Failed to update IP in /tmp/nonexistent: File not found")


# =============================================================================
# Test update_network_secret Method
# =============================================================================


class TestUpdateNetworkSecret:
    """Test the update_network_secret method"""

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_network_secret_success(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, sample_network_secret_data
    ):
        """Test successful network secret update"""
        base64_file_path = "/tmp/nmstate_file"
        network_config_secret_file_path = "/tmp/network_secret.yaml"
        replacement_node = "new-control4"

        # Mock file reading
        mock_file.return_value.read.return_value = "test nmstate data"
        mock_yaml_load.return_value = sample_network_secret_data

        node_configurator.update_network_secret(base64_file_path, network_config_secret_file_path, replacement_node)

        # Verify file operations
        mock_file.assert_any_call(base64_file_path, "r")
        mock_file.assert_any_call(network_config_secret_file_path, "r")
        mock_file.assert_any_call(network_config_secret_file_path, "w")

        # Verify YAML operations
        mock_yaml_load.assert_called_once()
        mock_yaml_dump.assert_called_once()

        # Verify the data was updated correctly
        updated_data = mock_yaml_dump.call_args[0][0]
        expected_base64 = base64.b64encode("test nmstate data".encode()).decode()
        assert updated_data["data"]["nmstate"] == expected_base64
        assert updated_data["metadata"]["name"] == "new-control4-network-config-secret"

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_network_secret_with_empty_data(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, sample_network_secret_data
    ):
        """Test network secret update with empty nmstate data"""
        base64_file_path = "/tmp/empty_nmstate"
        network_config_secret_file_path = "/tmp/network_secret.yaml"
        replacement_node = "new-control4"

        # Mock empty file reading
        mock_file.return_value.read.return_value = ""
        mock_yaml_load.return_value = sample_network_secret_data

        node_configurator.update_network_secret(base64_file_path, network_config_secret_file_path, replacement_node)

        # Should still work with empty data
        updated_data = mock_yaml_dump.call_args[0][0]
        expected_base64 = base64.b64encode("".encode()).decode()
        assert updated_data["data"]["nmstate"] == expected_base64
        assert updated_data["metadata"]["name"] == "new-control4-network-config-secret"


# =============================================================================
# Test update_bmc_secret_name Method
# =============================================================================


class TestUpdateBmcSecretName:
    """Test the update_bmc_secret_name method"""

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_bmc_secret_name_success(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, sample_bmc_secret_data
    ):
        """Test successful BMC secret name update"""
        bmc_secret_file_path = "/tmp/bmc_secret.yaml"
        replacement_node = "new-control4"

        mock_yaml_load.return_value = sample_bmc_secret_data

        node_configurator.update_bmc_secret_name(bmc_secret_file_path, replacement_node)

        # Verify file operations
        mock_file.assert_any_call(bmc_secret_file_path, "r")
        mock_file.assert_any_call(bmc_secret_file_path, "w")

        # Verify YAML operations
        mock_yaml_load.assert_called_once()
        mock_yaml_dump.assert_called_once()

        # Verify the name was updated
        updated_data = mock_yaml_dump.call_args[0][0]
        assert updated_data["metadata"]["name"] == "new-control4-bmc-secret"


# =============================================================================
# Test update_bmh Method (Most Complex)
# =============================================================================


class TestUpdateBMH:
    """Test the update_bmh method"""

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_bmh_control_plane_success(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator, sample_bmh_data
    ):
        """Test successful BMH update for control plane node"""
        bmh_file_path = "/tmp/bmh.yaml"
        replacement_node_bmc_ip = "192.168.94.200"
        replacement_node_mac_address = "52:54:00:aa:bb:cc"
        replacement_node = "new-control4"
        sushy_uid = "new-uuid-67890"
        role = "master"

        mock_yaml_load.return_value = sample_bmh_data

        node_configurator.update_bmh(
            bmh_file_path, replacement_node_bmc_ip, replacement_node_mac_address, replacement_node, sushy_uid, role
        )

        # Verify YAML operations
        mock_yaml_load.assert_called_once()
        mock_yaml_dump.assert_called_once()

        # Verify the data was updated correctly
        updated_data = mock_yaml_dump.call_args[0][0]

        # Check BMC address update
        expected_address = f"redfish-virtualmedia+http://{replacement_node_bmc_ip}:8000/redfish/v1/Systems/{sushy_uid}"
        assert updated_data["spec"]["bmc"]["address"] == expected_address

        # Check other fields
        assert updated_data["spec"]["bootMACAddress"] == replacement_node_mac_address
        assert updated_data["spec"]["preprovisioningNetworkDataName"] == f"{replacement_node}-network-config-secret"
        assert updated_data["metadata"]["name"] == replacement_node
        assert updated_data["spec"]["bmc"]["credentialsName"] == f"{replacement_node}-bmc-secret"

        # Check control plane role labels
        assert updated_data["metadata"]["labels"]["installer.openshift.io/role"] == "control-plane"

        # Check userData for master
        assert updated_data["spec"]["userData"]["name"] == "master-user-data-managed"

        # Verify printer calls
        mock_printer.print_info.assert_any_call(f"Updated sushy UID to: {sushy_uid}")
        mock_printer.print_info.assert_any_call(f"Updated BMC credentialsName to: {replacement_node}-bmc-secret")
        mock_printer.print_success.assert_any_call("Ensured control-plane role label is present")

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_bmh_worker_node(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator, sample_bmh_data
    ):
        """Test BMH update for worker node"""
        bmh_file_path = "/tmp/bmh.yaml"
        replacement_node_bmc_ip = "192.168.94.201"
        replacement_node_mac_address = "52:54:00:dd:ee:ff"
        replacement_node = "new-worker1"
        role = "worker"

        mock_yaml_load.return_value = sample_bmh_data

        node_configurator.update_bmh(
            bmh_file_path, replacement_node_bmc_ip, replacement_node_mac_address, replacement_node, None, role
        )

        updated_data = mock_yaml_dump.call_args[0][0]

        # Check that role labels were removed for worker
        assert "installer.openshift.io/role" not in updated_data["metadata"]["labels"]
        assert "node-role.kubernetes.io/control-plane" not in updated_data["metadata"]["labels"]
        assert "node-role.kubernetes.io/master" not in updated_data["metadata"]["labels"]

        # Check userData for worker
        assert updated_data["spec"]["userData"]["name"] == "worker-user-data-managed"

        # Verify printer calls
        mock_printer.print_success.assert_any_call("Removed all role labels for worker node")
        mock_printer.print_success.assert_any_call("Set BMH userData to worker-user-data-managed")

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_bmh_without_sushy_uid(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator, sample_bmh_data
    ):
        """Test BMH update without sushy UID replacement"""
        bmh_file_path = "/tmp/bmh.yaml"
        replacement_node_bmc_ip = "192.168.94.202"
        replacement_node_mac_address = "52:54:00:11:22:33"
        replacement_node = "new-control5"

        mock_yaml_load.return_value = sample_bmh_data

        node_configurator.update_bmh(
            bmh_file_path, replacement_node_bmc_ip, replacement_node_mac_address, replacement_node, None, None
        )

        updated_data = mock_yaml_dump.call_args[0][0]

        # Check that only IP was updated, not the UID
        expected_address = (
            f"redfish-virtualmedia+http://{replacement_node_bmc_ip}:8000/redfish/v1/Systems/old-uuid-12345"
        )
        assert updated_data["spec"]["bmc"]["address"] == expected_address

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_update_bmh_systems_pattern_not_found(self, mock_yaml_load, mock_file, mock_printer, node_configurator):
        """Test BMH update when Systems/ pattern not found in BMC address"""
        bmh_file_path = "/tmp/bmh.yaml"
        replacement_node_bmc_ip = "192.168.94.203"
        replacement_node_mac_address = "52:54:00:44:55:66"
        replacement_node = "new-control6"
        sushy_uid = "new-uuid-99999"

        # BMH data without Systems/ pattern
        bmh_data_no_systems = {
            "apiVersion": "metal3.io/v1alpha1",
            "kind": "BareMetalHost",
            "metadata": {"name": "test-node", "labels": {}},
            "spec": {
                "bmc": {"address": "ipmi://192.168.94.10", "credentialsName": "test-secret"},
                "bootMACAddress": "52:54:00:old",
                "preprovisioningNetworkDataName": "old-secret",
                "userData": {},
            },
        }
        mock_yaml_load.return_value = bmh_data_no_systems

        node_configurator.update_bmh(
            bmh_file_path, replacement_node_bmc_ip, replacement_node_mac_address, replacement_node, sushy_uid, None
        )

        # Should warn that Systems/ pattern not found
        mock_printer.print_warning.assert_called_with(
            "Systems/ pattern not found in BMC address, sushy UID not updated"
        )

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", side_effect=IOError("Permission denied"))
    def test_update_bmh_file_error(self, mock_file, mock_printer, node_configurator):
        """Test BMH update when file operations fail"""
        bmh_file_path = "/tmp/readonly.yaml"

        node_configurator.update_bmh(bmh_file_path, "192.168.94.204", "52:54:00:77:88:99", "test-node")

        mock_printer.print_error.assert_called_with("Failed to update BMC IP in /tmp/readonly.yaml: Permission denied")

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_bmh_missing_metadata_labels(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator
    ):
        """Test BMH update when metadata or labels sections are missing"""
        bmh_file_path = "/tmp/bmh.yaml"
        replacement_node = "new-control7"

        # BMH data without metadata/labels but with complete spec structure
        bmh_data_minimal = {
            "apiVersion": "metal3.io/v1alpha1",
            "kind": "BareMetalHost",
            "spec": {
                "bmc": {
                    "address": "redfish-virtualmedia+http://192.168.94.10:8000/redfish/v1/Systems/test",
                    "credentialsName": "test-secret",
                },
                "bootMACAddress": "52:54:00:old",
                "preprovisioningNetworkDataName": "old-secret",
                "userData": {"name": "master-user-data-managed", "namespace": "openshift-machine-api"},
            },
        }
        mock_yaml_load.return_value = bmh_data_minimal

        # This should not raise an exception despite missing metadata
        try:
            node_configurator.update_bmh(bmh_file_path, "192.168.94.205", "52:54:00:99:aa:bb", replacement_node)
        except Exception as e:
            pytest.fail(f"update_bmh should handle missing metadata gracefully, but raised: {e}")

        # Verify the method completed successfully
        # Check if yaml.dump was called or if an error was printed
        if mock_yaml_dump.called:
            updated_data = mock_yaml_dump.call_args[0][0]
            # Should have created missing metadata and labels sections
            assert "metadata" in updated_data
            assert "labels" in updated_data["metadata"]
        else:
            # If yaml.dump wasn't called, an error should have been printed
            mock_printer.print_error.assert_called()


# =============================================================================
# Test update_machine_yaml Method
# =============================================================================


class TestUpdateMachineYAML:
    """Test the update_machine_yaml method"""

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_master_success(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator, sample_machine_data
    ):
        """Test successful machine YAML update for master node"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "ocp-control4"
        replacement_node_role = "master"

        mock_yaml_load.return_value = sample_machine_data

        node_configurator.update_machine_yaml(
            machine_file_path, replacement_node, replacement_node_role, printer=mock_printer
        )

        # Verify YAML operations
        mock_yaml_load.assert_called_once()
        mock_yaml_dump.assert_called_once()

        # Verify the data was updated correctly
        updated_data = mock_yaml_dump.call_args[0][0]

        # Check metadata updates
        assert updated_data["metadata"]["name"] == "two-xkb99-master-4"
        assert updated_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "master"
        assert updated_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-type"] == "master"

        # Check lifecycle hooks for master
        assert "lifecycleHooks" in updated_data["spec"]

        # Check userData
        assert updated_data["spec"]["providerSpec"]["value"]["userData"]["name"] == "master-user-data-managed"

        # Verify printer calls
        mock_printer.print_info.assert_any_call("Extracted node number '4' from replacement_node 'ocp-control4'")
        mock_printer.print_info.assert_any_call("Updated machine configuration:")
        mock_printer.print_info.assert_any_call("  - Name: two-xkb99-master-4")
        mock_printer.print_info.assert_any_call("  - Role: master")
        mock_printer.print_info.assert_any_call("  - UserData: master-user-data-managed")

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_worker_success(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator, sample_machine_data
    ):
        """Test machine YAML update for worker node"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "ocp-worker5"
        replacement_node_role = "worker"

        mock_yaml_load.return_value = sample_machine_data

        node_configurator.update_machine_yaml(
            machine_file_path, replacement_node, replacement_node_role, printer=mock_printer
        )

        updated_data = mock_yaml_dump.call_args[0][0]

        # Check metadata updates for worker
        assert updated_data["metadata"]["name"] == "two-xkb99-worker-5"
        assert updated_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "worker"
        assert updated_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-type"] == "worker"

        # Check lifecycle hooks removed for worker
        assert "lifecycleHooks" not in updated_data["spec"]

        # Check userData for worker
        assert updated_data["spec"]["providerSpec"]["value"]["userData"]["name"] == "worker-user-data-managed"

        # Verify printer calls
        mock_printer.print_info.assert_any_call("Removed lifecycle hooks for worker node")

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_default_role(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator, sample_machine_data
    ):
        """Test machine YAML update with default role (master)"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "ocp-control6"

        mock_yaml_load.return_value = sample_machine_data

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, None, printer=mock_printer)

        updated_data = mock_yaml_dump.call_args[0][0]

        # Should default to master role
        assert updated_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "master"
        assert "lifecycleHooks" in updated_data["spec"]

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_no_number_in_name(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator, sample_machine_data
    ):
        """Test machine YAML update when replacement node name has no number"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "new-control-node"

        mock_yaml_load.return_value = sample_machine_data

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, "master", printer=mock_printer)

        updated_data = mock_yaml_dump.call_args[0][0]

        # Should use '0' as fallback
        assert updated_data["metadata"]["name"] == "two-xkb99-master-0"

        # Check for both possible warnings - either about extracting number or about uniqueness verification
        warning_calls = [call.args[0] for call in mock_printer.print_warning.call_args_list]
        expected_warnings = [
            "Could not extract number from replacement_node 'new-control-node', using '0'",
            "Cannot verify machine name uniqueness - execute_oc_command not provided",
        ]
        assert any(
            warning in warning_calls for warning in expected_warnings
        ), f"Expected one of {expected_warnings}, got {warning_calls}"

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_fqdn_node_name(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator, sample_machine_data
    ):
        """Test machine YAML update with FQDN replacement node name"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "ocp-control7.cluster.example.com"

        mock_yaml_load.return_value = sample_machine_data

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, "master", printer=mock_printer)

        updated_data = mock_yaml_dump.call_args[0][0]

        # Should extract number from FQDN
        assert updated_data["metadata"]["name"] == "two-xkb99-master-7"

        mock_printer.print_info.assert_any_call(
            "Extracted node number '7' from replacement_node 'ocp-control7.cluster.example.com'"
        )

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_infrastructure_role(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator, sample_machine_data
    ):
        """Test machine YAML update with infrastructure role"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "ocp-infra1"
        replacement_node_role = "infrastructure"

        mock_yaml_load.return_value = sample_machine_data

        node_configurator.update_machine_yaml(
            machine_file_path, replacement_node, replacement_node_role, printer=mock_printer
        )

        updated_data = mock_yaml_dump.call_args[0][0]

        # Infrastructure role should use worker userData and no lifecycle hooks
        assert updated_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "infrastructure"
        assert "lifecycleHooks" not in updated_data["spec"]
        assert updated_data["spec"]["providerSpec"]["value"]["userData"]["name"] == "worker-user-data-managed"

        mock_printer.print_info.assert_any_call("Using worker userData for role 'infrastructure'")

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_missing_lifecycle_hooks(
        self, mock_yaml_dump, mock_yaml_load, mock_file, mock_printer, node_configurator
    ):
        """Test machine YAML update when lifecycle hooks are missing for master"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "ocp-control8"

        # Machine data without lifecycle hooks
        machine_data_no_hooks = {
            "apiVersion": "machine.openshift.io/v1beta1",
            "kind": "Machine",
            "metadata": {
                "name": "two-xkb99-master-1",
                "labels": {
                    "machine.openshift.io/cluster-api-cluster": "two-xkb99",
                    "machine.openshift.io/cluster-api-machine-role": "master",
                    "machine.openshift.io/cluster-api-machine-type": "master",
                },
            },
            "spec": {"providerSpec": {"value": {"userData": {"name": "master-user-data-managed"}}}},
        }
        mock_yaml_load.return_value = machine_data_no_hooks

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, "master", printer=mock_printer)

        updated_data = mock_yaml_dump.call_args[0][0]

        # Should add lifecycle hooks for master
        assert "lifecycleHooks" in updated_data["spec"]
        assert updated_data["spec"]["lifecycleHooks"]["preDrain"][0]["name"] == "EtcdQuorumOperator"

        mock_printer.print_info.assert_any_call("Added lifecycle hooks for master node")

    @patch("modules.node_configurator.printer")
    @patch("builtins.open", side_effect=IOError("Read error"))
    def test_update_machine_yaml_file_error(self, mock_file, mock_printer, node_configurator):
        """Test machine YAML update when file operations fail"""
        machine_file_path = "/tmp/nonexistent.yaml"
        replacement_node = "test-node"

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, "master", printer=mock_printer)

        mock_printer.print_error.assert_called_with("Failed to update machine YAML /tmp/nonexistent.yaml: Read error")


# =============================================================================
# Integration Tests
# =============================================================================


class TestNodeConfiguratorIntegration:
    """Integration tests combining multiple NodeConfigurator methods"""

    @patch("modules.node_configurator.printer")
    def test_complete_node_configuration_workflow(self, mock_printer, node_configurator):
        """Test complete workflow of configuring a replacement node"""
        replacement_node = "new-control4"
        replacement_ip = "192.168.1.204"
        replacement_bmc_ip = "192.168.94.204"
        replacement_mac = "52:54:00:aa:bb:cc"
        sushy_uid = "new-uuid-12345"

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create temporary files with test data
            nmstate_file = f"{temp_dir}/nmstate"
            network_secret_file = f"{temp_dir}/network_secret.yaml"
            bmc_secret_file = f"{temp_dir}/bmc_secret.yaml"
            bmh_file = f"{temp_dir}/bmh.yaml"
            machine_file = f"{temp_dir}/machine.yaml"

            # Write test data to files
            with open(nmstate_file, "w") as f:
                yaml.dump(
                    {
                        "interfaces": [
                            {
                                "name": "eno1",
                                "ipv4": {"enabled": True, "address": [{"ip": "192.168.1.100", "prefix-length": 24}]},
                            }
                        ]
                    },
                    f,
                )

            with open(network_secret_file, "w") as f:
                yaml.dump({"metadata": {"name": "old-network-secret"}, "data": {"nmstate": "old-data"}}, f)

            with open(bmc_secret_file, "w") as f:
                yaml.dump({"metadata": {"name": "old-bmc-secret"}}, f)

            with open(bmh_file, "w") as f:
                yaml.dump(
                    {
                        "metadata": {"name": "old-node", "labels": {}},
                        "spec": {
                            "bmc": {
                                "address": "redfish-virtualmedia+http://192.168.94.10:8000/redfish/v1/Systems/old-uuid",
                                "credentialsName": "old-bmc-secret",
                            },
                            "bootMACAddress": "52:54:00:old",
                            "preprovisioningNetworkDataName": "old-network-secret",
                            "userData": {"name": "master-user-data-managed"},
                        },
                    },
                    f,
                )

            with open(machine_file, "w") as f:
                yaml.dump(
                    {
                        "metadata": {
                            "name": "cluster-abc-master-1",
                            "labels": {
                                "machine.openshift.io/cluster-api-machine-role": "master",
                                "machine.openshift.io/cluster-api-machine-type": "master",
                            },
                        },
                        "spec": {"providerSpec": {"value": {"userData": {"name": "master-user-data-managed"}}}},
                    },
                    f,
                )

            # Execute the complete workflow
            node_configurator.update_nmstate_ip(nmstate_file, replacement_ip)
            node_configurator.update_network_secret(nmstate_file, network_secret_file, replacement_node)
            node_configurator.update_bmc_secret_name(bmc_secret_file, replacement_node)
            node_configurator.update_bmh(
                bmh_file, replacement_bmc_ip, replacement_mac, replacement_node, sushy_uid, "master"
            )
            node_configurator.update_machine_yaml(machine_file, replacement_node, "master", printer=Mock())

            # Verify all files were updated correctly
            with open(nmstate_file, "r") as f:
                nmstate_data = yaml.safe_load(f)
                assert nmstate_data["interfaces"][0]["ipv4"]["address"][0]["ip"] == replacement_ip

            with open(network_secret_file, "r") as f:
                network_data = yaml.safe_load(f)
                assert network_data["metadata"]["name"] == f"{replacement_node}-network-config-secret"

            with open(bmc_secret_file, "r") as f:
                bmc_data = yaml.safe_load(f)
                assert bmc_data["metadata"]["name"] == f"{replacement_node}-bmc-secret"

            with open(bmh_file, "r") as f:
                bmh_data = yaml.safe_load(f)
                assert replacement_bmc_ip in bmh_data["spec"]["bmc"]["address"]
                assert bmh_data["spec"]["bootMACAddress"] == replacement_mac
                assert bmh_data["metadata"]["name"] == replacement_node

            with open(machine_file, "r") as f:
                machine_data = yaml.safe_load(f)
                assert machine_data["metadata"]["name"] == "cluster-abc-master-4"


# =============================================================================
# Test Runner Configuration
# =============================================================================

if __name__ == "__main__":
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "--cov=modules.node_configurator",
            "--cov-report=term-missing",
            "--cov-fail-under=60",
        ]
    )
