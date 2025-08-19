#!/usr/bin/env python3

import argparse
import os
import sys
import yaml
import json
import base64
import subprocess
import time

# Message formatting functions
def print_header(message):
    """Print a section header with visual separation"""
    print(f"\n{'='*60}")
    print(f" {message.upper()}")
    print(f"{'='*60}")

def print_info(message):
    """Print informational message"""
    print(f"[INFO]  {message}")

def print_success(message):
    """Print success message"""
    print(f"[✓]     {message}")

def print_warning(message):
    """Print warning message"""
    print(f"[⚠️]     {message}")

def print_error(message):
    """Print error message"""
    print(f"[✗]     {message}")

def print_step(step_num, total_steps, message):
    """Print numbered step"""
    print(f"[{step_num}/{total_steps}] {message}")

def print_action(message):
    """Print action being performed"""
    print(f"[ACTION] {message}")

def print_result(message):
    """Print result of an action"""
    print(f"[RESULT] {message}")

def create_backup_dir(backups_dir):
    """
    Create a backup directory if it doesn't exist.
    
    Args:
        backups_dir: Path to the backup directory to create
    
    Returns:
        str: Path to the backup directory
    """
    if not os.path.exists(backups_dir):
        os.makedirs(backups_dir)
        print_success(f"Created backup directory: {backups_dir}")
    else:
        print_info(f"Using existing backup directory: {backups_dir}")
    return backups_dir
    
def exec_pod_command(pod_name, command, namespace, container_name=None, discard_stderr=False, return_on_error=False):
    """
    Execute a command in a pod and return the output.
    
    Args:
        pod_name: Name of the pod to execute command in
        command: List of command arguments to execute
        namespace: Kubernetes namespace
        container_name: Optional container name (if pod has multiple containers)
        discard_stderr: If True, discard stderr output
        return_on_error: If True, return stdout even when command exits with non-zero code
    
    Returns:
        Command stdout as string, or None if command failed and return_on_error=False
    """
    try:
        if container_name:
            exec_command = [
                'oc',
                'exec', '-n', namespace, pod_name, 
                '-c', container_name, 
                '--', *command]
        else:
            exec_command = [
                'oc',
                'exec', '-n', namespace, pod_name, 
                '--', *command]
        
        print_action(f"Executing pod command: {' '.join(exec_command)}")
        
        if discard_stderr:
            result = subprocess.run(
                exec_command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.DEVNULL, 
                text=True
            )
        else:
            result = subprocess.run(exec_command, capture_output=True, text=True)
        if result.returncode != 0:
            if not discard_stderr:  # Only print stderr if we're not discarding it
                print_error(f"Command failed: {result.stderr}")
            # Return stdout if explicitly requested, or if stdout contains data
            if return_on_error or (result.stdout and result.stdout.strip()):
                return result.stdout
            return None
        return result.stdout
    except Exception as e:
        print_error(f"Exception during command execution: {e}")
        return None
    
def execute_oc_command(command, json_output=False):
    """
    Execute an OpenShift CLI command and return the output.
    
    Args:
        command: List of command arguments to execute (excluding 'oc')
        json_output: If True, add JSON output flag and parse result as JSON
    
    Returns:
        str or dict: Command output as string, or parsed JSON dict if json_output=True.
                    Returns None on command failure.
    """
    try:
        if json_output:
            exec_command = ['oc', 'get', '-o', 'json', *command]
        else:
            exec_command = ['oc', *command]
        print_action(f"Executing oc command: {' '.join(exec_command)}")
        result = subprocess.run(exec_command, capture_output=True, text=True)
        if result.returncode != 0:
            print_error(f"Command failed: {result.stderr}")
            return None
        if json_output:
            return json.loads(result.stdout)
        return result.stdout
    except Exception as e:
        print_error(f"Exception during command execution: {e}")
        return None
    

def determine_failed_control_node():
    """
    Identify a control plane node that is in NotReady state.
    
    Args:
        None
    
    Returns:
        str or None: Name of the failed control node, or None if all nodes are ready
    """
    nodes_data = execute_oc_command(['nodes', "-l node-role.kubernetes.io/control-plane"], json_output=True)
    for node in nodes_data['items']:
        node_name = node['metadata']['name']
        node_status = node['status']['conditions']
        for condition in node_status:
            if condition['type'] == 'Ready' and condition['status'] != 'True':
                print_warning(f"Found failed control node: {node_name}")
                return node_name
    return None

def sanitize_metadata(data):
    """
    Remove unwanted metadata fields from a Kubernetes object.
    
    Args:
        data: Dictionary containing Kubernetes object data
    
    Returns:
        dict: The same dictionary with unwanted metadata fields removed
    """
    metadata_keys_to_remove = [
        'creationTimestamp', 
        'resourceVersion', 
        'uid', 
        'ownerReferences', 
        'annotations', 
        'managedFields', 
        'finalizers'
    ]
    
    if 'metadata' in data:
        for key in metadata_keys_to_remove:
            data['metadata'].pop(key, None)  # pop with None default won't raise KeyError
    
    return data
    
    
def extract_bmh_fields(bmh_data):
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
            "namespace": bmh_data.get("metadata", {}).get("namespace")
        },
        "spec": {
            "automatedCleaningMode": bmh_data.get("spec", {}).get("automatedCleaningMode"),
            "bmc": {
                "address": bmh_data.get("spec", {}).get("bmc", {}).get("address"),
                "credentialsName": bmh_data.get("spec", {}).get("bmc", {}).get("credentialsName"),
                "disableCertificateVerification": bmh_data.get("spec", {}).get("bmc", {}).get("disableCertificateVerification")
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
                "namespace": bmh_data.get("spec", {}).get("userData", {}).get("namespace")
            }
        }
    }
    return extracted
    
    
def main():
    """
    Main function to orchestrate OpenShift control plane node replacement.
    
    This function performs an 8-step process to safely remove a failed control plane node
    and prepare for its replacement:
    1. Set up backup directory
    2. Identify failed control node
    3. Process ETCD cluster recovery (remove failed member)
    4. Disable quorum guard
    5. Clean up ETCD secrets
    6. Create resource backups (BMH, secrets)
    7. Remove failed resources (BMH, machine)
    8. Validate removal and display manual steps
    
    Args:
        None (uses command-line arguments)
    
    Returns:
        None
    """
    print_header("OpenShift Control Plane Replacement Tool")
    
    parser = argparse.ArgumentParser(description="Replace the control plane in a Kubernetes cluster")
    parser.add_argument("--backup_dir", type=str, required=False, help="The full path to the backup directory")
    args = parser.parse_args()
    
    print_step(1, 8, "Setting up backup directory")
    cluster_cmd = ["config", "view", "-o", "jsonpath='{.clusters[].name}'"]
    cluster_name = execute_oc_command(cluster_cmd).split(":")[0].strip()
    if args.backup_dir:
        backup_dir = args.backup_dir
    else:
        backup_dir = f"/home/{os.getenv('USER', 'unknown')}/backup_yamls/{cluster_name}"
    print_info(f"Backup directory: {backup_dir}")
    create_backup_dir(backup_dir)
    
    print_step(2, 8, "Identifying failed control node")
    failed_node = determine_failed_control_node()
    if not failed_node:
        print_error("No failed control node found - exiting")
        return
    print_success(f"Identified failed node: {failed_node}")
    
    print_step(3, 8, "Processing ETCD cluster recovery")
    all_etcd_pods = execute_oc_command(["pods", "-n", "openshift-etcd", "-l", "app=etcd"], json_output=True)
    running_etcd_pod_names = [
        item['metadata']['name'] 
        for item in all_etcd_pods.get("items", []) 
        if item.get('status', {}).get('phase') == 'Running'
    ]
    counter = 0 
    # We want to remove the failed node from the list of running etcd pods
    # So that we can execute a command on the remaining etcd pods
    for pod_name in running_etcd_pod_names:
        if failed_node in pod_name:
            running_etcd_pod_names.pop(counter)
        counter += 1
    
    etcd_pod = running_etcd_pod_names[0]
    print_info(f"Entering pod: {etcd_pod}")
    failed_etcd_endpoint_json = json.loads(exec_pod_command(etcd_pod, ["etcdctl", "endpoint", "health", "--write-out=json"], "openshift-etcd", "etcd", discard_stderr=True ))
    for endpoint in failed_etcd_endpoint_json:
        if endpoint['health'] == False:
            etcd_failed_url = endpoint['endpoint']
            break
        else:
            etcd_failed_url = None
    if not etcd_failed_url:
        print_error("No failed ETCD endpoint found - exiting")
        return
    print_info(f"This ETCD endpoint has failed: {etcd_failed_url}")
    etcd_member_list_json = json.loads(exec_pod_command(etcd_pod, ["etcdctl", "member", "list", "--write-out=json"], "openshift-etcd", "etcd", discard_stderr=True ))
    for member in etcd_member_list_json['members']:
        if etcd_failed_url in member['clientURLs']:
            etcd_failed_member_id = member['ID']
            break
    if not etcd_failed_member_id:
        print_error("No failed ETCD member ID found - exiting")
        return
    print_info(f"This ETCD member ID has failed: {etcd_failed_member_id}")
    etcd_member_remove_json = json.loads(exec_pod_command(etcd_pod, ["etcdctl", "member", "remove", etcd_failed_member_id, "--write-out=json"], "openshift-etcd", "etcd", discard_stderr=True ))
    print_info(f"ETCD member remove output: {etcd_member_remove_json}")
    time.sleep(3)
    
    print_step(4, 8, "Disabling quorum guard")
    print_action("Disabling ETCD quorum guard")
    execute_oc_command(["patch", "etcd/cluster", "--type=merge", "-p", '{"spec": {"unsupportedConfigOverrides": {"useUnsupportedUnsafeNonHANonProductionUnstableEtcd": true}}}'])
    print_info("Waiting 120 seconds for ETCD cluster recovery...")
    time.sleep(120)
    print_success("Quorum guard disabled")
    
    bad_node_json = execute_oc_command(["nodes", "-l", "node-role.kubernetes.io/control-plane"], json_output=True)
    for node in bad_node_json['items']:
        if failed_node in node['metadata']['name']:
            bad_node = node['metadata']['name']
            break
    print_step(5, 8, "Cleaning up ETCD secrets")
    print_info(f"Removing secrets for failed node: {bad_node}")
    secrets = execute_oc_command(["secrets", "-n", "openshift-etcd"], json_output=True)
    deleted_secrets = 0
    for secret in secrets['items']:
        if bad_node in secret['metadata']['name']:
            print_action(f"Deleting secret: {secret['metadata']['name']}")
            execute_oc_command(["delete", "secret", secret['metadata']['name'], "-n", "openshift-etcd"])
            deleted_secrets += 1
    print_success(f"Deleted {deleted_secrets} ETCD secrets")

    
    machine_json = execute_oc_command(["bmh", "-n", "openshift-machine-api", "-l", "installer.openshift.io/role=control-plane"], json_output=True)
    for machine in machine_json['items']:
        if bad_node in machine['metadata']['name']:
            bad_machine = machine['spec']['consumerRef']['name']
            bmh_name = machine['metadata']['name']
            break
    if not bad_machine:
        print_error("No machine found - exiting")
        return
    
    if not bmh_name:
        print_error("No BMH found - exiting")
        return
    
    print_info(f"Found machine: {bad_machine}")
    print_info(f"Found BMH: {bmh_name}")
    print_step(6, 8, "Creating resource backups")
    
    print_action(f"Backing up BMH definition: {bmh_name}")
    bmh_data = execute_oc_command(["bmh", bmh_name, "-n", "openshift-machine-api"], json_output=True)
    extracted_bmh = extract_bmh_fields(bmh_data)

    # Save to YAML file
    with open(f"{backup_dir}/{bmh_name}_bmh.yaml", "w") as f:
        yaml.dump(extracted_bmh, f, default_flow_style=False)
    
    
    print_action("Backing up network configuration secret")
    network_secret_json = execute_oc_command(["secret", "-n", "openshift-machine-api", f"{bad_node}-network-config-secret"], json_output=True)
    network_secret_json_sanitized = sanitize_metadata(network_secret_json)
    
    print(f"Backing up Network Secret (if it exists): {network_secret_json_sanitized['metadata']['name']}")
    network_backup_file = f"{backup_dir}/{bad_node}_nmstate.yaml"
    with open(network_backup_file, "w") as f:
        yaml.dump(network_secret_json_sanitized, f)
    print_success(f"Network secret backup saved: {network_backup_file}")
    
    print_action("Extracting nmstate configuration")
    execute_oc_command(["extract", "-n", "openshift-machine-api", "secret", f"{bad_node}-network-config-secret", "--to", backup_dir])
    nmstate_file = f"{backup_dir}/{bad_node}_nmstate"
    os.rename(f"{backup_dir}/nmstate", nmstate_file)
    print_success(f"nmstate file extracted: {nmstate_file}")
    
    print_action("Backing up BMC secret")
    bmc_secret_json = execute_oc_command(["secret", "-n", "openshift-machine-api", f"{bad_node}-bmc-secret"], json_output=True)
    bmc_secret_json_sanitized = sanitize_metadata(bmc_secret_json)
    bmc_backup_file = f"{backup_dir}/{bad_node}-bmc-secret.yaml"
    with open(bmc_backup_file, "w") as f:
        yaml.dump(bmc_secret_json_sanitized, f)
    print_success(f"BMC secret backup saved: {bmc_backup_file}")
    
    print_step(7, 8, "Removing failed resources")
    
    print_action(f"Removing BMH: {bmh_name}")
    print_warning("This may take 5+ minutes as the machine gets wiped and powered off...")
    execute_oc_command(["delete", "bmh", bmh_name, "-n", "openshift-machine-api"])
    print_info(f"BMH removal initiated: {bmh_name}")

    print_action(f"Removing machine: {bad_machine}")
    del_machine_output = execute_oc_command(["delete", "machine", "-n", "openshift-machine-api", bad_machine])
    print_success(f"Machine removal completed: {bad_machine}")

    print_step(8, 8, "Validating resource removal")
    
    # Validate BMH removal
    try:
        bmh_output = execute_oc_command(["bmh", "-n", "openshift-machine-api", bmh_name], json_output=True)
        if bmh_output and bmh_output.get('items'):
            print_warning(f"BMH {bmh_name} still exists")
        else:
            print(f"✓ BMH {bmh_name} successfully removed")
    except Exception:
        print_success(f"BMH {bmh_name} not found (successfully removed)")

    # Validate machine removal
    try:
        machine_output = execute_oc_command(["machine", "-n", "openshift-machine-api", bad_machine], json_output=True)
        if machine_output and machine_output.get('items'):
            print_warning(f"Machine {bad_machine} still exists")
        else:
            print_success(f"Machine {bad_machine} successfully removed")
    except Exception:
        print_success(f"Machine {bad_machine} not found (successfully removed)")

    # Validate node removal
    try:
        node_output = execute_oc_command(["nodes", failed_node], json_output=True)
        if node_output and node_output.get('items'):
            print_warning(f"Node {failed_node} still exists")
        else:
            print_success(f"Node {failed_node} successfully removed")
    except Exception:
        print_success(f"Node {failed_node} not found (successfully removed)")
    
    # Show completion and manual steps
    print_header("Control Plane Replacement - Phase 1 Complete")
    print_success("Automated cleanup completed successfully!")
    print_warning("MANUAL STEPS REQUIRED:")
    print_info(f"1. Edit {backup_dir}/{bad_node}_nmstate - verify IP addresses")
    print_info(f"2. Create base64: base64 -w0 {backup_dir}/{bad_node}_nmstate")
    print_info(f"3. Edit {backup_dir}/{bad_node}_network-config-secret.yaml - update base64 data")
    print_info(f"4. Edit {backup_dir}/{bad_node}-bmc-secret.yaml - update name if needed")
    print_info(f"5. Edit {backup_dir}/{bmh_name}_bmh.yaml - review settings")
    print_info(f"6. Apply secrets: oc apply -f {backup_dir}/*secret*.yaml")
    print_info(f"7. Apply BMH: oc apply -f {backup_dir}/{bmh_name}_bmh.yaml")
    print_info("8. Watch and approve CSRs: oc get csr --watch")
    print_header("End of Automated Process")

if __name__ == "__main__":
    main()