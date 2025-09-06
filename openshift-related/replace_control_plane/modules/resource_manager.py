#!/usr/bin/env python3
"""Resource Manager module for backup, removal, and application operations."""

import time
from typing import Any, Callable, Dict, Optional, Tuple


class ResourceManager:
    """Manages resource operations for OpenShift node replacement, addition, and expansion.

    This class encapsulates all resource management operations including BMH discovery,
    backup operations, resource cleanup, MachineSet scaling, and provisioning monitoring.
    Provides intelligent caching and consistent error handling across all operations.
    """

    def __init__(
        self,
        printer: Optional[Any] = None,
        execute_oc_command: Optional[Callable] = None,
        find_bmh_by_pattern: Optional[Callable] = None,
        format_runtime: Optional[Callable] = None,
    ) -> None:
        """Initialize ResourceManager with required dependencies.

        Args:
            printer: PrintManager instance for formatted output
            execute_oc_command: Function to execute OpenShift CLI commands
            find_bmh_by_pattern: Function to find BMH by node pattern
            format_runtime: Function to format runtime duration
        """
        self.printer = printer
        self.execute_oc_command = execute_oc_command
        self.find_bmh_by_pattern = find_bmh_by_pattern
        self.format_runtime = format_runtime

        # Caching for performance optimization
        self._bmh_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_ttl = 300  # 5 minutes cache TTL

    def _get_bmh_data(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get BMH data with intelligent caching to avoid duplicate API calls.

        Args:
            force_refresh: Force refresh of cached data

        Returns:
            Complete BMH data collection from cluster, or None if failed
        """
        current_time = time.time()

        # Check if cache is valid
        if (
            not force_refresh
            and self._bmh_cache is not None
            and self._cache_timestamp is not None
            and (current_time - self._cache_timestamp) < self._cache_ttl
        ):
            return self._bmh_cache

        # Fetch fresh data
        if self.printer:
            self.printer.print_action("Retrieving BMH data from cluster...")

        if not self.execute_oc_command:
            return None

        bmh_data = self.execute_oc_command(
            ["get", "bmh", "-n", "openshift-machine-api", "-o", "json"], json_output=True, printer=self.printer
        )

        # Update cache
        if bmh_data:
            self._bmh_cache = bmh_data
            self._cache_timestamp = current_time
            if self.printer:
                item_count = len(bmh_data.get("items", []))
                self.printer.print_success(f"Retrieved {item_count} BMH(s) from cluster")

        return bmh_data

    def _handle_operation_failure(
        self,
        error_msg: str,
        start_time: float,
        current_step: int,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], int]:
        """Handle operation failure with consistent error reporting and runtime calculation.

        Args:
            error_msg: Error message to display
            start_time: Operation start time for runtime calculation
            current_step: Current step number to return

        Returns:
            Tuple of (None, None, current_step) for consistent error handling
        """
        if self.printer:
            self.printer.print_error(error_msg)
            if self.format_runtime:
                end_time = time.time()
                total_runtime = self.format_runtime(start_time, end_time)
                self.printer.print_info(f"Runtime before exit: {total_runtime}")
        return None, None, current_step

    def _handle_simple_failure(
        self,
        error_msg: str,
        start_time: float,
        current_step: int,
    ) -> Tuple[Optional[str], int]:
        """Handle operation failure for methods returning (Optional[str], int).

        Args:
            error_msg: Error message to display
            start_time: Operation start time for runtime calculation
            current_step: Current step number to return

        Returns:
            Tuple of (None, current_step) for consistent error handling
        """
        if self.printer:
            self.printer.print_error(error_msg)
            if self.format_runtime:
                end_time = time.time()
                total_runtime = self.format_runtime(start_time, end_time)
                self.printer.print_info(f"Runtime before exit: {total_runtime}")
        return None, current_step

    def _find_bmh_data_by_name(self, bmh_name: str, all_bmh_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract specific BMH data from the collection by name.

        Args:
            bmh_name: Name of the BMH to find
            all_bmh_data: Complete BMH data collection from cluster

        Returns:
            Dictionary containing the specific BMH data, or None if not found
        """
        if not all_bmh_data or not all_bmh_data.get("items"):
            return None

        return next((bmh for bmh in all_bmh_data["items"] if bmh["metadata"]["name"] == bmh_name), None)

    def _find_and_validate_bmh(
        self,
        bad_node: str,
        current_step: int,
        total_steps: int,
        start_time: float,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], int]:
        """Find and validate BMH for the failed node.

        Args:
            bad_node: Name or pattern of the failed node
            current_step: Current step number
            total_steps: Total steps in process
            start_time: Operation start time

        Returns:
            Tuple containing:
            - BMH name (str) or None if failed
            - Complete BMH data collection (dict) or None if failed
            - Updated current_step number
        """
        if self.printer:
            self.printer.print_step(current_step, total_steps, "Finding BMH and machine information")
            self.printer.print_action(f"Retrieving BMH information to find pattern matching: {bad_node}")

        # Use cached BMH data to avoid duplicate API calls
        all_bmh_data = self._get_bmh_data()

        if not all_bmh_data:
            return self._handle_operation_failure("Failed to retrieve BMH data from cluster", start_time, current_step)

        # Find BMH that matches the bad_node pattern
        if not self.find_bmh_by_pattern:
            return None, None, current_step

        bmh_name = self.find_bmh_by_pattern(bad_node, all_bmh_data, printer=self.printer)
        if not bmh_name:
            return self._handle_operation_failure(
                f"Could not find BMH matching pattern: {bad_node}", start_time, current_step
            )

        if self.printer:
            self.printer.print_success(f"Found BMH: {bmh_name}")
        return bmh_name, all_bmh_data, current_step + 1

    def _backup_bmh_and_machine_resources(
        self,
        bmh_name: str,
        all_bmh_data: Dict[str, Any],
        backup_manager: Any,
        current_step: int,
        total_steps: int,
        start_time: float,
    ) -> Tuple[Optional[str], int]:
        """Backup BMH and Machine resources using already-fetched data.

        Args:
            bmh_name: Name of the BMH to backup
            all_bmh_data: Complete BMH data collection (to avoid re-fetching)
            backup_manager: BackupManager instance
            current_step: Current step number
            total_steps: Total steps in process
            start_time: Operation start time

        Returns:
            Tuple containing:
            - Machine name (str) or None if failed
            - Updated current_step number
        """
        if self.printer:
            self.printer.print_step(current_step, total_steps, "Backing up BMH and machine definitions")

        # Extract specific BMH data from already-fetched collection (no duplicate API call)
        specific_bmh_data = self._find_bmh_data_by_name(bmh_name, all_bmh_data)
        if not specific_bmh_data:
            return self._handle_simple_failure(f"BMH {bmh_name} not found in fetched data", start_time, current_step)

        # Extract machine name from consumerRef (runtime field used only for identification)
        try:
            machine_name = specific_bmh_data["spec"]["consumerRef"]["name"]
            if self.printer:
                self.printer.print_info(f"Identified machine from BMH consumerRef: {machine_name}")
        except KeyError:
            return self._handle_simple_failure(
                f"BMH {bmh_name} does not have a consumer machine reference", start_time, current_step
            )

        # Backup BMH using extracted fields only (excludes runtime fields like consumerRef)
        if self.printer:
            self.printer.print_action(f"Backing up BMH definition: {bmh_name}")
        if backup_manager:
            bmh_backup_file = backup_manager.backup_bmh_definition(bmh_name, specific_bmh_data)
            if self.printer:
                self.printer.print_success(f"BMH backup saved: {bmh_backup_file}")

        # Backup machine (fetch machine-specific data)
        if self.printer:
            self.printer.print_action(f"Backing up machine definition: {machine_name}")
        if not self.execute_oc_command:
            return None, current_step
        machine_data = self.execute_oc_command(
            ["get", "machine", machine_name, "-n", "openshift-machine-api", "-o", "json"],
            json_output=True,
            printer=self.printer,
        )
        if not machine_data:
            return self._handle_simple_failure(
                f"Failed to retrieve machine data for: {machine_name}", start_time, current_step
            )

        if backup_manager:
            machine_backup_file = backup_manager.backup_machine_definition(machine_name, machine_data)
            if self.printer:
                self.printer.print_success(f"Machine backup saved: {machine_backup_file}")

        return machine_name, current_step + 1

    def _remove_failed_node_resources(
        self,
        bmh_name: str,
        machine_name: str,
        current_step: int,
        total_steps: int,
    ) -> int:
        """Remove machine and BMH resources from the cluster.

        Args:
            bmh_name: Name of the BMH to remove
            machine_name: Name of the machine to remove
            current_step: Current step number
            total_steps: Total steps in process

        Returns:
            Updated current_step number
        """
        if self.printer:
            self.printer.print_step(current_step, total_steps, "Removing failed node resources")

        # Remove machine first (recommended order)
        if self.printer:
            self.printer.print_action(f"Removing machine: {machine_name}")
        if self.execute_oc_command:
            self.execute_oc_command(
                ["delete", "machine", machine_name, "-n", "openshift-machine-api"], printer=self.printer
            )
        if self.printer:
            self.printer.print_success(f"Machine {machine_name} removed")

        # Remove BMH
        if self.printer:
            self.printer.print_action(f"Removing BMH: {bmh_name}")
        if self.execute_oc_command:
            self.execute_oc_command(["delete", "bmh", bmh_name, "-n", "openshift-machine-api"], printer=self.printer)
        if self.printer:
            self.printer.print_success(f"BMH {bmh_name} removed")

        if self.printer:
            self.printer.print_success("Resource cleanup completed")
        time.sleep(1)

        return current_step + 1

    def backup_and_remove_resources(
        self,
        bad_node: str,
        backup_manager: Any,
        start_time: float,
        current_step: int,
        total_steps: int,
    ) -> Tuple[Optional[str], Optional[str], int]:
        """Handle resource backup and removal for control plane replacement.

        This method orchestrates the complete workflow of finding, backing up,
        and removing BareMetal Host (BMH) and Machine resources associated with
        a failed node to prepare for replacement node provisioning.

        Args:
            bad_node: Name or pattern of the failed node to be replaced
            backup_manager: BackupManager instance for handling resource backups
            start_time: Timestamp when the operation started (for runtime calculation)
            current_step: Current step number in the overall process
            total_steps: Total number of steps in the process

        Returns:
            Tuple containing:
            - BMH name (str) or None if failed
            - Machine name (str) or None if failed
            - Updated current_step number (int)

        Raises:
            Any exceptions from execute_oc_command or backup operations will propagate
        """
        # Step 1: Find and validate BMH
        bmh_name, all_bmh_data, current_step = self._find_and_validate_bmh(
            bad_node, current_step, total_steps, start_time
        )
        if not bmh_name:  # Error occurred in validation
            return None, None, current_step

        # Step 2: Backup BMH and Machine resources
        if not all_bmh_data:
            return None, None, current_step
        machine_name, current_step = self._backup_bmh_and_machine_resources(
            bmh_name, all_bmh_data, backup_manager, current_step, total_steps, start_time
        )
        if not machine_name:  # Error occurred in backup
            return None, None, current_step

        # Step 3: Remove failed node resources
        current_step = self._remove_failed_node_resources(bmh_name, machine_name, current_step, total_steps)

        return bmh_name, machine_name, current_step

    def find_machineset_for_machine(self, machine_name: str) -> Optional[str]:
        """Find the MachineSet that owns a specific machine.

        Args:
            machine_name: Name of the machine to find the parent MachineSet for

        Returns:
            MachineSet name if found, None otherwise
        """
        try:
            # Get the machine data to find its owner reference
            machine_data = self.execute_oc_command(
                ["get", "machine", machine_name, "-n", "openshift-machine-api", "-o", "json"],
                json_output=True,
                printer=self.printer,
            )

            if not machine_data:
                if self.printer:
                    self.printer.print_error(f"Failed to retrieve machine data for: {machine_name}")
                return None

            # Look for MachineSet owner reference
            owner_refs = machine_data.get("metadata", {}).get("ownerReferences", [])
            for owner in owner_refs:
                if owner.get("kind") == "MachineSet":
                    machineset_name = owner.get("name")
                    if self.printer:
                        self.printer.print_info(f"Found MachineSet '{machineset_name}' for machine '{machine_name}'")
                    return machineset_name

            if self.printer:
                self.printer.print_warning(f"No MachineSet owner found for machine: {machine_name}")
            return None

        except Exception as e:
            if self.printer:
                self.printer.print_error(f"Error finding MachineSet for machine {machine_name}: {e}")
            return None

    def get_machineset_by_name(
        self, machinesets_data: Dict[str, Any], machineset_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific MachineSet by name from the provided data.

        Args:
            machinesets_data: Pre-fetched MachineSet data from cluster
            machineset_name: Name of the MachineSet to find

        Returns:
            MachineSet dict if found, None otherwise
        """
        for ms in machinesets_data.get("items", []):
            if ms["metadata"]["name"] == machineset_name:
                return ms
        return None

    def _get_machineset_data(self, machineset_name: str) -> Optional[Dict]:
        """Get MachineSet data from the cluster.

        Args:
            machineset_name: Name of the MachineSet

        Returns:
            MachineSet data dict or None if failed
        """
        if not self.execute_oc_command:
            return None

        machineset_data = self.execute_oc_command(
            ["get", "machineset", machineset_name, "-n", "openshift-machine-api", "-o", "json"],
            json_output=True,
            printer=self.printer,
        )

        if not machineset_data and self.printer:
            self.printer.print_error(f"Failed to retrieve MachineSet data for: {machineset_name}")

        return machineset_data

    def _calculate_new_replicas(self, current_replicas: int, scale_direction: str) -> tuple[int, str, bool]:
        """Calculate new replica count and action description.

        Args:
            current_replicas: Current number of replicas
            scale_direction: "up" or "down"

        Returns:
            Tuple of (new_replicas, action_description, should_continue)
        """
        if scale_direction == "up":
            return current_replicas + 1, "Scaling up", True
        elif scale_direction == "down":
            if current_replicas == 0:
                if self.printer:
                    self.printer.print_warning("MachineSet is already at 0 replicas")
                return 0, "Already at minimum", False
            return max(0, current_replicas - 1), "Scaling down", True
        else:
            if self.printer:
                self.printer.print_error(f"Invalid scale direction: {scale_direction}. Use 'up' or 'down'")
            return 0, "Invalid direction", False

    def _execute_scaling(self, machineset_name: str, new_replicas: int) -> bool:
        """Execute the actual scaling operation.

        Args:
            machineset_name: Name of the MachineSet to scale
            new_replicas: Target number of replicas

        Returns:
            True if successful, False otherwise
        """
        try:
            self.execute_oc_command(
                ["scale", "machineset", machineset_name, "-n", "openshift-machine-api", f"--replicas={new_replicas}"],
                printer=self.printer,
            )

            if self.printer:
                self.printer.print_success(
                    f"Successfully scaled MachineSet '{machineset_name}' to {new_replicas} replicas"
                )
            return True
        except Exception as e:
            if self.printer:
                self.printer.print_error(f"Failed to execute scaling: {e}")
            return False

    def scale_machineset_for_machine(self, machine_name: str, scale_direction: str = "up") -> bool:
        """Scale the MachineSet that owns a specific machine.

        Simple and direct: find the machine's parent MachineSet and scale it.

        Args:
            machine_name: Name of the machine whose MachineSet should be scaled
            scale_direction: "up" to scale up, "down" to scale down (default: "up")

        Returns:
            True if scaling was successful, False otherwise
        """
        try:
            # Find which MachineSet owns this machine
            machineset_name = self.find_machineset_for_machine(machine_name)
            if not machineset_name:
                if self.printer:
                    self.printer.print_error(f"Could not find MachineSet for machine: {machine_name}")
                return False

            # Get the MachineSet data
            machineset_data = self._get_machineset_data(machineset_name)
            if not machineset_data:
                return False

            current_replicas = machineset_data["spec"].get("replicas", 0)
            new_replicas, action, should_continue = self._calculate_new_replicas(current_replicas, scale_direction)

            if not should_continue:
                return (
                    scale_direction == "down" and current_replicas == 0
                )  # Success if already at minimum for scale down

            if self.printer:
                self.printer.print_action(
                    f"{action} MachineSet '{machineset_name}' from {current_replicas} to {new_replicas} replicas"
                )

            return self._execute_scaling(machineset_name, new_replicas)

        except Exception as e:
            if self.printer:
                self.printer.print_error(f"Failed to scale MachineSet for machine {machine_name}: {e}")
            return False

    def scale_machineset_directly(self, machineset_name: str, scale_direction: str = "up") -> bool:
        """Scale a MachineSet directly by name.

        Args:
            machineset_name: Name of the MachineSet to scale
            scale_direction: "up" to scale up, "down" to scale down (default: "up")

        Returns:
            True if scaling was successful, False otherwise
        """
        try:
            # Get the MachineSet data
            machineset_data = self._get_machineset_data(machineset_name)
            if not machineset_data:
                return False

            current_replicas = machineset_data["spec"].get("replicas", 0)
            new_replicas, action, should_continue = self._calculate_new_replicas(current_replicas, scale_direction)

            if not should_continue:
                return (
                    scale_direction == "down" and current_replicas == 0
                )  # Success if already at minimum for scale down

            if self.printer:
                self.printer.print_action(
                    f"{action} MachineSet '{machineset_name}' from {current_replicas} to {new_replicas} replicas"
                )

            return self._execute_scaling(machineset_name, new_replicas)

        except Exception as e:
            if self.printer:
                self.printer.print_error(f"Failed to scale MachineSet {machineset_name}: {e}")
            return False

    def _apply_resource_files(self, copied_files: Dict[str, str], is_addition: bool) -> bool:
        """Apply resource files to the cluster.

        Args:
            copied_files: Dictionary mapping resource types to their file paths
            is_addition: True for worker addition, False for control plane replacement

        Returns:
            True if all resources applied successfully, False otherwise
        """
        try:
            for resource_type, file_path in copied_files.items():
                if resource_type == "nmstate":
                    continue  # nmstate is handled by network-config-secret

                # Skip machine application for worker additions - MachineSet handles machine creation
                if resource_type == "machine" and is_addition:
                    if self.printer:
                        self.printer.print_info(
                            "Skipping machine application - MachineSet will create the machine automatically"
                        )
                    continue

                if self.printer:
                    self.printer.print_action(f"Applying {resource_type}: {file_path}")
                if self.execute_oc_command:
                    self.execute_oc_command(["apply", "-f", file_path], printer=self.printer)
                if self.printer:
                    self.printer.print_success(f"Applied {resource_type}")

            if self.printer:
                self.printer.print_success("All resources applied successfully")
            return True
        except Exception as e:
            if self.printer:
                self.printer.print_error(f"Failed to apply resources: {e}")
            return False

    def _find_worker_machineset(self) -> Optional[str]:
        """Find a worker MachineSet in the cluster.

        Returns:
            Name of worker MachineSet or None if not found
        """
        machinesets_data = self.execute_oc_command(
            ["get", "machineset", "-n", "openshift-machine-api", "-o", "json"],
            json_output=True,
            printer=self.printer,
        )

        if not machinesets_data:
            return None

        # Find a worker MachineSet by looking for the worker role label
        for machineset in machinesets_data.get("items", []):
            labels = machineset.get("metadata", {}).get("labels", {})
            if labels.get("machine.openshift.io/cluster-api-machine-role") == "worker":
                worker_machineset = machineset["metadata"]["name"]
                if self.printer:
                    self.printer.print_info(f"Found worker MachineSet: {worker_machineset}")
                return worker_machineset
        return None

    def _handle_worker_scaling(self) -> bool:
        """Handle scaling of worker MachineSet for worker addition.

        Returns:
            True if scaling was successful or not needed, False on failure
        """
        if self.printer:
            self.printer.print_action("Scaling worker MachineSet to accommodate new worker")

        worker_machineset = self._find_worker_machineset()

        if worker_machineset:
            if not self.scale_machineset_directly(worker_machineset, scale_direction="up"):
                if self.printer:
                    self.printer.print_error("Failed to scale MachineSet - continuing with monitoring anyway")
                return False
            else:
                if self.printer:
                    self.printer.print_success("MachineSet scaled successfully")
                return True
        else:
            if self.printer:
                self.printer.print_error("No worker MachineSet found - continuing with monitoring anyway")
            return False

    def _create_and_monitor_resources(
        self,
        replacement_node: str,
        backup_dir: str,
        is_addition: bool,
        is_expansion: bool,
        ResourceMonitor: Any,
        start_time: float,
        handle_provisioning_failure: Callable,
    ) -> tuple[bool, Optional[str]]:
        """Create resource monitor and monitor provisioning.

        Args:
            replacement_node: Name of the replacement/new node
            backup_dir: Directory path where backups and configs are stored
            is_addition: True for worker addition, False for control plane replacement
            is_expansion: True if this is an expansion operation
            ResourceMonitor: Class for monitoring resource provisioning
            start_time: Timestamp when the operation started
            handle_provisioning_failure: Function to handle provisioning failures

        Returns:
            Tuple of (success, error_message)
        """
        # Create resource monitor and start monitoring
        monitor = ResourceMonitor(
            replacement_node,
            backup_dir,
            is_addition=is_addition,
            is_expansion=is_expansion,
            printer=self.printer,
            execute_oc_command=self.execute_oc_command,
        )

        try:
            success, phase_reached, error_message = monitor.monitor_provisioning_sequence()
            if success:
                if self.printer:
                    self.printer.print_success(f"Node {replacement_node} successfully provisioned and ready!")
                return True, None
            else:
                handle_provisioning_failure(
                    phase_reached,
                    error_message,
                    start_time,
                    is_addition,
                    printer=self.printer,
                    format_runtime=self.format_runtime,
                )
                return False, error_message

        except KeyboardInterrupt:
            if self.printer:
                self.printer.print_warning("\nMonitoring interrupted by user")
                self.printer.print_info("Node provisioning may still be in progress...")
                self.printer.print_info(
                    f"Check status manually with: oc get bmh {replacement_node} -n openshift-machine-api"
                )
            return False, "Monitoring interrupted by user"

    def apply_resources_and_monitor(
        self,
        copied_files: Dict[str, str],
        backup_dir: str,
        replacement_node: str,
        start_time: float,
        current_step: int,
        total_steps: int,
        is_addition: bool,
        is_expansion: bool = False,
        ResourceMonitor: Optional[Any] = None,
        handle_provisioning_failure: Optional[Callable] = None,
    ) -> Tuple[Optional[Dict[str, str]], int]:
        """Apply resources and monitor node provisioning.

        Applies Kubernetes resources for a replacement or additional node and monitors
        the provisioning process. For worker additions, automatically scales the worker
        MachineSet. Handles both control plane replacement and worker addition scenarios.

        Args:
            copied_files: Dictionary mapping resource types to their file paths
            backup_dir: Directory path where backups and configs are stored
            replacement_node: Name of the replacement/new node
            start_time: Timestamp when the operation started
            current_step: Current step number in the overall process
            total_steps: Total number of steps in the process
            is_addition: True for worker addition, False for control plane replacement
            ResourceMonitor: Class for monitoring resource provisioning (optional)
            handle_provisioning_failure: Function to handle provisioning failures (optional)

        Returns:
            Tuple containing:
            - copied_files dict if successful, None if failed
            - Updated current_step number

        Raises:
            KeyboardInterrupt: Handled gracefully with appropriate messaging
            Any other exceptions from resource operations will propagate
        """
        # Apply all resources
        step_desc = "Applying new worker configuration" if is_addition else "Applying replacement node configuration"
        if self.printer:
            self.printer.print_step(current_step, total_steps, step_desc)

        if not self._apply_resource_files(copied_files, is_addition):
            return None, current_step

        # For worker addition: scale up the MachineSet
        if is_addition:
            self._handle_worker_scaling()

        current_step += 1

        # Monitor provisioning
        step_desc = "Monitoring new worker provisioning" if is_addition else "Monitoring replacement node provisioning"
        if self.printer:
            self.printer.print_step(current_step, total_steps, step_desc)

        if not ResourceMonitor or not handle_provisioning_failure:
            if self.printer:
                self.printer.print_error("Required monitoring components not available")
            return None, current_step

        success, _ = self._create_and_monitor_resources(
            replacement_node,
            backup_dir,
            is_addition,
            is_expansion,
            ResourceMonitor,
            start_time,
            handle_provisioning_failure,
        )

        if success:
            current_step += 1
            return copied_files, current_step
        else:
            return None, current_step
