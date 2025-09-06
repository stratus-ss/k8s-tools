#!/usr/bin/env python3
"""
Comprehensive pytest tests for configuration_manager module.
Tests all functions with realistic OpenShift data and mocked dependencies.
"""

import pytest
import os
import sys

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import Mock, patch, mock_open, call  # noqa: E402
from modules.configuration_manager import (  # noqa: E402
    _find_machine_template,
    _extract_and_copy_secrets,
    create_new_node_configs,
    configure_replacement_node,
)


# =============================================================================
# Test Fixtures - Static Data from Real OpenShift Cluster
# =============================================================================


@pytest.fixture
def sample_control_plane_machines_data():
    """Real Machine data from OpenShift cluster with control plane machines"""
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "machine.openshift.io/v1beta1",
                "kind": "Machine",
                "metadata": {
                    "name": "two-xkb99-master-0",
                    "namespace": "openshift-machine-api",
                    "labels": {
                        "machine.openshift.io/cluster-api-cluster": "two-xkb99",
                        "machine.openshift.io/cluster-api-machine-role": "master",
                        "machine.openshift.io/cluster-api-machine-type": "master",
                    },
                },
                "spec": {
                    "metadata": {"labels": {"node-role.kubernetes.io/control-plane": ""}},
                    "providerSpec": {
                        "value": {
                            "apiVersion": "machine.openshift.io/v1beta1",
                            "kind": "BareMetalMachineProviderSpec",
                        }
                    },
                },
            },
            {
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
                    "metadata": {"labels": {"node-role.kubernetes.io/control-plane": ""}},
                    "providerSpec": {
                        "value": {
                            "apiVersion": "machine.openshift.io/v1beta1",
                            "kind": "BareMetalMachineProviderSpec",
                        }
                    },
                },
            },
        ],
    }


@pytest.fixture
def sample_mixed_machines_data():
    """Real Machine data with both control plane and worker machines"""
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "machine.openshift.io/v1beta1",
                "kind": "Machine",
                "metadata": {
                    "name": "two-xkb99-master-0",
                    "namespace": "openshift-machine-api",
                    "labels": {
                        "machine.openshift.io/cluster-api-cluster": "two-xkb99",
                        "machine.openshift.io/cluster-api-machine-role": "master",
                        "machine.openshift.io/cluster-api-machine-type": "master",
                    },
                },
                "spec": {
                    "metadata": {"labels": {"node-role.kubernetes.io/control-plane": ""}},
                },
            },
            {
                "apiVersion": "machine.openshift.io/v1beta1",
                "kind": "Machine",
                "metadata": {
                    "name": "two-xkb99-worker-abc12",
                    "namespace": "openshift-machine-api",
                    "labels": {
                        "machine.openshift.io/cluster-api-cluster": "two-xkb99",
                        "machine.openshift.io/cluster-api-machine-role": "worker",
                        "machine.openshift.io/cluster-api-machine-type": "worker",
                    },
                },
                "spec": {
                    "metadata": {"labels": {"node-role.kubernetes.io/worker": ""}},
                },
            },
        ],
    }


@pytest.fixture
def sample_control_plane_nodes_data():
    """Real control plane nodes data"""
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "v1",
                "kind": "Node",
                "metadata": {
                    "name": "ocp-control1.two.ocp4.example.com",
                    "labels": {
                        "node-role.kubernetes.io/control-plane": "",
                        "kubernetes.io/hostname": "ocp-control1.two.ocp4.example.com",
                    },
                },
                "status": {
                    "conditions": [
                        {"type": "Ready", "status": "True"},
                        {"type": "MemoryPressure", "status": "False"},
                    ]
                },
            },
            {
                "apiVersion": "v1",
                "kind": "Node",
                "metadata": {
                    "name": "ocp-control2.two.ocp4.example.com",
                    "labels": {
                        "node-role.kubernetes.io/control-plane": "",
                        "kubernetes.io/hostname": "ocp-control2.two.ocp4.example.com",
                    },
                },
                "status": {
                    "conditions": [
                        {"type": "Ready", "status": "False"},
                        {"type": "MemoryPressure", "status": "False"},
                    ]
                },
            },
        ],
    }


@pytest.fixture
def sample_bmh_template_data():
    """Sample BMH template data"""
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
                "address": "redfish-virtualmedia+http://192.168.94.1:8000/redfish/v1/Systems/node1",
                "credentialsName": "ocp-control1.two.ocp4.example.com-bmc-secret",
            },
            "bootMACAddress": "52:54:00:e9:d5:8a",
            "bootMode": "UEFI",
            "online": True,
            "preprovisioningNetworkDataName": "ocp-control1.two.ocp4.example.com-network-config-secret",
            "rootDeviceHints": {"deviceName": "/dev/vda"},
        },
    }


@pytest.fixture
def mock_printer():
    """Mock printer for output testing"""
    printer = Mock()
    printer.print_info = Mock()
    printer.print_action = Mock()
    printer.print_success = Mock()
    printer.print_error = Mock()
    printer.print_warning = Mock()
    return printer


@pytest.fixture
def mock_backup_manager():
    """Mock BackupManager for testing"""
    backup_manager = Mock()
    backup_manager.backup_dir = "/test/backup"
    backup_manager.backup_secret = Mock()
    backup_manager.extract_nmstate_config = Mock()
    backup_manager.make_file_copy = Mock()
    backup_manager.extract_bmh_fields = Mock()
    backup_manager.extract_machine_fields = Mock()
    return backup_manager


@pytest.fixture
def mock_execute_oc_command():
    """Mock oc command execution function"""
    return Mock()


@pytest.fixture
def mock_node_configurator():
    """Mock NodeConfigurator class"""
    configurator_instance = Mock()
    configurator_instance.update_nmstate_ip = Mock()
    configurator_instance.update_network_secret = Mock()
    configurator_instance.update_bmc_secret_name = Mock()
    configurator_instance.update_bmh = Mock()
    configurator_instance.update_machine_yaml = Mock()

    configurator_class = Mock(return_value=configurator_instance)
    return configurator_class


# =============================================================================
# Test _find_machine_template Function
# =============================================================================


class TestFindMachineTemplate:
    """Test the _find_machine_template function"""

    def test_find_worker_template_success(self, sample_mixed_machines_data, mock_printer):
        """Test finding a worker machine template successfully"""
        result = _find_machine_template(sample_mixed_machines_data, is_worker_template=True, printer=mock_printer)

        assert result is not None
        assert result["metadata"]["name"] == "two-xkb99-worker-abc12"
        assert result["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "worker"
        mock_printer.print_info.assert_called_with("Found worker machine template: two-xkb99-worker-abc12")

    def test_find_worker_template_fallback_to_master(self, mock_printer):
        """Test fallback to master template when no worker template found"""
        # Define test data inline - each test gets its own instance
        test_data = {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "machine.openshift.io/v1beta1",
                    "kind": "Machine",
                    "metadata": {
                        "name": "two-xkb99-master-0",
                        "namespace": "openshift-machine-api",
                        "labels": {
                            "machine.openshift.io/cluster-api-cluster": "two-xkb99",
                            "machine.openshift.io/cluster-api-machine-role": "master",
                            "machine.openshift.io/cluster-api-machine-type": "master",
                        },
                    },
                },
            ],
        }

        result = _find_machine_template(test_data, is_worker_template=True, printer=mock_printer)

        assert result is not None
        assert result["metadata"]["name"] == "two-xkb99-master-0"
        # Should modify labels for worker use
        assert result["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "worker"
        assert result["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-type"] == "worker"
        mock_printer.print_info.assert_called_with(
            "Adapting control plane machine template for worker use: two-xkb99-master-0"
        )

    def test_find_master_template(self, sample_control_plane_machines_data, mock_printer):
        """Test finding a master machine template"""
        result = _find_machine_template(
            sample_control_plane_machines_data, is_worker_template=False, printer=mock_printer
        )

        assert result is not None
        assert result["metadata"]["name"] == "two-xkb99-master-0"
        # When is_worker_template=False, it uses the first available machine (master) as-is
        assert result["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] == "master"
        mock_printer.print_info.assert_called_with("Using machine template: two-xkb99-master-0")

    def test_no_machines_data_provided(self, mock_printer):
        """Test exception when no machines data provided"""
        with pytest.raises(Exception, match="No machines data provided or no machines found"):
            _find_machine_template(None, is_worker_template=False, printer=mock_printer)

    def test_empty_machines_data(self, mock_printer):
        """Test exception when machines data is empty"""
        empty_data = {"items": []}
        with pytest.raises(Exception, match="No machines data provided or no machines found"):
            _find_machine_template(empty_data, is_worker_template=False, printer=mock_printer)

    def test_find_template_without_printer(self, sample_mixed_machines_data):
        """Test function works without printer (silent mode)"""
        result = _find_machine_template(sample_mixed_machines_data, is_worker_template=True, printer=None)

        assert result is not None
        assert result["metadata"]["name"] == "two-xkb99-worker-abc12"


# =============================================================================
# Test _extract_and_copy_secrets Function
# =============================================================================


class TestExtractAndCopySecrets:
    """Test the _extract_and_copy_secrets function"""

    @patch("modules.configuration_manager.find_node")
    def test_extract_and_copy_secrets_success(
        self,
        mock_find_node,
        mock_backup_manager,
        sample_control_plane_nodes_data,
        mock_execute_oc_command,
        mock_printer,
    ):
        """Test successful secret extraction and copying"""
        # Setup mocks
        mock_find_node.return_value = "ocp-control1.two.ocp4.example.com"
        mock_execute_oc_command.return_value = sample_control_plane_nodes_data
        mock_backup_manager.backup_secret.side_effect = [
            "/test/backup/network_backup.yaml",
            "/test/backup/bmc_backup.yaml",
        ]
        mock_backup_manager.extract_nmstate_config.return_value = "/test/backup/nmstate_temp"

        replacement_node = "new-control4"
        backup_dir = "/test/backup"

        result = _extract_and_copy_secrets(
            mock_backup_manager, replacement_node, backup_dir, mock_execute_oc_command, mock_printer
        )

        # Verify the result contains expected file paths
        expected_files = {
            "network_secret": f"{backup_dir}/{replacement_node}_network-config-secret.yaml",
            "bmc_secret": f"{backup_dir}/{replacement_node}-bmc-secret.yaml",
            "nmstate": f"{backup_dir}/{replacement_node}_nmstate",
        }
        assert result == expected_files

        # Verify function calls
        mock_execute_oc_command.assert_called_once_with(
            ["get", "nodes", "-l", "node-role.kubernetes.io/control-plane", "-o", "json"],
            json_output=True,
            printer=mock_printer,
        )
        mock_find_node.assert_called_once_with(
            check_ready=True, nodes_data=sample_control_plane_nodes_data, printer=mock_printer
        )

        # Verify backup manager calls
        mock_backup_manager.backup_secret.assert_any_call(
            "ocp-control1.two.ocp4.example.com",
            "network-config-secret",
            "_network-config-secret.yaml",
            "network secret",
        )
        mock_backup_manager.backup_secret.assert_any_call(
            "ocp-control1.two.ocp4.example.com",
            "bmc-secret",
            "-bmc-secret.yaml",
            "BMC secret",
        )
        mock_backup_manager.extract_nmstate_config.assert_called_once_with("ocp-control1.two.ocp4.example.com")

        # Verify file copy operations
        assert mock_backup_manager.make_file_copy.call_count == 3
        mock_printer.print_success.assert_called_with(
            "Extracted all configuration from ocp-control1.two.ocp4.example.com"
        )

    @patch("modules.configuration_manager.find_node")
    def test_extract_secrets_no_control_plane_data(
        self, mock_find_node, mock_backup_manager, mock_execute_oc_command, mock_printer
    ):
        """Test exception when no control plane data available"""
        mock_execute_oc_command.return_value = None

        with pytest.raises(Exception, match="Failed to retrieve control plane nodes data"):
            _extract_and_copy_secrets(mock_backup_manager, "new-node", "/backup", mock_execute_oc_command, mock_printer)

    @patch("modules.configuration_manager.find_node")
    def test_extract_secrets_no_working_control_node(
        self,
        mock_find_node,
        mock_backup_manager,
        sample_control_plane_nodes_data,
        mock_execute_oc_command,
        mock_printer,
    ):
        """Test exception when no working control plane node found"""
        mock_execute_oc_command.return_value = sample_control_plane_nodes_data
        mock_find_node.return_value = None

        with pytest.raises(Exception, match="No working control plane node found to extract secrets from"):
            _extract_and_copy_secrets(mock_backup_manager, "new-node", "/backup", mock_execute_oc_command, mock_printer)


# =============================================================================
# Test create_new_node_configs Function
# =============================================================================


class TestCreateConfigurationFromTemplate:
    """Test the create_new_node_configs function"""

    @patch("modules.configuration_manager._extract_and_copy_secrets")
    @patch("modules.configuration_manager._find_machine_template")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_create_config_control_plane_replacement(
        self,
        mock_yaml_dump,
        mock_yaml_load,
        mock_file,
        mock_find_machine_template,
        mock_extract_secrets,
        mock_backup_manager,
        sample_bmh_template_data,
        sample_control_plane_machines_data,
        mock_execute_oc_command,
        mock_printer,
    ):
        """Test configuration creation for control plane replacement"""
        # Setup mocks
        mock_yaml_load.return_value = sample_bmh_template_data
        mock_find_machine_template.return_value = sample_control_plane_machines_data["items"][0]
        mock_extract_secrets.return_value = {
            "network_secret": "/backup/new-node_network-config-secret.yaml",
            "bmc_secret": "/backup/new-node-bmc-secret.yaml",
            "nmstate": "/backup/new-node_nmstate",
        }
        mock_backup_manager.extract_bmh_fields.return_value = {"cleaned": "bmh_data"}
        mock_backup_manager.extract_machine_fields.return_value = {"cleaned": "machine_data"}

        template_file = "/backup/template_bmh.yaml"
        replacement_node = "new-control4"
        backup_dir = "/test/backup"

        result = create_new_node_configs(
            backup_manager=mock_backup_manager,
            backup_dir=backup_dir,
            template_backup_file=template_file,
            replacement_node=replacement_node,
            is_addition=False,
            is_worker_template=False,
            machines_data=sample_control_plane_machines_data,
            execute_oc_command=mock_execute_oc_command,
            printer=mock_printer,
        )

        # Verify all expected files are created
        expected_files = {
            "network_secret": "/backup/new-node_network-config-secret.yaml",
            "bmc_secret": "/backup/new-node-bmc-secret.yaml",
            "nmstate": "/backup/new-node_nmstate",
            "bmh": f"{backup_dir}/{replacement_node}_bmh.yaml",
            "machine": f"{backup_dir}/{replacement_node}_machine.yaml",
        }
        assert result == expected_files

        # Verify template loading and machine finding
        mock_file.assert_any_call(template_file, "r")
        mock_find_machine_template.assert_called_once_with(sample_control_plane_machines_data, False, mock_printer)

        # Verify file writing operations
        mock_file.assert_any_call(f"{backup_dir}/{replacement_node}_bmh.yaml", "w")
        mock_file.assert_any_call(f"{backup_dir}/{replacement_node}_machine.yaml", "w")
        assert mock_yaml_dump.call_count == 2

    @patch("modules.configuration_manager._extract_and_copy_secrets")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_create_config_worker_addition(
        self,
        mock_yaml_dump,
        mock_yaml_load,
        mock_file,
        mock_extract_secrets,
        mock_backup_manager,
        sample_bmh_template_data,
        mock_execute_oc_command,
        mock_printer,
    ):
        """Test configuration creation for worker addition"""
        # Setup mocks
        mock_yaml_load.return_value = sample_bmh_template_data
        mock_extract_secrets.return_value = {
            "network_secret": "/backup/new-worker_network-config-secret.yaml",
            "bmc_secret": "/backup/new-worker-bmc-secret.yaml",
            "nmstate": "/backup/new-worker_nmstate",
        }
        mock_backup_manager.extract_bmh_fields.return_value = {"cleaned": "bmh_data"}

        replacement_node = "new-worker1"
        backup_dir = "/test/backup"

        result = create_new_node_configs(
            backup_manager=mock_backup_manager,
            backup_dir=backup_dir,
            template_backup_file="/backup/template_bmh.yaml",
            replacement_node=replacement_node,
            is_addition=True,
            is_worker_template=False,  # Ignored for worker additions
            machines_data=None,  # Ignored for worker additions
            execute_oc_command=mock_execute_oc_command,
            printer=mock_printer,
        )

        # Should only have BMH file, no machine file for worker additions
        expected_files = {
            "network_secret": "/backup/new-worker_network-config-secret.yaml",
            "bmc_secret": "/backup/new-worker-bmc-secret.yaml",
            "nmstate": "/backup/new-worker_nmstate",
            "bmh": f"{backup_dir}/{replacement_node}_bmh.yaml",
        }
        assert result == expected_files
        assert "machine" not in result

        # Verify machine file not created
        mock_file.assert_any_call(f"{backup_dir}/{replacement_node}_bmh.yaml", "w")
        # Should only have one yaml.dump call (for BMH)
        assert mock_yaml_dump.call_count == 1

        mock_printer.print_info.assert_any_call(
            "Skipping machine template processing - MachineSet will handle machine creation"
        )
        mock_printer.print_info.assert_any_call(
            "Skipping machine creation - MachineSet will handle machine provisioning"
        )

    @patch("builtins.open", new_callable=mock_open)
    def test_create_config_invalid_template(
        self, mock_file, mock_backup_manager, mock_execute_oc_command, mock_printer
    ):
        """Test exception when template file is invalid"""
        # Mock yaml.safe_load to return None
        with patch("yaml.safe_load", return_value=None):
            with pytest.raises(Exception, match="Could not load BMH data from backup file"):
                create_new_node_configs(
                    backup_manager=mock_backup_manager,
                    backup_dir="/backup",
                    template_backup_file="/invalid/template.yaml",
                    replacement_node="new-node",
                    is_addition=False,
                    is_worker_template=False,
                    machines_data={"items": []},
                    execute_oc_command=mock_execute_oc_command,
                    printer=mock_printer,
                )


# =============================================================================
# Test configure_replacement_node Function
# =============================================================================


class TestConfigureReplacementNode:
    """Test the configure_replacement_node function"""

    def test_configure_replacement_node_all_files(self, mock_printer, mock_node_configurator):
        """Test configuring replacement node with all configuration files"""
        copied_files = {
            "nmstate": "/backup/new-node_nmstate",
            "network_secret": "/backup/new-node_network-config-secret.yaml",
            "bmc_secret": "/backup/new-node-bmc-secret.yaml",
            "bmh": "/backup/new-node_bmh.yaml",
            "machine": "/backup/new-node_machine.yaml",
        }

        replacement_node = "new-control4"
        replacement_node_ip = "192.168.1.100"
        replacement_node_bmc_ip = "192.168.94.100"
        replacement_node_mac_address = "52:54:00:aa:bb:cc"
        replacement_node_role = "master"
        sushy_uid = "test-uid-12345"

        configure_replacement_node(
            copied_files=copied_files,
            replacement_node=replacement_node,
            replacement_node_ip=replacement_node_ip,
            replacement_node_bmc_ip=replacement_node_bmc_ip,
            replacement_node_mac_address=replacement_node_mac_address,
            replacement_node_role=replacement_node_role,
            sushy_uid=sushy_uid,
            printer=mock_printer,
            NodeConfigurator=mock_node_configurator,
        )

        # Verify NodeConfigurator was instantiated
        mock_node_configurator.assert_called_once()
        configurator_instance = mock_node_configurator.return_value

        # Verify all configuration updates were called
        configurator_instance.update_nmstate_ip.assert_called_once_with(copied_files["nmstate"], replacement_node_ip)
        configurator_instance.update_network_secret.assert_called_once_with(
            copied_files["nmstate"], copied_files["network_secret"], replacement_node
        )
        configurator_instance.update_bmc_secret_name.assert_called_once_with(
            copied_files["bmc_secret"], replacement_node
        )
        configurator_instance.update_bmh.assert_called_once_with(
            copied_files["bmh"],
            replacement_node_bmc_ip,
            replacement_node_mac_address,
            replacement_node,
            sushy_uid,
            role=replacement_node_role,
        )
        # Check that update_machine_yaml was called with correct parameters
        call_args = configurator_instance.update_machine_yaml.call_args
        assert call_args[0] == (copied_files["machine"], replacement_node, replacement_node_role)
        assert call_args[1]["execute_oc_command"] is None
        assert call_args[1]["printer"] is not None

        # Verify printer output
        expected_print_calls = [
            call("Updating nmstate network configuration"),
            call("Updating network secret configuration"),
            call("Updating BMC secret configuration"),
            call("Updating BMH configuration"),
            call("Updating machine configuration"),
        ]
        mock_printer.print_action.assert_has_calls(expected_print_calls)

        expected_success_calls = [
            call("Updated network configuration"),
            call("Updated network secret"),
            call("Updated BMC secret name"),
            call("Updated BMH configuration"),
            call("Updated machine configuration"),
            call("Node configuration completed successfully"),
        ]
        mock_printer.print_success.assert_has_calls(expected_success_calls)

    def test_configure_replacement_node_partial_files(self, mock_printer, mock_node_configurator):
        """Test configuring replacement node with only some configuration files"""
        # Only provide BMH and network files, but no nmstate file
        copied_files = {
            "bmh": "/backup/new-worker_bmh.yaml",
            "network_secret": "/backup/new-worker_network-config-secret.yaml",
        }

        configure_replacement_node(
            copied_files=copied_files,
            replacement_node="new-worker1",
            replacement_node_ip="192.168.1.101",
            replacement_node_bmc_ip="192.168.94.101",
            replacement_node_mac_address="52:54:00:aa:bb:dd",
            replacement_node_role="worker",
            sushy_uid="worker-uid-12345",
            printer=mock_printer,
            NodeConfigurator=mock_node_configurator,
        )

        configurator_instance = mock_node_configurator.return_value

        # Verify only BMH update was called (network_secret needs nmstate file too)
        configurator_instance.update_bmh.assert_called_once()

        # Verify other methods were NOT called due to missing files
        configurator_instance.update_nmstate_ip.assert_not_called()
        configurator_instance.update_network_secret.assert_not_called()  # Needs both network_secret AND nmstate
        configurator_instance.update_bmc_secret_name.assert_not_called()
        configurator_instance.update_machine_yaml.assert_not_called()

    def test_configure_replacement_node_network_secret_with_nmstate(self, mock_printer, mock_node_configurator):
        """Test configuring replacement node with both network_secret and nmstate files"""
        # Provide both network_secret and nmstate to verify network secret update works
        copied_files = {
            "network_secret": "/backup/new-node_network-config-secret.yaml",
            "nmstate": "/backup/new-node_nmstate",
        }

        configure_replacement_node(
            copied_files=copied_files,
            replacement_node="new-node",
            replacement_node_ip="192.168.1.102",
            replacement_node_bmc_ip="192.168.94.102",
            replacement_node_mac_address="52:54:00:aa:bb:ee",
            replacement_node_role="worker",
            sushy_uid="test-uid",
            printer=mock_printer,
            NodeConfigurator=mock_node_configurator,
        )

        configurator_instance = mock_node_configurator.return_value

        # Verify both nmstate and network_secret updates were called
        configurator_instance.update_nmstate_ip.assert_called_once()
        configurator_instance.update_network_secret.assert_called_once()

        # Verify other methods were NOT called due to missing files
        configurator_instance.update_bmc_secret_name.assert_not_called()
        configurator_instance.update_bmh.assert_not_called()
        configurator_instance.update_machine_yaml.assert_not_called()

    def test_configure_replacement_node_no_files(self, mock_printer, mock_node_configurator):
        """Test configuring replacement node with no configuration files"""
        copied_files = {}

        configure_replacement_node(
            copied_files=copied_files,
            replacement_node="new-node",
            replacement_node_ip="192.168.1.102",
            replacement_node_bmc_ip="192.168.94.102",
            replacement_node_mac_address="52:54:00:aa:bb:ee",
            replacement_node_role="master",
            sushy_uid="test-uid",
            printer=mock_printer,
            NodeConfigurator=mock_node_configurator,
        )

        configurator_instance = mock_node_configurator.return_value

        # Verify no configuration methods were called
        configurator_instance.update_nmstate_ip.assert_not_called()
        configurator_instance.update_network_secret.assert_not_called()
        configurator_instance.update_bmc_secret_name.assert_not_called()
        configurator_instance.update_bmh.assert_not_called()
        configurator_instance.update_machine_yaml.assert_not_called()

        # Should still print completion message
        mock_printer.print_success.assert_called_with("Node configuration completed successfully")


# =============================================================================
# Integration Tests
# =============================================================================


class TestConfigurationManagerIntegration:
    """Integration tests combining multiple functions"""

    @patch("modules.configuration_manager._extract_and_copy_secrets")
    @patch("modules.configuration_manager._find_machine_template")
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("yaml.dump")
    def test_end_to_end_control_plane_replacement(
        self,
        mock_yaml_dump,
        mock_yaml_load,
        mock_file,
        mock_find_machine_template,
        mock_extract_secrets,
        mock_backup_manager,
        sample_bmh_template_data,
        sample_control_plane_machines_data,
        mock_execute_oc_command,
        mock_printer,
        mock_node_configurator,
    ):
        """Test end-to-end control plane replacement workflow"""
        # Setup mocks for create_new_node_configs
        mock_yaml_load.return_value = sample_bmh_template_data
        mock_find_machine_template.return_value = sample_control_plane_machines_data["items"][0]
        config_files = {
            "network_secret": "/backup/new-control4_network-config-secret.yaml",
            "bmc_secret": "/backup/new-control4-bmc-secret.yaml",
            "nmstate": "/backup/new-control4_nmstate",
            "bmh": "/backup/new-control4_bmh.yaml",
            "machine": "/backup/new-control4_machine.yaml",
        }
        mock_extract_secrets.return_value = config_files
        mock_backup_manager.extract_bmh_fields.return_value = {"cleaned": "bmh_data"}
        mock_backup_manager.extract_machine_fields.return_value = {"cleaned": "machine_data"}

        # Step 1: Create configuration from template
        created_files = create_new_node_configs(
            backup_manager=mock_backup_manager,
            backup_dir="/backup",
            template_backup_file="/backup/template_bmh.yaml",
            replacement_node="new-control4",
            is_addition=False,
            is_worker_template=False,
            machines_data=sample_control_plane_machines_data,
            execute_oc_command=mock_execute_oc_command,
            printer=mock_printer,
        )

        # Step 2: Configure the replacement node
        configure_replacement_node(
            copied_files=created_files,
            replacement_node="new-control4",
            replacement_node_ip="192.168.1.100",
            replacement_node_bmc_ip="192.168.94.100",
            replacement_node_mac_address="52:54:00:aa:bb:cc",
            replacement_node_role="master",
            sushy_uid="test-uid-12345",
            printer=mock_printer,
            NodeConfigurator=mock_node_configurator,
        )

        # Verify the workflow completed successfully
        assert len(created_files) == 5
        assert all(key in created_files for key in ["bmh", "machine", "network_secret", "bmc_secret", "nmstate"])

        # Verify NodeConfigurator was called with all configuration updates
        configurator_instance = mock_node_configurator.return_value
        configurator_instance.update_bmh.assert_called_once()
        configurator_instance.update_machine_yaml.assert_called_once()
        configurator_instance.update_network_secret.assert_called_once()


# =============================================================================
# Test Runner Configuration
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
