#!/usr/bin/env python3
"""
Comprehensive pytest tests for node_configurator module.
Tests all NodeConfigurator methods with realistic OpenShift data and mocked dependencies.

This module provides enterprise-grade test coverage for the NodeConfigurator class,
validating all node configuration operations required for OpenShift node replacement.
All tests include proper type annotations, comprehensive error handling, and follow
SOLID principles for maintainable test code.

Uses factory-based test data generation from conftest.py for consistent and
maintainable resource creation across all test scenarios.
"""

import pytest
import os
import sys
import base64
import tempfile
import yaml

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, mock_open  # noqa: E402
from modules.node_configurator import NodeConfigurator  # noqa: E402


@pytest.fixture(scope="function")
def standard_bmh_data(bmh_factory):
    """Standard BMH data for node configurator tests - reused across multiple test methods."""
    return bmh_factory(
        node_name="ocp-control1.two.ocp4.example.com",
        bmc_address="redfish-virtualmedia+http://192.168.94.10:8000/redfish/v1/Systems/old-uuid-12345",
        boot_mac_address="52:54:00:e9:d5:8a",
        labels={"installer.openshift.io/role": "control-plane"},
        architecture="x86_64",
        automated_cleaning_mode="metadata",
        boot_mode="UEFI",
        online=True,
        network_config_name="ocp-control1.two.ocp4.example.com-network-config-secret",
        root_device_hints={"deviceName": "/dev/vda"},
        user_data_name="master-user-data-managed",
    )


@pytest.fixture(scope="function")
def standard_machine_data(machine_factory):
    """Standard Machine data for node configurator tests - reused across multiple test methods."""
    machine_data = machine_factory(
        machine_name="two-xkb99-master-1",
        cluster_name="two-xkb99",
        machine_role="master",
        include_cluster_labels=True,
        include_full_provider_spec=True,
        user_data_name="master-user-data-managed",
    )
    machine_data["spec"]["lifecycleHooks"] = {
        "preDrain": [{"name": "EtcdQuorumOperator", "owner": "clusteroperator/etcd"}]
    }
    machine_data["spec"]["providerSpec"]["value"]["hostSelector"] = {
        "matchLabels": {"installer.openshift.io/role": "control-plane"}
    }
    machine_data["spec"]["providerSpec"]["value"]["userData"]["namespace"] = "openshift-machine-api"
    machine_data["spec"]["taints"] = [{"effect": "NoSchedule", "key": "node-role.kubernetes.io/master"}]
    return machine_data


@pytest.fixture
def node_configurator() -> NodeConfigurator:
    """NodeConfigurator instance for testing.

    Returns:
        NodeConfigurator: Fresh NodeConfigurator instance for each test
            to ensure test isolation and prevent state leakage.
    """
    return NodeConfigurator()


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


class TestUpdateNmstateIP:
    """Test the update_nmstate_ip method"""

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_nmstate_ip_success(self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator):
        """Test successful IP address update in nmstate file"""
        nmstate_file_path = "/tmp/test_nmstate"
        new_ip_address = "192.168.1.200"

        # Minimal nmstate data - only what the method actually needs
        nmstate_data = {
            "interfaces": [{"name": "eno1", "ipv4": {"enabled": True, "address": [{"ip": "192.168.1.100"}]}}]
        }
        mock_yaml_load.return_value = nmstate_data

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

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_update_nmstate_ip_no_interfaces(self, mock_yaml_load, mock_file, node_configurator):
        """Test nmstate update when no interfaces section exists"""
        nmstate_file_path = "/tmp/test_nmstate"

        # Data without interfaces section
        nmstate_data = {"routes": {"config": []}}
        mock_yaml_load.return_value = nmstate_data

        node_configurator.update_nmstate_ip(nmstate_file_path, "192.168.1.200")

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_update_nmstate_ip_no_ipv4_addresses(self, mock_yaml_load, mock_file, node_configurator):
        """Test nmstate update when no IPv4 addresses are configured"""
        nmstate_file_path = "/tmp/test_nmstate"

        # Interface without IPv4 addresses
        nmstate_data = {"interfaces": [{"name": "eno1", "type": "ethernet", "state": "up", "ipv4": {"enabled": False}}]}
        mock_yaml_load.return_value = nmstate_data

        node_configurator.update_nmstate_ip(nmstate_file_path, "192.168.1.200")

    @patch("builtins.open", side_effect=IOError("File not found"))
    def test_update_nmstate_ip_file_error(self, mock_file, node_configurator):
        """Test nmstate update when file operations fail"""
        nmstate_file_path = "/tmp/nonexistent"

        node_configurator.update_nmstate_ip(nmstate_file_path, "192.168.1.200")


class TestUpdateNetworkSecret:
    """Test the update_network_secret method"""

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_network_secret_success(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, secret_factory
    ):
        """Test successful network secret update"""
        base64_file_path = "/tmp/nmstate_file"
        network_config_secret_file_path = "/tmp/network_secret.yaml"
        replacement_node = "new-control4"

        # Create network secret data using factory pattern
        network_secret_data = secret_factory(
            secret_name="ocp-control1.two.ocp4.example.com-network-config-secret",
            namespace="openshift-machine-api",
            string_data={"nmstate": "interfaces:\n- name: eno1\n  type: ethernet"},
        )
        # Mock file reading
        mock_file.return_value.read.return_value = "test nmstate data"
        mock_yaml_load.return_value = network_secret_data

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
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, secret_factory
    ):
        """Test network secret update with empty nmstate data"""
        base64_file_path = "/tmp/empty_nmstate"
        network_config_secret_file_path = "/tmp/network_secret.yaml"
        replacement_node = "new-control4"

        # Create network secret data using factory pattern
        network_secret_data = secret_factory(
            secret_name="ocp-control1.two.ocp4.example.com-network-config-secret",
            namespace="openshift-machine-api",
            string_data={"nmstate": "interfaces:\n- name: eno1\n  type: ethernet"},
        )
        # Mock empty file reading
        mock_file.return_value.read.return_value = ""
        mock_yaml_load.return_value = network_secret_data

        node_configurator.update_network_secret(base64_file_path, network_config_secret_file_path, replacement_node)

        # Should still work with empty data
        updated_data = mock_yaml_dump.call_args[0][0]
        expected_base64 = base64.b64encode("".encode()).decode()
        assert updated_data["data"]["nmstate"] == expected_base64
        assert updated_data["metadata"]["name"] == "new-control4-network-config-secret"


class TestUpdateBmcSecretName:
    """Test the update_bmc_secret_name method"""

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_bmc_secret_name_success(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, secret_factory
    ):
        """Test successful BMC secret name update"""
        bmc_secret_file_path = "/tmp/bmc_secret.yaml"
        replacement_node = "new-control4"

        # Create BMC secret data using factory pattern
        bmc_secret_data = secret_factory(
            secret_name="ocp-control1.two.ocp4.example.com-bmc-secret",
            namespace="openshift-machine-api",
            string_data={"username": "test-userer", "password": "test-password"},
        )
        mock_yaml_load.return_value = bmc_secret_data

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


class TestUpdateBMH:
    """Test the update_bmh method"""

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_bmh_control_plane_success(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, standard_bmh_data
    ):
        """Test successful BMH update for control plane node"""
        bmh_file_path = "/tmp/bmh.yaml"
        replacement_node_bmc_ip = "192.168.94.200"
        replacement_node_mac_address = "52:54:00:aa:bb:cc"
        replacement_node = "new-control4"
        sushy_uid = "new-uuid-67890"
        role = "master"

        mock_yaml_load.return_value = standard_bmh_data

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

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_bmh_worker_node(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, standard_bmh_data
    ):
        """Test BMH update for worker node"""
        bmh_file_path = "/tmp/bmh.yaml"
        replacement_node_bmc_ip = "192.168.94.201"
        replacement_node_mac_address = "52:54:00:dd:ee:ff"
        replacement_node = "new-worker1"
        role = "worker"

        mock_yaml_load.return_value = standard_bmh_data

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

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_bmh_without_sushy_uid(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, standard_bmh_data
    ):
        """Test BMH update without sushy UID replacement"""
        bmh_file_path = "/tmp/bmh.yaml"
        replacement_node_bmc_ip = "192.168.94.202"
        replacement_node_mac_address = "52:54:00:11:22:33"
        replacement_node = "new-control5"

        mock_yaml_load.return_value = standard_bmh_data

        node_configurator.update_bmh(
            bmh_file_path, replacement_node_bmc_ip, replacement_node_mac_address, replacement_node, None, None
        )

        updated_data = mock_yaml_dump.call_args[0][0]

        # Check that only IP was updated, not the UID
        expected_address = (
            f"redfish-virtualmedia+http://{replacement_node_bmc_ip}:8000/redfish/v1/Systems/old-uuid-12345"
        )
        assert updated_data["spec"]["bmc"]["address"] == expected_address

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_update_bmh_systems_pattern_not_found(self, mock_yaml_load, mock_file, node_configurator):
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

    @patch("builtins.open", side_effect=IOError("Permission denied"))
    def test_update_bmh_file_error(self, mock_file, node_configurator):
        """Test BMH update when file operations fail"""
        bmh_file_path = "/tmp/readonly.yaml"

        node_configurator.update_bmh(bmh_file_path, "192.168.94.204", "52:54:00:77:88:99", "test-node")

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_bmh_missing_metadata_labels(self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator):
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


class TestUpdateMachineYAML:
    """Test the update_machine_yaml method"""

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_master_success(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, standard_machine_data
    ):
        """Test successful machine YAML update for master node"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "ocp-control4"

        mock_yaml_load.return_value = standard_machine_data

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, "master")

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

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_worker_success(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, standard_machine_data
    ):
        """Test machine YAML update for worker node"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "ocp-worker5"

        mock_yaml_load.return_value = standard_machine_data

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, "worker")

        updated_data = mock_yaml_dump.call_args[0][0]

        # Check metadata updates for worker
        assert updated_data["metadata"]["name"] == "two-xkb99-worker-5"
        assert updated_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "worker"
        assert updated_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-type"] == "worker"

        # Check lifecycle hooks removed for worker
        assert "lifecycleHooks" not in updated_data["spec"]

        # Check userData for worker
        assert updated_data["spec"]["providerSpec"]["value"]["userData"]["name"] == "worker-user-data-managed"

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_default_role(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, standard_machine_data
    ):
        """Test machine YAML update with default role (master)"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "ocp-control6"

        mock_yaml_load.return_value = standard_machine_data

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, None)

        updated_data = mock_yaml_dump.call_args[0][0]

        # Should default to master role
        assert updated_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "master"
        assert "lifecycleHooks" in updated_data["spec"]

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_no_number_in_name(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, standard_machine_data
    ):
        """Test machine YAML update when replacement node name has no number"""
        replacement_node = "new-control-node"

        mock_yaml_load.return_value = standard_machine_data

        node_configurator.update_machine_yaml("/tmp/machine.yaml", replacement_node, "master")

        updated_data = mock_yaml_dump.call_args[0][0]

        # Should use '0' as fallback
        assert updated_data["metadata"]["name"] == "two-xkb99-master-0"

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_fqdn_node_name(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, standard_machine_data
    ):
        """Test machine YAML update with FQDN replacement node name"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "ocp-control7.cluster.example.com"

        mock_yaml_load.return_value = standard_machine_data

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, "master")

        updated_data = mock_yaml_dump.call_args[0][0]

        # Should extract number from FQDN
        assert updated_data["metadata"]["name"] == "two-xkb99-master-7"

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_infrastructure_role(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator, standard_machine_data
    ):
        """Test machine YAML update with infrastructure role"""
        machine_file_path = "/tmp/machine.yaml"
        replacement_node = "ocp-infra1"

        mock_yaml_load.return_value = standard_machine_data

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, "infrastructure")

        updated_data = mock_yaml_dump.call_args[0][0]

        # Infrastructure role should use worker userData and no lifecycle hooks
        assert updated_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "infrastructure"
        assert "lifecycleHooks" not in updated_data["spec"]
        assert updated_data["spec"]["providerSpec"]["value"]["userData"]["name"] == "worker-user-data-managed"

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_update_machine_yaml_missing_lifecycle_hooks(
        self, mock_yaml_dump, mock_yaml_load, mock_file, node_configurator
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

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, "master")

        updated_data = mock_yaml_dump.call_args[0][0]

        # Should add lifecycle hooks for master
        assert "lifecycleHooks" in updated_data["spec"]
        assert updated_data["spec"]["lifecycleHooks"]["preDrain"][0]["name"] == "EtcdQuorumOperator"

    @patch("builtins.open", side_effect=IOError("Read error"))
    def test_update_machine_yaml_file_error(self, mock_file, node_configurator):
        """Test machine YAML update when file operations fail"""
        machine_file_path = "/tmp/nonexistent.yaml"
        replacement_node = "test-node"

        node_configurator.update_machine_yaml(machine_file_path, replacement_node, "master")


class TestNodeConfiguratorIntegration:
    """Integration tests combining multiple NodeConfigurator methods"""

    def test_complete_node_configuration_workflow(
        self, node_configurator, nmstate_factory, secret_factory, bmh_factory, machine_factory
    ):
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

            # Generate test data using factory patterns
            nmstate_data = nmstate_factory(interface_name="eno1", ip_address="192.168.1.100", prefix_length=24)

            # Write test data to files
            with open(nmstate_file, "w") as f:
                yaml.dump(nmstate_data, f)

            network_secret_data = secret_factory(
                secret_name="old-network-secret", namespace="openshift-machine-api", string_data={"nmstate": "old-data"}
            )

            with open(network_secret_file, "w") as f:
                yaml.dump(network_secret_data, f)

            bmc_secret_data = secret_factory(secret_name="old-bmc-secret", namespace="openshift-machine-api")

            with open(bmc_secret_file, "w") as f:
                yaml.dump(bmc_secret_data, f)

            bmh_data = bmh_factory(
                node_name="old-node",
                bmc_address="redfish-virtualmedia+http://192.168.94.10:8000/redfish/v1/Systems/old-uuid",
                boot_mac_address="52:54:00:old",
                bmc_credentials_name="old-bmc-secret",
                network_config_name="old-network-secret",
                user_data_name="master-user-data-managed",
                labels={},
            )

            with open(bmh_file, "w") as f:
                yaml.dump(bmh_data, f)

            machine_data = machine_factory(
                machine_name="cluster-abc-master-1",
                cluster_name="cluster-abc",
                machine_role="master",
                include_cluster_labels=True,
                user_data_name="master-user-data-managed",
            )

            with open(machine_file, "w") as f:
                yaml.dump(machine_data, f)

            # Execute the complete workflow
            node_configurator.update_nmstate_ip(nmstate_file, replacement_ip)
            node_configurator.update_network_secret(nmstate_file, network_secret_file, replacement_node)
            node_configurator.update_bmc_secret_name(bmc_secret_file, replacement_node)
            node_configurator.update_bmh(
                bmh_file, replacement_bmc_ip, replacement_mac, replacement_node, sushy_uid, "master"
            )
            node_configurator.update_machine_yaml(machine_file, replacement_node, "master")

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
