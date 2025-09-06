#!/usr/bin/env python3
"""Configuration Manager module for configuration file creation and management."""

import yaml

from .utilities import find_node


def _find_machine_template(machines_data, is_worker_template, printer=None):
    """
    Find a suitable machine template from cluster data.

    Args:
        machines_data: Machine data from cluster
        is_worker_template: Whether to prefer worker machine templates
        printer: Printer instance for logging

    Returns:
        dict: Machine template data

    Raises:
        Exception: If no suitable machine template is found
    """
    if not machines_data or not machines_data.get("items"):
        raise Exception("No machines data provided or no machines found")

    template_machine_data = None

    # If we found a worker template BMH, try to find a corresponding worker machine
    if is_worker_template:
        for machine in machines_data["items"]:
            labels = machine.get("metadata", {}).get("labels", {})
            if labels.get("machine.openshift.io/cluster-api-machine-role") == "worker":
                template_machine_data = machine
                if printer:
                    printer.print_info(f"Found worker machine template: {machine['metadata']['name']}")
                break

    # If no worker machine found, use the first available machine template
    if not template_machine_data:
        template_machine_data = machines_data["items"][0]

        # If it's a control plane template and we need a worker template, modify it for worker use
        labels = template_machine_data.get("metadata", {}).get("labels", {})
        if labels.get("machine.openshift.io/cluster-api-machine-role") == "master" and is_worker_template:
            if printer:
                printer.print_info(
                    f"Adapting control plane machine template for worker use: {template_machine_data['metadata']['name']}"
                )
            # Update labels for worker role
            template_machine_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"] = "worker"
            template_machine_data["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-type"] = "worker"
        else:
            if printer:
                printer.print_info(f"Using machine template: {template_machine_data['metadata']['name']}")

    if not template_machine_data:
        raise Exception("Could not find a machine to use as template")

    return template_machine_data


def _extract_and_copy_secrets(backup_manager, replacement_node, backup_dir, execute_oc_command, printer=None):
    """
    Extract secrets and nmstate configuration from a working control plane node.

    Args:
        backup_manager: BackupManager instance
        replacement_node: Name of replacement node (for file naming)
        backup_dir: Directory to store configuration files
        execute_oc_command: Function to execute OpenShift commands
        printer: Printer instance for logging

    Returns:
        dict: Dictionary of created configuration file paths

    Raises:
        Exception: If no working control plane node is found
    """
    # Find working control plane node
    if printer:
        printer.print_action("Retrieving control plane nodes information for secret extraction...")

    control_plane_nodes_data = execute_oc_command(
        ["get", "nodes", "-l", "node-role.kubernetes.io/control-plane", "-o", "json"], json_output=True, printer=printer
    )

    if not control_plane_nodes_data:
        raise Exception("Failed to retrieve control plane nodes data")

    control_plane_node = find_node(check_ready=True, nodes_data=control_plane_nodes_data, printer=printer)
    if not control_plane_node:
        raise Exception("No working control plane node found to extract secrets from")

    if printer:
        printer.print_info(f"Extracting secrets from control plane node: {control_plane_node}")

    # Extract secrets using BackupManager
    network_backup_file = backup_manager.backup_secret(
        control_plane_node, "network-config-secret", "_network-config-secret.yaml", "network secret"
    )
    bmc_backup_file = backup_manager.backup_secret(control_plane_node, "bmc-secret", "-bmc-secret.yaml", "BMC secret")
    temp_nmstate_file = backup_manager.extract_nmstate_config(control_plane_node)

    # Create target file paths and copy files
    config_files = {
        "network_secret": f"{backup_dir}/{replacement_node}_network-config-secret.yaml",
        "bmc_secret": f"{backup_dir}/{replacement_node}-bmc-secret.yaml",
        "nmstate": f"{backup_dir}/{replacement_node}_nmstate",
    }

    backup_manager.make_file_copy(network_backup_file, config_files["network_secret"])
    backup_manager.make_file_copy(bmc_backup_file, config_files["bmc_secret"])
    backup_manager.make_file_copy(temp_nmstate_file, config_files["nmstate"])

    if printer:
        printer.print_success(f"Extracted all configuration from {control_plane_node}")

    return config_files


def create_new_node_configs(
    backup_manager,
    backup_dir,
    template_backup_file,
    replacement_node,
    is_addition,
    is_worker_template,
    machines_data,
    printer=None,
    execute_oc_command=None,
    is_expansion=False,
):
    """
    Create all necessary configuration files for a new OpenShift node.

    This function generates the complete set of configuration files needed for node
    replacement or addition operations, including:
    - BareMetalHost (BMH) YAML configuration
    - Machine YAML configuration (for control plane operations only)
    - Network configuration secrets
    - BMC secrets for hardware management
    - nmstate network configuration files

    Args:
        backup_manager (BackupManager): Instance for file operations and data extraction
        backup_dir (str): Directory path to store generated configuration files
        template_backup_file (str): Path to template BMH backup file to use as base
        replacement_node (str): Name of the replacement node (used for file naming)
        is_addition (bool): True for worker addition, False for control plane operations
        is_worker_template (bool): Whether the template is from a worker node (ignored for additions)
        machines_data (dict): Machine data from cluster (ignored for worker additions)
        printer (PrintManager, optional): Printer instance for logging operations
        execute_oc_command (callable): Function to execute OpenShift CLI commands
        is_expansion (bool, optional): True for control plane expansion, False for replacement

    Returns:
        dict: Dictionary mapping config types to file paths:
            - 'network_secret': Path to network configuration secret file
            - 'bmc_secret': Path to BMC secret configuration file
            - 'nmstate': Path to nmstate network configuration file
            - 'bmh': Path to BareMetalHost YAML configuration file
            - 'machine': Path to Machine YAML file (control plane operations only)

    Raises:
        Exception: If template backup file cannot be loaded
        Exception: If no working control plane node found for secret extraction
        Exception: If no suitable machine template is found (control plane operations)

    Note:
        For worker additions (is_addition=True), machine configuration is skipped
        since MachineSet handles machine creation automatically.

        The generated files contain template data and require further customization
        via configure_replacement_node() to set node-specific values (IP, BMC, MAC, etc.).
    """

    # 1. Load BMH template
    with open(template_backup_file, "r") as f:
        template_bmh_data = yaml.safe_load(f)
    if not template_bmh_data:
        raise Exception(f"Could not load BMH data from backup file: {template_backup_file}")

    # 2. Find machine template (for control plane replacement and expansion)
    template_machine_data = None
    if not is_addition:
        template_machine_data = _find_machine_template(machines_data, is_worker_template, printer)
        if is_expansion and printer:
            printer.print_info("Using existing control plane machine as template for expansion")
    else:
        if printer:
            printer.print_info("Skipping machine template processing - MachineSet will handle machine creation")

    # 3. Extract secrets and nmstate from working control plane node
    config_files = _extract_and_copy_secrets(backup_manager, replacement_node, backup_dir, execute_oc_command, printer)

    # 4. Create BMH configuration file
    bmh_data = backup_manager.extract_bmh_fields(template_bmh_data)
    config_files["bmh"] = f"{backup_dir}/{replacement_node}_bmh.yaml"
    with open(config_files["bmh"], "w") as f:
        yaml.dump(bmh_data, f, default_flow_style=False)

    # 5. Create machine configuration file (for control plane replacement and expansion)
    if not is_addition and template_machine_data:
        machine_data = backup_manager.extract_machine_fields(template_machine_data)
        config_files["machine"] = f"{backup_dir}/{replacement_node}_machine.yaml"
        with open(config_files["machine"], "w") as f:
            yaml.dump(machine_data, f, default_flow_style=False)
        if printer:
            if is_expansion:
                printer.print_info("Created machine configuration file for control plane expansion")
            else:
                printer.print_info("Created machine configuration file for control plane replacement")
    elif is_addition and printer:
        printer.print_info("Skipping machine creation - MachineSet will handle machine provisioning")

    if printer:
        printer.print_success(f"Created {len(config_files)} configuration files from template")
    return config_files


def configure_replacement_node(
    copied_files,
    replacement_node,
    replacement_node_ip,
    replacement_node_bmc_ip,
    replacement_node_mac_address,
    replacement_node_role,
    sushy_uid=None,
    printer=None,
    NodeConfigurator=None,
    execute_oc_command=None,
):
    """
    Configure node-specific parameters in the generated configuration files.

    This function takes the template configuration files created by create_new_node_configs()
    and customizes them with node-specific values.

    Args:
        copied_files (dict): Dictionary of configuration file paths from create_new_node_configs()
            Expected keys: 'nmstate', 'network_secret', 'bmc_secret', 'bmh', 'machine'
        replacement_node (str): Name of the replacement node for labeling and identification
        replacement_node_ip (str): IP address to assign to the replacement node
        replacement_node_bmc_ip (str): BMC/iDRAC IP address for hardware management
        replacement_node_mac_address (str): MAC address of the replacement node's network interface
        replacement_node_role (str): Node role ('master' for control plane, 'worker' for worker nodes)
        sushy_uid (str, optional): Unique identifier for Sushy BMC management. Defaults to None.
        printer (PrintManager, optional): Printer instance for logging configuration updates
        NodeConfigurator (class): NodeConfigurator class for performing the actual updates
        execute_oc_command (callable, optional): Function to execute oc commands for machine name uniqueness checking

    Returns:
        None: Function modifies configuration files in-place

    Configuration Updates Performed:
        - nmstate: Updates IP address configuration
        - network_secret: Updates network configuration and node naming
        - bmc_secret: Updates BMC secret name for the replacement node
        - bmh: Updates BareMetalHost with BMC IP, MAC address, node name, and role
        - machine: Updates Machine configuration with node name and role (if present)

    Note:
        This function requires that the NodeConfigurator class is passed as a parameter
        to maintain dependency injection. All configuration files are modified in-place,
        so ensure backups exist if needed.
    """
    configurator = NodeConfigurator()

    # Update nmstate configuration if available
    if "nmstate" in copied_files:
        printer.print_action("Updating nmstate network configuration")
        configurator.update_nmstate_ip(copied_files["nmstate"], replacement_node_ip)
        printer.print_success("Updated network configuration")

    # Update network secret if available
    if "network_secret" in copied_files and "nmstate" in copied_files:
        printer.print_action("Updating network secret configuration")
        configurator.update_network_secret(copied_files["nmstate"], copied_files["network_secret"], replacement_node)
        printer.print_success("Updated network secret")

    # Update BMC secret if available
    if "bmc_secret" in copied_files:
        printer.print_action("Updating BMC secret configuration")
        configurator.update_bmc_secret_name(copied_files["bmc_secret"], replacement_node)
        printer.print_success("Updated BMC secret name")

    # Update BMH configuration if available
    if "bmh" in copied_files:
        printer.print_action("Updating BMH configuration")
        configurator.update_bmh(
            copied_files["bmh"],
            replacement_node_bmc_ip,
            replacement_node_mac_address,
            replacement_node,
            sushy_uid,
            role=replacement_node_role,
        )
        printer.print_success("Updated BMH configuration")

    # Update machine configuration if available
    if "machine" in copied_files:
        printer.print_action("Updating machine configuration")
        configurator.update_machine_yaml(
            copied_files["machine"],
            replacement_node,
            replacement_node_role,
            execute_oc_command=execute_oc_command,
            printer=printer,
        )
        printer.print_success("Updated machine configuration")

    printer.print_success("Node configuration completed successfully")
