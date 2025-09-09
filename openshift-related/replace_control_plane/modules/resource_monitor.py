#!/usr/bin/env python3
"""Resource Monitor module for OpenShift Control Plane Replacement Tool."""

import re
import time


class ResourceMonitor:
    """
    Handles 4-phase provisioning monitoring for OpenShift resources.

    Phases:
    1. BMH Provisioned - Wait for BareMetalHost to reach Provisioned state
    2. Machine Created - Create and verify Machine resource
    3. Machine Running - Wait for Machine to reach Running state
    4. Node Ready - Monitor CSRs and wait for Node to be Ready
    """

    def __init__(
        self,
        replacement_node,
        backup_dir,
        timeout_minutes=45,
        check_interval=25,
        is_addition=False,
        is_expansion=False,
        printer=None,
        execute_oc_command=None,
    ):
        """
        Initialize ResourceMonitor for 4-phase provisioning.

        Args:
            replacement_node (str): Name of the replacement node
            backup_dir (str): Directory containing backup files
            timeout_minutes (int): Total timeout for monitoring (default: 20 minutes)
            check_interval (int): Seconds between status checks (default: 15 seconds)
            is_addition (bool): True if this is a worker addition, False for control plane operations
            is_expansion (bool): True if this is a control plane expansion, False for control plane replacement
            printer: Printer instance for output
            self.execute_oc_command: Function to execute oc commands
        """
        self.replacement_node = replacement_node
        self.backup_dir = backup_dir
        self.timeout_seconds = timeout_minutes * 60
        self.check_interval = check_interval
        self.is_addition = is_addition
        self.is_expansion = is_expansion
        self.start_time = None
        self.printer = printer
        self.execute_oc_command = execute_oc_command

        # Phase tracking
        self.bmh_provisioned = False
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
        self.printer.print_info("Starting automated 4-phase provisioning sequence...")
        self.printer.print_info(f"Monitoring BMH: {self.replacement_node}")

        self.start_time = time.time()

        while not self.node_ready and not self._is_timeout_reached():
            self._print_progress()

            if not self.bmh_provisioned:
                self._monitor_bmh_status()
            elif not self.machine_created:
                if self.is_addition:
                    # For worker additions, MachineSet creates machine automatically - discover it
                    self._discover_machine_for_worker_addition()
                else:
                    # For control plane operations (both replacement and expansion),
                    # machine was already applied in previous step - just discover it
                    self._discover_machine_for_control_plane()
            elif not self.machine_running:
                self._monitor_machine_status()
            else:
                self._monitor_node_and_csrs()

            # Wait before next check (unless node is ready)
            if not self.node_ready:
                time.sleep(self.check_interval)

        return self._get_final_status()

    def _monitor_bmh_status(self):
        """Phase 1: Monitor BMH until Provisioned state using JSON processing"""
        bmh_data = self.execute_oc_command(
            ["get", "bmh", self.replacement_node, "-n", "openshift-machine-api", "-o", "json"], json_output=True
        )
        if bmh_data:
            # Extract BMH state from JSON structure
            bmh_status = bmh_data.get("status", {}).get("provisioning", {}).get("state", "Unknown")

            if bmh_status == "provisioned":
                self.bmh_provisioned = True
                self.printer.print_success(f"BMH {self.replacement_node} is now Provisioned!")
                self.printer.print_success("BMH is ready for machine binding")
            elif bmh_status in ["provisioning", "ready", "available"]:
                self.printer.print_info(
                    f"BMH {self.replacement_node} is {bmh_status}, waiting for Provisioned status..."
                )
            elif bmh_status == "error":
                self.printer.print_error(
                    f"BMH {self.replacement_node} is in error state - manual intervention required"
                )
            else:
                self.printer.print_info(f"BMH {self.replacement_node} status: {bmh_status}, continuing to monitor...")
        else:
            self.printer.print_info(f"BMH {self.replacement_node} not found yet, waiting for it to appear...")

    def _discover_machine_for_worker_addition(self):
        """Phase 2 (Worker Addition): Discover machine created by MachineSet scaling"""
        self.printer.print_info("BMH is provisioned, looking for machine created by MachineSet...")

        # Try to get machine name from BMH consumerRef
        if not self.target_machine_name:
            self.target_machine_name = self._get_machine_name_from_bmh_consumerref()

        if self.target_machine_name:
            self.machine_created = True
            self.machine_monitor_start_time = time.time()
            self.printer.print_success(f"Machine discovered: {self.target_machine_name}")
            self.printer.print_info("MachineSet has successfully created the machine, now monitoring status...")
            self.printer.print_info(
                "Note: CSR checking will begin automatically if machine doesn't reach Provisioned state within 10 minutes"
            )
        else:
            self.printer.print_info("Waiting for MachineSet to create machine and update BMH consumerRef...")

    def _discover_machine_for_control_plane(self):
        """Phase 2 (Control Plane Operations): Discover machine that was already applied"""
        self.printer.print_success("BMH is provisioned, now looking for applied machine...")

        # Try to get machine name from BMH consumerRef
        if not self.target_machine_name:
            self.target_machine_name = self._get_machine_name_from_bmh_consumerref()

        if self.target_machine_name:
            self.machine_created = True
            self.machine_monitor_start_time = time.time()
            self.printer.print_success(f"Machine discovered: {self.target_machine_name}")
            self.printer.print_info("Machine was successfully applied earlier, now monitoring status...")
            self.printer.print_info(
                "Note: CSR checking will begin automatically if machine doesn't reach Provisioned state within 10 minutes"
            )
        else:
            self.printer.print_info("Waiting for applied machine to bind to BMH...")

    def _get_machine_info(self):
        """Get machine list and determine target machine name and phase."""
        machines_data = self.execute_oc_command(
            ["get", "machines", "-n", "openshift-machine-api", "-o", "json"], json_output=True
        )
        machine_phase = None

        if machines_data and machines_data.get("items"):
            if not self.target_machine_name:
                # Try to get machine name from BMH consumerRef first (most reliable)
                self.target_machine_name = self._get_machine_name_from_bmh_consumerref()

                # Fallback to node number matching if BMH consumerRef not available yet
                if not self.target_machine_name:
                    self.target_machine_name = self._find_target_machine_name(machines_data["items"])

            if self.target_machine_name:
                # Find the specific machine in the data we already have
                for machine in machines_data["items"]:
                    if machine["metadata"]["name"] == self.target_machine_name:
                        machine_phase = machine.get("status", {}).get("phase", "Unknown")
                        break

        return machines_data, machine_phase

    def _handle_csr_timing_logic(self, machine_phase):
        """Handle smart CSR checking logic based on timing and machine state."""
        if self.csr_checking_enabled or not self.machine_monitor_start_time:
            return

        machine_elapsed = time.time() - self.machine_monitor_start_time
        early_csr_threshold = 3 * 60  # 3 minutes

        if machine_elapsed >= self.csr_check_delay_seconds:
            # Original 10-minute logic
            self.csr_checking_enabled = True
            self.printer.print_info("⏰ 10 minutes elapsed - Now checking for CSRs while monitoring machine status...")
        elif machine_elapsed >= early_csr_threshold and machine_phase == "Provisioning":
            # Early CSR checking if machine appears stuck in provisioning
            self.csr_checking_enabled = True
            self.printer.print_info("🔧 Machine stuck in Provisioning for 3+ minutes - Starting early CSR checking...")

    def _process_machine_phase(self, machine_phase):
        """Process and respond to different machine phases."""
        csr_status = " (CSR checking active)" if self.csr_checking_enabled else ""
        self.printer.print_info(f"Machine {self.target_machine_name} phase: {machine_phase}{csr_status}")

        if machine_phase == "Running":
            self.machine_running = True
            self.printer.print_success(f"Machine {self.target_machine_name} is now Running!")
            self.printer.print_success("Machine is ready, now monitoring for node and CSRs...")
        elif machine_phase in ["Provisioning", "Provisioned"]:
            wait_msg = f"Machine {self.target_machine_name} is {machine_phase}, waiting for Running state..."
            if self.csr_checking_enabled:
                wait_msg += " (CSRs being checked and approved as needed)"
            self.printer.print_info(wait_msg)
        elif machine_phase == "Failed":
            self.printer.print_error(
                f"Machine {self.target_machine_name} is in Failed state - manual intervention required"
            )
        else:
            message = f"Machine {self.target_machine_name} phase: {machine_phase}, continuing to monitor..."
            self.printer.print_info(f"{message}{csr_status}")

    def _handle_machine_not_found(self, machines_data):
        """Handle cases where machine is not found or not yet created."""
        has_machines = machines_data and machines_data.get("items")

        if has_machines and self.target_machine_name:
            self.printer.print_info(f"Machine {self.target_machine_name} not found, continuing to monitor...")
        elif has_machines:
            node_number_match = re.search(r"(\d+)", self.replacement_node)
            node_num = node_number_match.group(1) if node_number_match else "unknown"
            self.printer.print_info(f"Looking for machine with node number {node_num}...")
        else:
            self.printer.print_info("No machines found yet, waiting for machine to appear...")

    def _monitor_machine_status(self):
        """Phase 3: Monitor machine until Running state"""
        # Get machine information
        machines_data, machine_phase = self._get_machine_info()

        # Handle CSR checking timing logic
        self._handle_csr_timing_logic(machine_phase)

        # Check for pending CSRs if enabled
        if self.csr_checking_enabled:
            self._approve_pending_csrs()

        # Process machine status and show progress
        if machines_data and machines_data.get("items") and self.target_machine_name and machine_phase:
            self._process_machine_phase(machine_phase)
        else:
            self._handle_machine_not_found(machines_data)

    def _monitor_node_and_csrs(self):
        """Phase 4: Monitor CSRs and node readiness"""
        # Check for pending CSRs and approve them
        self._approve_pending_csrs()

        # Check if the replacement node is Ready
        self._check_node_readiness()

    def _approve_pending_csrs(self):
        """Discover and approve pending CSRs using JSON processing for consistency"""
        csr_data = self.execute_oc_command(["get", "csr", "-o", "json"], json_output=True)

        if csr_data and csr_data.get("items"):
            pending_csrs = []
            for csr in csr_data["items"]:
                # Check if CSR has conditions and find pending ones
                conditions = csr.get("status", {}).get("conditions", [])
                # If no conditions exist, the CSR is pending
                if not conditions:
                    csr_name = csr["metadata"]["name"]
                    pending_csrs.append(csr_name)

            if pending_csrs:
                self.printer.print_info(f"Found {len(pending_csrs)} pending CSR(s), approving...")
                for csr_name in pending_csrs:
                    result = self.execute_oc_command(["adm", "certificate", "approve", csr_name])
                    if result:
                        self.printer.print_success(f"Approved CSR: {csr_name}")
                    else:
                        self.printer.print_warning(f"Failed to approve CSR: {csr_name}")

                # Brief pause after approving CSRs
                time.sleep(3)

    def _check_node_readiness(self):
        """Check if replacement node is Ready using JSON processing"""
        node_data = self.execute_oc_command(["get", "node", self.replacement_node, "-o", "json"], json_output=True)
        if node_data:
            # Extract node status from JSON structure
            conditions = node_data.get("status", {}).get("conditions", [])
            node_status = "Unknown"

            # Find the Ready condition
            for condition in conditions:
                if condition.get("type") == "Ready":
                    node_status = "Ready" if condition.get("status") == "True" else "NotReady"
                    break

            self.printer.print_info(f"Node {self.replacement_node} status: {node_status}")

            if node_status == "Ready":
                self.node_ready = True
                self.printer.print_success(f"Node {self.replacement_node} is now Ready!")
            elif node_status == "NotReady":
                self.printer.print_info(f"Node {self.replacement_node} is still NotReady, continuing to monitor...")
        else:
            self.printer.print_info(f"Node {self.replacement_node} not found yet, waiting for it to appear...")

    def _find_target_machine_name(self, machines_data):
        """Find machine name based on BMH association or replacement node number from JSON machine data"""
        # First try to find machine by BMH annotation (most reliable)
        for machine in machines_data:
            annotations = machine.get("metadata", {}).get("annotations", {})
            bmh_annotation = annotations.get("metal3.io/BareMetalHost")
            if bmh_annotation and self.replacement_node in bmh_annotation:
                machine_name = machine.get("metadata", {}).get("name", "")
                if machine_name:
                    self.printer.print_success(f"Found machine by BMH annotation: {machine_name}")
                    return machine_name

        # Fallback to node number matching (less reliable due to gap-filling logic)
        node_number_match = re.search(r"(\d+)", self.replacement_node)
        if node_number_match:
            node_number = node_number_match.group(1)
            self.printer.print_info(f"Looking for machine with node number {node_number}...")
            for machine in machines_data:
                machine_name = machine.get("metadata", {}).get("name", "")
                if machine_name and node_number in machine_name:
                    self.printer.print_success(f"Found machine by node number: {machine_name}")
                    return machine_name

            self.printer.print_warning(
                f"No machine found with node number {node_number} - this may be due to gap-filling logic"
            )

        return None

    def _get_machine_name_from_bmh_consumerref(self):
        """Get machine name from BMH consumerRef field"""
        try:
            bmh_output = self.execute_oc_command(
                ["get", "bmh", self.replacement_node, "-n", "openshift-machine-api", "-o", "json"],
                json_output=True,
                printer=self.printer,
            )
            if bmh_output and "spec" in bmh_output and "consumerRef" in bmh_output["spec"]:
                consumer_ref = bmh_output["spec"]["consumerRef"]
                if consumer_ref.get("kind") == "Machine" and "name" in consumer_ref:
                    machine_name = consumer_ref["name"]
                    self.printer.print_success(f"Found machine name from BMH consumerRef: {machine_name}")
                    return machine_name
            return None
        except Exception as e:
            self.printer.print_error(f"Error getting machine name from BMH consumerRef: {e}")
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
                activation_reason = (
                    "3min threshold" if machine_elapsed < self.csr_check_delay_seconds else "10min timer"
                )
                csr_status = f", CSR checking: ACTIVE ({activation_reason})"
            elif machine_elapsed < self.csr_check_delay_seconds:
                early_threshold = 3 * 60
                if machine_elapsed >= early_threshold:
                    csr_status = ", CSR checking: May activate if machine stuck in Provisioning"
                else:
                    remaining_to_early = early_threshold - machine_elapsed
                    remaining_to_full = self.csr_check_delay_seconds - machine_elapsed
                    csr_status = f", CSR early check: {remaining_to_early}s, full check: {remaining_to_full}s"

        self.printer.print_info(f"Elapsed: {elapsed_time}s, Remaining: {remaining_time}s{csr_status}")

    def _get_final_status(self):
        """
        Get final monitoring status and error messages.

        Returns:
            tuple: (success: bool, phase_reached: str, error_message: str)
        """
        timeout_minutes = self.timeout_seconds // 60

        if self.node_ready:
            self.printer.print_success("Complete 4-phase provisioning sequence completed successfully!")
            self.printer.print_success("✓ Phase 1: BMH became Provisioned")
            self.printer.print_success("✓ Phase 2: Machine created successfully")
            self.printer.print_success("✓ Phase 3: Machine reached Running state")
            self.printer.print_success("✓ Phase 4: CSRs approved and node is Ready")
            return True, "Phase 4: Node Ready", ""

        # Determine which phase failed and provide specific guidance
        self.printer.print_warning(f"TIMEOUT: Provisioning sequence did not complete within {timeout_minutes} minutes")

        if not self.bmh_provisioned:
            self.printer.print_warning("FAILED at Phase 1: BMH did not become Provisioned")
            self.printer.print_warning("Manual intervention required:")
            self.printer.print_info(f"1. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            self.printer.print_info(
                f"2. Check BMH details: oc describe bmh {self.replacement_node} -n openshift-machine-api"
            )
            self.printer.print_info("3. Check for hardware/networking issues")
            self.printer.print_info("4. Verify BMC credentials and connectivity")
            return False, "Phase 1: BMH Provisioned", "BMH did not become Provisioned"
        elif not self.machine_created:
            self.printer.print_warning("FAILED at Phase 2: Machine creation failed")
            self.printer.print_warning("Manual intervention required:")
            self.printer.print_info(f"1. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            self.printer.print_info("2. Manually create machine: oc apply -f <machine-yaml>")
            return False, "Phase 2: Machine Created", "Machine creation failed"
        elif not self.machine_running:
            self.printer.print_warning("FAILED at Phase 3: Machine did not reach Running state")
            self.printer.print_warning("Manual intervention required:")
            self.printer.print_info("1. Check machine status: oc get machines -n openshift-machine-api")
            self.printer.print_info(
                "2. Check machine details: oc describe machine <machine-name> -n openshift-machine-api"
            )
            self.printer.print_info("3. Check for provisioning errors in machine status")
            return False, "Phase 3: Machine Running", "Machine did not reach Running state"
        else:
            self.printer.print_warning("FAILED at Phase 4: Node did not become Ready")
            self.printer.print_warning("Manual intervention may be required:")
            self.printer.print_info(f"1. Check node status: oc get nodes {self.replacement_node}")
            self.printer.print_info("2. Check for pending CSRs: oc get csr --watch")
            self.printer.print_info("3. Manually approve CSRs if needed: oc adm certificate approve <csr-name>")
            self.printer.print_info("4. Check machine status: oc get machine -n openshift-machine-api")
            self.printer.print_info(f"5. Check BMH status: oc get bmh {self.replacement_node} -n openshift-machine-api")
            return False, "Phase 4: Node Ready", "Node did not become Ready"
