#!/usr/bin/env python3
"""Arguments Parser module for OpenShift Control Plane Replacement Tool."""

import argparse

from . import print_manager


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
