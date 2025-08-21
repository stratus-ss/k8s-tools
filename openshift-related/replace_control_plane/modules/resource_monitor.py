#!/usr/bin/env python3
"""Resource Monitor module for OpenShift Control Plane Replacement Tool."""

import re
import time

from .print_manager import printer
from .utilities import execute_oc_command


class ResourceMonitor:
    """
    Handles 4-phase provisioning monitoring for OpenShift resources.

    Phases:
    1. BMH Available - Wait for BareMetalHost to reach Available state
    2. Machine Created - Create and verify Machine resource
    3. Machine Running - Wait for Machine to reach Running state
    4. Node Ready - Monitor CSRs and wait for Node to be Ready
    """

    def __init__(self, replacement_node, backup_dir, timeout_minutes=45, check_interval=25):
        """
        Initialize ResourceMonitor for 4-phase provisioning.

        Args:
            replacement_node (str): Name of the replacement node
            backup_dir (str): Directory containing backup files
            timeout_minutes (int): Total timeout for monitoring (default: 20 minutes)
            check_interval (int): Seconds between status checks (default: 15 seconds)
        """
        self.replacement_node = replacement_node
        self.backup_dir = backup_dir
        self.timeout_seconds = timeout_minutes * 60
        self.check_interval = check_interval
        self.start_time = None

        # Phase tracking
        self.bmh_available = False
        self.machine_created = False
        self.machine_running = False
        self.node_ready = False
        self.target_machine_name = None

        # CSR checking tracking
        self.machine_monitor_start_time = None
        self.csr_checking_enabled = False
        self.csr_check_delay_seconds = 10 * 60  # 10 minutes

    def monitor_provisioning_sequence(self):
        """
        Execute complete 4-phase provisioning sequence.

        Returns:
            tuple: (success: bool, phase_reached: str, error_message: str)
        """
        printer.print_info("Starting automated 4-phase provisioning sequence...")
        printer.print_info(f"Monitoring BMH: {self.replacement_node}")

        self.start_time = time.time()

        while not self.node_ready and not self._is_timeout_reached():
            self._print_progress()

            if not self.bmh_available:
                self._monitor_bmh_status()
            elif not self.machine_created:
                self._create_machine()
            elif not self.machine_running:
                self._monitor_machine_status()
            else:
                self._monitor_node_and_csrs()

            # Wait before next check (unless node is ready)
            if not self.node_ready:
                time.sleep(self.check_interval)

        return self._get_final_status()

    def _monitor_bmh_status(self):
        """Phase 1: Monitor BMH until Available state"""
        bmh_output = execute_oc_command(
            ["get", "bmh", self.replacement_node, "-n", "openshift-machine-api", "--no-headers"]
        )
        if bmh_output:
            # BMH output format: NAME STATE CONSUMER ONLINE ERROR AGE
            bmh_status = bmh_output.strip().split()[1] if len(bmh_output.strip().split()) > 1 else "Unknown"

            if bmh_status == "available":
                self.bmh_available = True
                printer.print_success(f"BMH {self.replacement_node} is now Available!")
                printer.print_info("BMH is ready for machine binding")
            elif bmh_status in ["provisioning", "provisioned", "externally-provisioned"]:
                printer.print_info(f"BMH {self.replacement_node} is {bmh_status}, waiting for Available status...")
            elif bmh_status == "error":
                printer.print_error(f"BMH {self.replacement_node} is in error state - manual intervention required")
            else:
                printer.print_info(f"BMH {self.replacement_node} status: {bmh_status}, continuing to monitor...")
        else:
            printer.print_info(f"BMH {self.replacement_node} not found yet, waiting for it to appear...")

    def _create_machine(self):
        """Phase 2: Create machine resource"""
        printer.print_success("BMH is available, now creating machine...")
        printer.print_info(f"Applying machine: oc apply -f {self.backup_dir}/{self.replacement_node}_machine.yaml")
        execute_oc_command(["apply", "-f", f"{self.backup_dir}/{self.replacement_node}_machine.yaml"])

        self.machine_created = True
        self.machine_monitor_start_time = time.time()  # Start tracking machine phase monitoring time
        printer.print_success("Machine created successfully!")
        printer.print_info("Now monitoring for machine to reach Running state...")
        printer.print_info(
            "Note: CSR checking will begin automatically if machine doesn't reach Provisioned state within 10 minutes"
        )

        # Brief pause to let machine creation propagate
        time.sleep(5)

    def _monitor_machine_status(self):
        """Phase 3: Monitor machine until Running state"""
        # monitoring loop created by cursor.ai
        # Check if we should enable CSR checking after 10 minutes
        if (
            not self.csr_checking_enabled
            and self.machine_monitor_start_time
            and (time.time() - self.machine_monitor_start_time) >= self.csr_check_delay_seconds
        ):
            self.csr_checking_enabled = True
            printer.print_info("⏰ 10 minutes elapsed - Now checking for CSRs while monitoring machine status...")

        # Check for pending CSRs if enabled (after 10 minutes)
        if self.csr_checking_enabled:
            self._approve_pending_csrs()

        # Get the actual machine name from the generated YAML
        machine_list_output = execute_oc_command(["get", "machines", "-n", "openshift-machine-api", "--no-headers"])
        if machine_list_output:
            machine_lines = machine_list_output.strip().split("\n")

            if not self.target_machine_name:
                self.target_machine_name = self._find_target_machine_name(machine_lines)

            if self.target_machine_name:
                machine_output = execute_oc_command(
                    ["get", "machine", self.target_machine_name, "-n", "openshift-machine-api", "--no-headers"]
                )
                if machine_output:
                    # Machine output format: NAME PHASE TYPE REGION ZONE AGE
                    machine_phase = (
                        machine_output.strip().split()[1] if len(machine_output.strip().split()) > 1 else "Unknown"
                    )

                    # Show CSR status in machine monitoring logs if enabled
                    csr_status = " (CSR checking active)" if self.csr_checking_enabled else ""
                    printer.print_info(f"Machine {self.target_machine_name} phase: {machine_phase}{csr_status}")

                    if machine_phase == "Running":
                        self.machine_running = True
                        printer.print_success(f"Machine {self.target_machine_name} is now Running!")
                        printer.print_info("Machine is ready, now monitoring for node and CSRs...")
                    elif machine_phase in ["Provisioning", "Provisioned"]:
                        wait_msg = (
                            f"Machine {self.target_machine_name} is {machine_phase}, waiting for Running state..."
                        )
                        if self.csr_checking_enabled:
                            wait_msg += " (CSRs being checked and approved as needed)"
                        printer.print_info(wait_msg)
                    elif machine_phase == "Failed":
                        printer.print_error(
                            f"Machine {self.target_machine_name} is in Failed state - manual intervention required"
                        )
                    else:
                        message = f"Machine {self.target_machine_name} phase: {machine_phase}, continuing to monitor..."
                        printer.print_info(f"{message}{csr_status}")
                else:
                    printer.print_info(f"Machine {self.target_machine_name} not found, continuing to monitor...")
            else:
                node_number_match = re.search(r"(\d+)", self.replacement_node)
                node_num = node_number_match.group(1) if node_number_match else "unknown"
                printer.print_info(f"Looking for machine with node number {node_num}...")
        else:
            printer.print_info("No machines found yet, waiting for machine to appear...")

    def _monitor_node_and_csrs(self):
        """Phase 4: Monitor CSRs and node readiness"""
        # Check for pending CSRs and approve them
        self._approve_pending_csrs()

        # Check if the replacement node is Ready
        self._check_node_readiness()

    def _approve_pending_csrs(self):
        """Discover and approve pending CSRs"""
        csr_output = execute_oc_command(["get", "csr", "--no-headers"])
        if csr_output:
            pending_csrs = []
            for line in csr_output.strip().split("\n"):
                if line and "Pending" in line:
                    csr_name = line.split()[0]
                    pending_csrs.append(csr_name)

            if pending_csrs:
                printer.print_info(f"Found {len(pending_csrs)} pending CSR(s), approving...")
                for csr_name in pending_csrs:
                    result = execute_oc_command(["adm", "certificate", "approve", csr_name])
                    if result:
                        printer.print_success(f"Approved CSR: {csr_name}")
                    else:
                        printer.print_warning(f"Failed to approve CSR: {csr_name}")

                # Brief pause after approving CSRs
                time.sleep(3)

    def _check_node_readiness(self):
        """Check if replacement node is Ready"""
        node_output = execute_oc_command(["get", "nodes", self.replacement_node, "--no-headers"])
        if node_output:
            # Node output format: NAME STATUS ROLES AGE VERSION
            node_status = node_output.strip().split()[1] if len(node_output.strip().split()) > 1 else "Unknown"
            printer.print_info(f"Node {self.replacement_node} status: {node_status}")

            if node_status == "Ready":
                self.node_ready = True
                printer.print_success(f"Node {self.replacement_node} is now Ready!")
            elif node_status == "NotReady":
                printer.print_info(f"Node {self.replacement_node} is still NotReady, continuing to monitor...")
        else:
            printer.print_info(f"Node {self.replacement_node} not found yet, waiting for it to appear...")

    def _find_target_machine_name(self, machine_lines):
        """Find machine name based on replacement node number"""
        node_number_match = re.search(r"(\d+)", self.replacement_node)
        if node_number_match:
            node_number = node_number_match.group(1)
            for line in machine_lines:
                if line and node_number in line:
                    machine_name = line.split()[0]
                    return machine_name
        return None

    def _is_timeout_reached(self):
        """Check if monitoring timeout has been reached"""
        return (time.time() - self.start_time) >= self.timeout_seconds

    def _get_elapsed_time(self):
        """Get elapsed time since monitoring started"""
        return int(time.time() - self.start_time)

    def _get_remaining_time(self):
        """Get remaining time before timeout"""
        return int(self.timeout_seconds - (time.time() - self.start_time))

    def _print_progress(self):
        """Print current progress and timing information"""
        elapsed_time = self._get_elapsed_time()
        remaining_time = self._get_remaining_time()

        # Add CSR checking status to progress
        csr_status = ""
        if self.machine_created and self.machine_monitor_start_time:
            machine_elapsed = int(time.time() - self.machine_monitor_start_time)
            if self.csr_checking_enabled:
                csr_status = f", CSR checking: ACTIVE (started at {self.csr_check_delay_seconds//60}min)"
            elif machine_elapsed < self.csr_check_delay_seconds:
                remaining_to_csr = self.csr_check_delay_seconds - machine_elapsed
                csr_status = f", CSR checking starts in: {remaining_to_csr}s"

        printer.print_info(f"Elapsed: {elapsed_time}s, Remaining: {remaining_time}s{csr_status}")

    def _get_final_status(self):
        """
        Get final monitoring status and error messages.

        Returns:
            tuple: (success: bool, phase_reached: str, error_message: str)
        """
        timeout_minutes = self.timeout_seconds // 60

        if self.node_ready:
            printer.print_success("Complete 4-phase provisioning sequence completed successfully!")
            printer.print_success("✓ Phase 1: BMH became Available")
            printer.print_success("✓ Phase 2: Machine created successfully")
            printer.print_success("✓ Phase 3: Machine reached Running state")
            printer.print_success("✓ Phase 4: CSRs approved and node is Ready")
            return True, "Phase 4: Node Ready", ""

        # Determine which phase failed and provide specific guidance
        printer.print_warning(f"TIMEOUT: Provisioning sequence did not complete within {timeout_minutes} minutes")

        if not self.bmh_available:
            printer.print_warning("FAILED at Phase 1: BMH did not become Available")
            printer.print_warning("Manual intervention required:")
            printer.print_info(f"1. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            printer.print_info(
                f"2. Check BMH details: oc describe bmh {self.replacement_node} -n openshift-machine-api"
            )
            printer.print_info("3. Check for hardware/networking issues")
            printer.print_info("4. Verify BMC credentials and connectivity")
            return False, "Phase 1: BMH Available", "BMH did not become Available"
        elif not self.machine_created:
            printer.print_warning("FAILED at Phase 2: Machine creation failed")
            printer.print_warning("Manual intervention required:")
            printer.print_info(f"1. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            printer.print_info("2. Manually create machine: oc apply -f <machine-yaml>")
            return False, "Phase 2: Machine Created", "Machine creation failed"
        elif not self.machine_running:
            printer.print_warning("FAILED at Phase 3: Machine did not reach Running state")
            printer.print_warning("Manual intervention required:")
            printer.print_info("1. Check machine status: oc get machines -n openshift-machine-api")
            printer.print_info("2. Check machine details: oc describe machine <machine-name> -n openshift-machine-api")
            printer.print_info("3. Check for provisioning errors in machine status")
            return False, "Phase 3: Machine Running", "Machine did not reach Running state"
        else:
            printer.print_warning("FAILED at Phase 4: Node did not become Ready")
            printer.print_warning("Manual intervention may be required:")
            printer.print_info(f"1. Check node status: oc get nodes {self.replacement_node}")
            printer.print_info("2. Check for pending CSRs: oc get csr --watch")
            printer.print_info("3. Manually approve CSRs if needed: oc adm certificate approve <csr-name>")
            printer.print_info("4. Check machine status: oc get machine -n openshift-machine-api")
            printer.print_info(f"5. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            return False, "Phase 4: Node Ready", "Node did not become Ready"
