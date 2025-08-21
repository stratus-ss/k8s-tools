#!/usr/bin/env python3
"""
OpenShift Control Plane Replacement Tool - Modular Version

This is the main entry point for the OpenShift Control Plane Replacement Tool.
It imports and uses modularized components for better maintainability and testing.

For a single-file monolithic version, use the build target:
    make build-monolith
"""

import json
import time

from modules import (
    ArgumentsParser,
    BackupManager,
    NodeConfigurator,
    ResourceMonitor,
    determine_failed_control_node,
    exec_pod_command,
    execute_oc_command,
    format_runtime,
    normalize_node_role,
    printer,
)


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
