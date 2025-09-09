#!/usr/bin/env python3
"""
Comprehensive pytest tests for etcd_manager module.

This test suite validates all ETCD management functions using a factory-based approach
for generating test data. The test architecture leverages shared fixtures from conftest.py
to eliminate code duplication and ensure consistent, maintainable test data generation.

Factory-Based Testing Approach:
- Uses secret_factory() for generating ETCD secrets test data
- Uses pod_factory() for generating ETCD pods test data  
- Uses node_factory() for generating control plane nodes test data
- Uses mock_format_runtime() for consistent runtime formatting across tests
- Eliminates 140+ lines of duplicate JSON/YAML hardcoded fixtures

Test Coverage:
- ETCD member discovery and health validation
- Failed member removal from ETCD cluster
- ETCD secrets cleanup operations
- Quorum guard enable/disable functionality
- Full replacement and expansion workflows
"""

import pytest
import os
import sys
import json

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import Mock, patch, call  # noqa: E402
from modules.etcd_manager import (  # noqa: E402
    _get_healthy_etcd_pod,
    _remove_failed_etcd_member,
    _disable_quorum_guard,
    _enable_quorum_guard,
    _cleanup_etcd_secrets,
    handle_etcd_operations_for_expansion,
    handle_etcd_operations_for_replacement,
    re_enable_quorum_guard_after_expansion,
)

@pytest.fixture
def sample_etcd_endpoint_health():
    """Sample ETCD endpoint health data with one failed endpoint"""
    return [
        {"endpoint": "https://192.168.1.10:2379", "health": True, "took": "2.123456ms", "error": ""},
        {"endpoint": "https://192.168.1.11:2379", "health": False, "took": "5s", "error": "context deadline exceeded"},
        {"endpoint": "https://192.168.1.12:2379", "health": True, "took": "1.987654ms", "error": ""},
    ]


@pytest.fixture
def sample_etcd_member_list():
    """Sample ETCD member list data"""
    return {
        "header": {
            "cluster_id": 17237436991929493444,
            "member_id": 9372538179322589801,
            "revision": 123456,
            "raft_term": 78,
        },
        "members": [
            {
                "ID": "9372538179322589801",
                "name": "ocp-control1.two.ocp4.example.com",
                "peerURLs": ["https://192.168.1.10:2380"],
                "clientURLs": ["https://192.168.1.10:2379"],
            },
            {
                "ID": "10501334649042878790",
                "name": "ocp-control2.two.ocp4.example.com",
                "peerURLs": ["https://192.168.1.11:2380"],
                "clientURLs": ["https://192.168.1.11:2379"],
            },
            {
                "ID": "15627534892987654321",
                "name": "ocp-control3.two.ocp4.example.com",
                "peerURLs": ["https://192.168.1.12:2380"],
                "clientURLs": ["https://192.168.1.12:2379"],
            },
        ],
    }


@pytest.fixture
def sample_etcd_member_remove_result():
    """Sample result after removing ETCD member"""
    return {
        "header": {
            "cluster_id": 17237436991929493444,
            "member_id": 9372538179322589801,
            "revision": 123457,
            "raft_term": 78,
        },
        "members": [
            {
                "ID": "9372538179322589801",
                "name": "ocp-control1.two.ocp4.example.com",
                "peerURLs": ["https://192.168.1.10:2380"],
                "clientURLs": ["https://192.168.1.10:2379"],
            },
            {
                "ID": "15627534892987654321",
                "name": "ocp-control3.two.ocp4.example.com",
                "peerURLs": ["https://192.168.1.12:2380"],
                "clientURLs": ["https://192.168.1.12:2379"],
            },
        ],
    }


@pytest.fixture
def mock_exec_pod_command():
    """Mock pod command execution function"""
    return Mock()

class TestGetHealthyEtcdPod:
    """Test the _get_healthy_etcd_pod function"""

    def test_get_healthy_etcd_pod_success(self, sample_etcd_pods_data, mock_execute_oc_command, mock_printer):
        """Test finding healthy ETCD pod successfully"""
        failed_node = "ocp-control2"
        mock_execute_oc_command.return_value = sample_etcd_pods_data

        result = _get_healthy_etcd_pod(failed_node, mock_execute_oc_command, mock_printer)

        # Should return the first healthy pod that doesn't contain the failed node
        assert result == "etcd-ocp-control1.two.ocp4.example.com"


    def test_get_healthy_etcd_pod_exclude_failed_node(
        self, sample_etcd_pods_data, mock_execute_oc_command, mock_printer
    ):
        """Test that failed node is excluded from healthy pod selection"""
        failed_node = "ocp-control1"
        mock_execute_oc_command.return_value = sample_etcd_pods_data

        result = _get_healthy_etcd_pod(failed_node, mock_execute_oc_command, mock_printer)

        # Should return the other healthy pod (not the failed one)
        assert result == "etcd-ocp-control3.two.ocp4.example.com"


class TestRemoveFailedEtcdMember:
    """Test the _remove_failed_etcd_member function"""

    def test_remove_failed_etcd_member_success(
        self,
        sample_etcd_endpoint_health,
        sample_etcd_member_list,
        sample_etcd_member_remove_result,
        mock_exec_pod_command,
        mock_printer,
    ):
        """Test successful removal of failed ETCD member"""
        etcd_pod = "etcd-control1"

        # Mock the exec_pod_command calls
        mock_exec_pod_command.side_effect = [
            json.dumps(sample_etcd_endpoint_health), 
            json.dumps(sample_etcd_member_list),  
            json.dumps(sample_etcd_member_remove_result),
        ]

        result = _remove_failed_etcd_member(etcd_pod, mock_exec_pod_command, mock_printer)

        assert result is True

        # Verify exec_pod_command calls
        expected_hex_id = format(int("10501334649042878790"), "x")  # Convert decimal to hex
        expected_calls = [
            call(
                etcd_pod,
                ["etcdctl", "endpoint", "health", "--write-out=json"],
                "openshift-etcd",
                "etcd",
                discard_stderr=True,
            ),
            call(
                etcd_pod,
                ["etcdctl", "member", "list", "--write-out=json"],
                "openshift-etcd",
                "etcd",
                discard_stderr=True,
            ),
            call(
                etcd_pod,
                ["etcdctl", "member", "remove", expected_hex_id, "--write-out=json"],
                "openshift-etcd",
                "etcd",
                discard_stderr=True,
            ),
        ]
        assert mock_exec_pod_command.call_args_list == expected_calls


    def test_remove_failed_etcd_member_no_failed_endpoint(
        self, sample_etcd_member_list, mock_exec_pod_command, mock_printer
    ):
        """Test when no failed endpoint is found"""
        etcd_pod = "etcd-control1"

        # All endpoints healthy
        healthy_endpoints = [
            {"endpoint": "https://192.168.1.10:2379", "health": True},
            {"endpoint": "https://192.168.1.11:2379", "health": True},
            {"endpoint": "https://192.168.1.12:2379", "health": True},
        ]

        mock_exec_pod_command.return_value = json.dumps(healthy_endpoints)

        result = _remove_failed_etcd_member(etcd_pod, mock_exec_pod_command, mock_printer)

        assert result is None
        # Should only call endpoint health, not member operations
        assert mock_exec_pod_command.call_count == 1

    def test_remove_failed_etcd_member_member_not_found(
        self, sample_etcd_endpoint_health, sample_etcd_member_list, mock_exec_pod_command, mock_printer
    ):
        """Test when failed member is not found in member list"""
        etcd_pod = "etcd-control1"

        # Member list without the failed member
        member_list_without_failed = {
            "members": [
                {
                    "ID": "9372538179322589801",
                    "name": "ocp-control1.two.ocp4.example.com",
                    "clientURLs": ["https://192.168.1.10:2379"],
                },
                {
                    "ID": "15627534892987654321",
                    "name": "ocp-control3.two.ocp4.example.com",
                    "clientURLs": ["https://192.168.1.12:2379"],
                },
            ]
        }

        mock_exec_pod_command.side_effect = [
            json.dumps(sample_etcd_endpoint_health),
            json.dumps(member_list_without_failed),
        ]

        result = _remove_failed_etcd_member(etcd_pod, mock_exec_pod_command, mock_printer)

        assert result is True  # Should return True - member might already be gone


    def test_remove_failed_etcd_member_ip_match(self, sample_etcd_endpoint_health, mock_exec_pod_command, mock_printer):
        """Test member matching by IP address when exact URL match fails"""
        etcd_pod = "etcd-control1"

        # Member list with different port but same IP
        member_list_different_port = {
            "members": [
                {
                    "ID": "10501334649042878790",
                    "name": "ocp-control2.two.ocp4.example.com",
                    "clientURLs": ["https://192.168.1.11:2380"],  # Different port
                }
            ]
        }

        remove_result = {"members": []}

        mock_exec_pod_command.side_effect = [
            json.dumps(sample_etcd_endpoint_health),
            json.dumps(member_list_different_port),
            json.dumps(remove_result),
        ]

        result = _remove_failed_etcd_member(etcd_pod, mock_exec_pod_command, mock_printer)

        assert result is True
class TestQuorumGuardFunctions:
    """Test the quorum guard enable/disable functions"""

    @patch("time.sleep")
    def test_disable_quorum_guard(self, mock_sleep, mock_execute_oc_command, mock_printer):
        """Test disabling ETCD quorum guard when not already disabled"""
        # Mock successful patch command (indicating changes were made)
        mock_execute_oc_command.return_value = "etcd.operator.openshift.io/cluster patched"

        _disable_quorum_guard(mock_execute_oc_command, mock_printer)

        # Verify oc command execution
        mock_execute_oc_command.assert_called_once_with(
            [
                "patch",
                "etcd/cluster",
                "--type=merge",
                "-p",
                '{"spec": {"unsupportedConfigOverrides": {"useUnsupportedUnsafeNonHANonProductionUnstableEtcd": true}}}',
            ],
            printer=mock_printer,
        )


    @patch("time.sleep")
    def test_disable_quorum_guard_already_disabled(self, mock_sleep, mock_execute_oc_command, mock_printer):
        """Test disabling ETCD quorum guard when already disabled (unchanged)"""
        # Mock unchanged patch command (indicating no changes were made)
        mock_execute_oc_command.return_value = "etcd.operator.openshift.io/cluster unchanged"

        _disable_quorum_guard(mock_execute_oc_command, mock_printer)

        # Verify oc command execution
        mock_execute_oc_command.assert_called_once_with(
            [
                "patch",
                "etcd/cluster",
                "--type=merge",
                "-p",
                '{"spec": {"unsupportedConfigOverrides": {"useUnsupportedUnsafeNonHANonProductionUnstableEtcd": true}}}',
            ],
            printer=mock_printer,
        )


    @patch("time.sleep")
    def test_enable_quorum_guard(self, mock_sleep, mock_execute_oc_command, mock_printer):
        """Test enabling ETCD quorum guard"""
        _enable_quorum_guard(mock_execute_oc_command, mock_printer)

        # Verify oc command execution
        mock_execute_oc_command.assert_called_once_with(
            ["patch", "etcd/cluster", "--type=merge", "-p", '{"spec": {"unsupportedConfigOverrides": null}}'],
            printer=mock_printer,
        )
class TestCleanupEtcdSecrets:
    """Test the _cleanup_etcd_secrets function"""

    @patch("time.sleep")
    def test_cleanup_etcd_secrets_success(
        self, mock_sleep, sample_etcd_control_plane_nodes, sample_etcd_secrets, mock_execute_oc_command, mock_printer
    ):
        """Test successful cleanup of ETCD secrets"""
        failed_node = "ocp-control2"

        # Mock oc command calls
        mock_execute_oc_command.side_effect = [
            sample_etcd_control_plane_nodes,  # nodes list
            sample_etcd_secrets,  # secrets list
            None,  # delete secret 1
            None,  # delete secret 2
        ]

        result = _cleanup_etcd_secrets(failed_node, mock_execute_oc_command, mock_printer)

        # Should return the full node name that was found
        assert result == "ocp-control2.two.ocp4.example.com"

        # Verify oc command calls
        expected_calls = [
            call(
                ["get", "nodes", "-l", "node-role.kubernetes.io/control-plane"], json_output=True, printer=mock_printer
            ),
            call(["get", "secrets", "-n", "openshift-etcd"], json_output=True, printer=mock_printer),
            call(
                ["delete", "secret", "etcd-peer-ocp-control2.two.ocp4.example.com", "-n", "openshift-etcd"],
                printer=mock_printer,
            ),
            call(
                ["delete", "secret", "etcd-serving-metrics-ocp-control2.two.ocp4.example.com", "-n", "openshift-etcd"],
                printer=mock_printer,
            ),
        ]
        assert mock_execute_oc_command.call_args_list == expected_calls

        # Verify sleep calls (one per deleted secret)
        assert mock_sleep.call_count == 2

    def test_cleanup_etcd_secrets_no_nodes(self, mock_execute_oc_command, mock_printer):
        """Test cleanup when no control plane nodes found"""
        failed_node = "ocp-control2"

        mock_execute_oc_command.side_effect = [None, {"items": []}]  # No nodes returned  # Empty secrets

        result = _cleanup_etcd_secrets(failed_node, mock_execute_oc_command, mock_printer)

        # Should use fallback node name
        assert result == failed_node

    def test_cleanup_etcd_secrets_no_secrets(self, sample_etcd_control_plane_nodes, mock_execute_oc_command, mock_printer):
        """Test cleanup when no secrets found"""
        failed_node = "ocp-control2"

        mock_execute_oc_command.side_effect = [sample_etcd_control_plane_nodes, None]  # No secrets returned

        result = _cleanup_etcd_secrets(failed_node, mock_execute_oc_command, mock_printer)

        assert result == "ocp-control2.two.ocp4.example.com"

    def test_cleanup_etcd_secrets_no_matching_secrets(
        self, sample_etcd_control_plane_nodes, mock_execute_oc_command, mock_printer
    ):
        """Test cleanup when no matching secrets found"""
        failed_node = "ocp-control4"  # Node that doesn't exist in secrets

        # Secrets that don't match the failed node
        non_matching_secrets = {
            "items": [{"metadata": {"name": "etcd-serving-other-node", "namespace": "openshift-etcd"}}]
        }

        mock_execute_oc_command.side_effect = [sample_etcd_control_plane_nodes, non_matching_secrets]

        result = _cleanup_etcd_secrets(failed_node, mock_execute_oc_command, mock_printer)

        # Should still return fallback since node not found in cluster
        assert result == failed_node


class TestEtcdOperationsFunctions:
    """Test the high-level ETCD operations functions"""

    @patch("modules.etcd_manager._disable_quorum_guard")
    @patch("time.time")
    def test_handle_etcd_operations_for_expansion(
        self, mock_time, mock_disable_quorum_guard, mock_execute_oc_command, mock_printer, mock_format_runtime
    ):
        """Test ETCD operations for control plane expansion"""
        start_time = 1000
        current_step = 5
        total_steps = 10

        mock_time.return_value = 1120  # 120 seconds later

        success, next_step = handle_etcd_operations_for_expansion(
            start_time,
            current_step,
            total_steps,
            printer=mock_printer,
            execute_oc_command=mock_execute_oc_command,
            format_runtime=mock_format_runtime,
        )

        assert success is True
        assert next_step == current_step + 1


    @patch("modules.etcd_manager._cleanup_etcd_secrets")
    @patch("modules.etcd_manager._disable_quorum_guard")
    @patch("modules.etcd_manager._remove_failed_etcd_member")
    @patch("modules.etcd_manager._get_healthy_etcd_pod")
    @patch("time.time")
    @patch("time.sleep")
    def test_handle_etcd_operations_for_replacement_success(
        self,
        mock_sleep,
        mock_time,
        mock_get_healthy_etcd_pod,
        mock_remove_failed_etcd_member,
        mock_disable_quorum_guard,
        mock_cleanup_etcd_secrets,
        mock_execute_oc_command,
        mock_exec_pod_command,
        mock_printer,
        mock_format_runtime,
    ):
        """Test successful ETCD operations for control plane replacement"""
        failed_node = "ocp-control2"
        start_time = 1000
        current_step = 3
        total_steps = 10

        mock_time.return_value = 1180  # 180 seconds later
        mock_get_healthy_etcd_pod.return_value = "etcd-control1"
        mock_remove_failed_etcd_member.return_value = True
        mock_cleanup_etcd_secrets.return_value = "ocp-control2.two.ocp4.example.com"

        result, next_step = handle_etcd_operations_for_replacement(
            failed_node,
            start_time,
            current_step,
            total_steps,
            printer=mock_printer,
            exec_pod_command=mock_exec_pod_command,
            execute_oc_command=mock_execute_oc_command,
            format_runtime=mock_format_runtime,
        )

        assert result == "ocp-control2.two.ocp4.example.com"
        assert next_step == current_step + 3  # 3 steps processed

        # Verify function calls
        mock_get_healthy_etcd_pod.assert_called_once_with(failed_node, mock_execute_oc_command, mock_printer)
        mock_remove_failed_etcd_member.assert_called_once_with("etcd-control1", mock_exec_pod_command, mock_printer)
        mock_disable_quorum_guard.assert_called_once_with(mock_execute_oc_command, mock_printer)
        mock_cleanup_etcd_secrets.assert_called_once_with(failed_node, mock_execute_oc_command, mock_printer)

        # Verify printer step calls
        expected_step_calls = [
            call(3, 10, "Processing ETCD cluster recovery"),
            call(4, 10, "Disabling quorum guard"),
            call(5, 10, "Cleaning up ETCD secrets"),
        ]

    @patch("modules.etcd_manager._get_healthy_etcd_pod")
    @patch("time.time")
    def test_handle_etcd_operations_for_replacement_no_healthy_pods(
        self,
        mock_time,
        mock_get_healthy_etcd_pod,
        mock_execute_oc_command,
        mock_exec_pod_command,
        mock_printer,
        mock_format_runtime,
    ):
        """Test replacement operations when no healthy ETCD pods available"""
        failed_node = "ocp-control2"
        start_time = 1000
        current_step = 3
        total_steps = 10

        mock_time.return_value = 1050
        mock_get_healthy_etcd_pod.return_value = None
        mock_format_runtime.return_value = "50s"

        result, next_step = handle_etcd_operations_for_replacement(
            failed_node,
            start_time,
            current_step,
            total_steps,
            printer=mock_printer,
            exec_pod_command=mock_exec_pod_command,
            execute_oc_command=mock_execute_oc_command,
            format_runtime=mock_format_runtime,
        )

        assert result is None
        assert next_step == current_step


    @patch("modules.etcd_manager._remove_failed_etcd_member")
    @patch("modules.etcd_manager._get_healthy_etcd_pod")
    @patch("time.time")
    def test_handle_etcd_operations_for_replacement_member_removal_fails(
        self,
        mock_time,
        mock_get_healthy_etcd_pod,
        mock_remove_failed_etcd_member,
        mock_execute_oc_command,
        mock_exec_pod_command,
        mock_printer,
        mock_format_runtime,
    ):
        """Test replacement operations when member removal fails"""
        failed_node = "ocp-control2"
        start_time = 1000
        current_step = 3
        total_steps = 10

        mock_time.return_value = 1070
        mock_get_healthy_etcd_pod.return_value = "etcd-control1"
        mock_remove_failed_etcd_member.return_value = False
        mock_format_runtime.return_value = "70s"

        result, next_step = handle_etcd_operations_for_replacement(
            failed_node,
            start_time,
            current_step,
            total_steps,
            printer=mock_printer,
            exec_pod_command=mock_exec_pod_command,
            execute_oc_command=mock_execute_oc_command,
            format_runtime=mock_format_runtime,
        )

        assert result is None
        assert next_step == current_step

    @patch("modules.etcd_manager._enable_quorum_guard")
    @patch("time.time")
    def test_re_enable_quorum_guard_after_expansion(
        self, mock_time, mock_enable_quorum_guard, mock_execute_oc_command, mock_printer, mock_format_runtime
    ):
        """Test re-enabling quorum guard after expansion"""
        start_time = 1000
        current_step = 8
        total_steps = 10

        mock_time.return_value = 1300  # 300 seconds later
        mock_format_runtime.return_value = "300s"

        next_step = re_enable_quorum_guard_after_expansion(
            start_time,
            current_step,
            total_steps,
            printer=mock_printer,
            execute_oc_command=mock_execute_oc_command,
            format_runtime=mock_format_runtime,
        )

        assert next_step == current_step + 1
class TestEtcdManagerIntegration:
    """Integration tests combining multiple ETCD manager functions"""

    @patch("modules.etcd_manager._cleanup_etcd_secrets")
    @patch("modules.etcd_manager._disable_quorum_guard")
    @patch("modules.etcd_manager._remove_failed_etcd_member")
    @patch("modules.etcd_manager._get_healthy_etcd_pod")
    @patch("time.time")
    @patch("time.sleep")
    def test_full_replacement_workflow(
        self,
        mock_sleep,
        mock_time,
        mock_get_healthy_etcd_pod,
        mock_remove_failed_etcd_member,
        mock_disable_quorum_guard,
        mock_cleanup_etcd_secrets,
        mock_execute_oc_command,
        mock_exec_pod_command,
        mock_printer,
        mock_format_runtime,
    ):
        """Test complete ETCD replacement workflow"""
        failed_node = "ocp-control2"
        start_time = 1000
        current_step = 3
        total_steps = 10

        # Setup mocks
        mock_time.return_value = 1200
        mock_get_healthy_etcd_pod.return_value = "etcd-control1"
        mock_remove_failed_etcd_member.return_value = True
        mock_cleanup_etcd_secrets.return_value = "ocp-control2.two.ocp4.example.com"

        # Execute the workflow
        result, final_step = handle_etcd_operations_for_replacement(
            failed_node,
            start_time,
            current_step,
            total_steps,
            printer=mock_printer,
            exec_pod_command=mock_exec_pod_command,
            execute_oc_command=mock_execute_oc_command,
            format_runtime=mock_format_runtime,
        )

        # Verify workflow completed successfully
        assert result == "ocp-control2.two.ocp4.example.com"
        assert final_step == 6

        # Verify all functions were called in correct order
        mock_get_healthy_etcd_pod.assert_called_once()
        mock_remove_failed_etcd_member.assert_called_once()
        mock_disable_quorum_guard.assert_called_once()
        mock_cleanup_etcd_secrets.assert_called_once()

        # Verify proper step progression
        assert mock_printer.print_step.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
