#!/usr/bin/env python3
"""Orchestrator module for OpenShift node operations workflow management."""

import time
from typing import Any, Dict, Optional, Tuple


class NodeOperationOrchestrator:
    """
    Orchestrates node operations workflow for OpenShift control plane replacement,
    expansion, and worker node addition.
    """

    def __init__(self, **dependencies: Any) -> None:
        """
        Initialize the orchestrator with all required dependencies.

        Args:
            **dependencies: All required function and class dependencies including:
                - printer: PrintManager instance for output formatting
                - execute_oc_command: Function to execute OpenShift CLI commands
                - format_runtime: Function to format time durations
                - BackupManager: BackupManager class constructor
                - NodeConfigurator: NodeConfigurator class constructor
                - ResourceMonitor: ResourceMonitor class constructor
                - Various utility functions for node operations
        """
        # Core dependencies
        self.printer = dependencies["printer"]
        self.execute_oc_command = dependencies["execute_oc_command"]
        self.format_runtime = dependencies["format_runtime"]

        # Class constructors
        self.BackupManager = dependencies["BackupManager"]
        self.NodeConfigurator = dependencies["NodeConfigurator"]
        self.ResourceMonitor = dependencies["ResourceMonitor"]

        # Utility functions
        self.find_bmh_by_mac_address = dependencies["find_bmh_by_mac_address"]
        self.find_bmh_by_pattern = dependencies["find_bmh_by_pattern"]
        self.find_machineset_for_machine = dependencies["find_machineset_for_machine"]
        self.annotate_machine_for_deletion = dependencies["annotate_machine_for_deletion"]
        self.scale_down_machineset = dependencies["scale_down_machineset"]
        self.cordon_node = dependencies["cordon_node"]
        self.drain_node = dependencies["drain_node"]
        self.delete_machine = dependencies["delete_machine"]
        self.delete_bmh = dependencies["delete_bmh"]
        self.verify_resources_deleted = dependencies["verify_resources_deleted"]

        # Workflow functions
        self.configure_replacement_node = dependencies["configure_replacement_node"]
        self.handle_successful_completion = dependencies["handle_successful_completion"]
        self.create_new_node_configs = dependencies["create_new_node_configs"]
        self.handle_provisioning_failure = dependencies["handle_provisioning_failure"]

        # Resource manager class
        self.ResourceManager = dependencies["ResourceManager"]
        self.resource_manager = None  # Will be initialized when needed

        # ETCD functions
        self.handle_etcd_operations_for_replacement = dependencies["handle_etcd_operations_for_replacement"]
        self.handle_etcd_operations_for_expansion = dependencies["handle_etcd_operations_for_expansion"]
        self.re_enable_quorum_guard_after_expansion = dependencies["re_enable_quorum_guard_after_expansion"]
        self.exec_pod_command = dependencies["exec_pod_command"]

        # Additional workflow functions
        self.determine_failed_control_node = dependencies["determine_failed_control_node"]

    def _setup_operation_parameters(
        self, args: Any, is_addition: bool, is_expansion: bool
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Setup operation parameters and step counts.

        Args:
            args: Parsed command line arguments containing replacement node details
            is_addition: True for worker addition, False otherwise
            is_expansion: True for control plane expansion, False otherwise

        Returns:
            Tuple containing:
                - total_steps (int): Total number of steps for the operation
                - operation_params (Dict[str, Any]): Dictionary of operation parameters
        """
        # Different step counts for different operations
        if is_addition:
            total_steps = 6  # Worker addition: fewer steps, no ETCD operations
        elif is_expansion:
            total_steps = 9  # Control plane expansion: includes ETCD disable + re-enable steps
        else:
            total_steps = 12  # Full replacement workflow

        operation_params = {
            "replacement_node": args.replacement_node,
            "replacement_node_ip": args.replacement_node_ip,
            "replacement_node_bmc_ip": args.replacement_node_bmc_ip,
            "replacement_node_mac_address": args.replacement_node_mac_address,
            "replacement_node_role": args.replacement_node_role,
            "sushy_uid": args.sushy_uid,
        }

        return total_steps, operation_params

    def _handle_existing_mac_conflict(self, mac_address: str, total_steps: int) -> int:
        """
        Handle existing nodes with same MAC address by cleaning them up.

        Args:
            mac_address: MAC address to check for conflicts
            total_steps: Current total step count

        Returns:
            Updated total_steps count, potentially increased if cleanup is needed
        """
        existing_bmh_info = self.find_bmh_by_mac_address(mac_address, printer=self.printer)

        if existing_bmh_info and existing_bmh_info.get("node_name"):
            self.printer.print_warning(
                f"Found existing node '{existing_bmh_info['node_name']}' with same MAC address {mac_address}"
            )
            self.printer.print_info("This node will be cordoned, drained, and removed before provisioning the new node")

            # Add 3 extra steps for the additional cleanup
            total_steps += 3

            self.printer.print_warning(f"Total steps increased to {total_steps} due to existing node cleanup")

            # Handle MachineSet scaling if it's a worker node
            if existing_bmh_info.get("machine_name"):
                self._handle_machineset_scaling(existing_bmh_info["machine_name"])

            # Cordon the existing node
            self.printer.print_info(f"Cordoning existing node: {existing_bmh_info['node_name']}")
            self.cordon_node(existing_bmh_info["node_name"], printer=self.printer)

            # Drain the existing node
            self.printer.print_info(f"Draining existing node: {existing_bmh_info['node_name']}")
            self.drain_node(existing_bmh_info["node_name"], printer=self.printer)

            # Delete existing resources
            self._delete_existing_resources(existing_bmh_info.get("machine_name"), existing_bmh_info["bmh_name"])

        return total_steps

    def _handle_machineset_scaling(self, machine_name: str) -> None:
        """
        Handle MachineSet scaling for existing machine to prevent automatic replacement.

        Args:
            machine_name: Name of the machine whose MachineSet should be scaled down
        """
        self.printer.print_action("Finding and scaling down associated MachineSet...")
        machineset_info = self.find_machineset_for_machine(machine_name, printer=self.printer)

        if machineset_info:
            machineset_name = machineset_info["machineset_name"]
            current_replicas = machineset_info["current_replicas"]

            self.printer.print_info(
                f"Machine '{machine_name}' belongs to MachineSet '{machineset_name}' with {current_replicas} replicas"
            )

            # Annotate machine for deletion before scaling down
            if not self.annotate_machine_for_deletion(
                machine_name, printer=self.printer, execute_oc_command=self.execute_oc_command
            ):
                self.printer.print_warning(
                    f"Failed to annotate machine '{machine_name}' - proceeding with scaling anyway"
                )

            if self.scale_down_machineset(
                machineset_name, printer=self.printer, execute_oc_command=self.execute_oc_command
            ):
                self.printer.print_success(f"Successfully scaled down MachineSet '{machineset_name}' by 1 replica")
                self.printer.print_info(
                    "This prevents the MachineSet from creating a replacement worker when this node is converted to control plane"
                )
            else:
                self.printer.print_warning(
                    f"Failed to scale down MachineSet '{machineset_name}' - you may need to manually scale down the worker MachineSet"
                )
        else:
            self.printer.print_info(
                f"Machine '{machine_name}' is not managed by any MachineSet (manually created) - skipping MachineSet operations"
            )

    def _delete_existing_resources(self, machine_name: Optional[str], bmh_name: str) -> None:
        """
        Delete existing machine and BMH resources and verify they are removed.

        Args:
            machine_name: Name of the machine to delete, None if no machine exists
            bmh_name: Name of the BareMetalHost to delete
        """
        success = True

        if machine_name:
            self.printer.print_info(f"Deleting existing machine: {machine_name}")
            if not self.delete_machine(machine_name, printer=self.printer):
                success = False

        if bmh_name:
            self.printer.print_info(f"Deleting existing BMH: {bmh_name}")
            if not self.delete_bmh(bmh_name, printer=self.printer):
                success = False

        # Verify resources are deleted to prevent conflicts
        if machine_name or bmh_name:
            self.printer.print_info("Waiting for existing resources to be deleted...")
            verification_success = self.verify_resources_deleted(
                machine_name=machine_name, bmh_name=bmh_name, printer=self.printer
            )
            if not verification_success:
                success = False

        if success:
            self.printer.print_success("Successfully cleaned up all existing resources")
        else:
            self.printer.print_warning("Some deletions failed - you may need to manually delete resources")

    def _get_template_configuration(
        self, is_addition: bool, is_expansion: bool, backup_manager: Any
    ) -> Tuple[Optional[str], Optional[bool], Optional[str]]:
        """
        Get template configuration based on operation type.

        Args:
            is_addition: True for worker addition, False otherwise
            is_expansion: True for control plane expansion, False otherwise
            backup_manager: BackupManager instance for handling backups

        Returns:
            Tuple containing:
                - template_backup_file (Optional[str]): Path to backup file, None if failed
                - is_worker_template (Optional[bool]): True if template is from worker, None if failed
                - failed_node (Optional[str]): Name of failed node for replacement, None for addition/expansion
        """
        if is_addition:
            # Worker addition: find and backup worker template
            template_backup_file, is_worker_template = backup_manager.backup_template_bmh(failed_control_node=None)
            if not template_backup_file:
                self.printer.print_error("No BMH found to use as template - exiting")
                self._exit_with_runtime(time.time())
                return None, None, None
            return template_backup_file, is_worker_template, None

        elif is_expansion:
            # Control plane expansion: get template from existing control plane
            self.printer.print_info("Expansion mode: Using existing control plane as template")
            template_backup_file, is_worker_template = backup_manager.backup_template_bmh(
                failed_control_node=None, is_control_plane_expansion=True
            )
            if not template_backup_file:
                self.printer.print_error("No control plane BMH found to use as template - exiting")
                self._exit_with_runtime(time.time())
                return None, None, None
            return template_backup_file, is_worker_template, None

        else:
            # Control plane replacement: get template from failed node
            failed_node = self.determine_failed_control_node()
            if not failed_node:
                self.printer.print_error("Could not determine failed control plane node")
                self._exit_with_runtime(time.time())
                return None, None, None

            self.printer.print_info(f"Using failed control plane node as template: {failed_node}")
            template_backup_file, is_worker_template = backup_manager.backup_template_bmh(
                failed_control_node=failed_node
            )
            if not template_backup_file:
                self.printer.print_error(f"Failed to backup template from {failed_node}")
                self._exit_with_runtime(time.time())
                return None, None, None
            return template_backup_file, is_worker_template, failed_node

    def _handle_etcd_operations_step(
        self,
        is_addition: bool,
        is_expansion: bool,
        args: Any,
        failed_node: Optional[str],
        start_time: float,
        current_step: int,
        total_steps: int,
    ) -> Tuple[Optional[str], int]:
        """
        Handle ETCD operations step based on operation type.

        Args:
            is_addition: True for worker addition (skips ETCD operations)
            is_expansion: True for control plane expansion (disables quorum guard only)
            args: Parsed command line arguments
            failed_node: Name of failed node for replacement operations
            start_time: Start time of the operation
            current_step: Current step number
            total_steps: Total number of steps

        Returns:
            Tuple containing:
                - bad_node (Optional[str]): Name of problematic ETCD node, None if operations failed
                - current_step (int): Updated current step number
        """
        if is_addition:
            # Worker addition: Skip ETCD operations
            self.printer.print_step(current_step, total_steps, "Skipping ETCD operations (worker addition)")
            self.printer.print_info("ETCD operations are not required for worker node addition")
            return None, current_step + 1
        elif is_expansion:
            # Control plane expansion: Only disable quorum guard
            bad_node, current_step = self.handle_etcd_operations_for_expansion(
                start_time,
                current_step,
                total_steps,
                printer=self.printer,
                execute_oc_command=self.execute_oc_command,
                format_runtime=self.format_runtime,
            )
            return bad_node, current_step
        else:
            # Control plane replacement: Full ETCD operations
            bad_node, current_step = self.handle_etcd_operations_for_replacement(
                failed_node,
                start_time,
                current_step,
                total_steps,
                printer=self.printer,
                exec_pod_command=self.exec_pod_command,
                execute_oc_command=self.execute_oc_command,
                format_runtime=self.format_runtime,
            )
            return bad_node, current_step

    def _create_configuration_files(
        self,
        is_addition: bool,
        is_expansion: bool,
        backup_manager: Any,
        backup_dir: str,
        template_backup_file: str,
        is_worker_template: bool,
        operation_params: Dict[str, Any],
        failed_node: Optional[str] = None,
        backup_bmh_name: Optional[str] = None,
        backup_machine_name: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """
        Create configuration files from template or copy existing files.

        Args:
            is_addition: True for worker addition
            is_expansion: True for control plane expansion
            backup_manager: BackupManager instance
            backup_dir: Directory path for backups
            template_backup_file: Path to template backup file
            is_worker_template: True if template is from a worker node
            operation_params: Dictionary containing operation parameters
            failed_node: Name of the failed node for control plane replacement

        Returns:
            Dictionary of created configuration files, None if creation failed
        """
        self.printer.print_action("Retrieving machines information for template selection...")
        machines_data = self.execute_oc_command(
            ["get", "machines", "-n", "openshift-machine-api", "-o", "json"], json_output=True, printer=self.printer
        )

        # For all operations (addition, expansion, AND replacement), create files from template
        # Extract configuration from working nodes, not failed ones
        copied_files = self.create_new_node_configs(
            backup_manager,
            backup_dir,
            template_backup_file,
            operation_params["replacement_node"],
            is_addition,
            is_worker_template,
            machines_data,
            printer=self.printer,
            execute_oc_command=self.execute_oc_command,
            is_expansion=is_expansion,
        )

        return copied_files

    def _exit_with_runtime(self, start_time: float) -> None:
        """
        Exit with runtime information after a failure.

        Args:
            start_time: Start time of the operation for runtime calculation
        """
        total_runtime = self.format_runtime(start_time, time.time())
        self.printer.print_error(f"Exiting... Total runtime: {total_runtime}")

    def _get_step_description(self, operation_type: str, step_name: str) -> str:
        """
        Get step description based on operation type.

        Args:
            operation_type: Operation type ("replacement", "addition", or "expansion")
            step_name: The step identifier (e.g., "configure_node", "apply_resources")

        Returns:
            Formatted step description string for display
        """
        descriptions = {
            "configure_node": {
                "replacement": "Configuring replacement node",
                "addition": "Configuring new worker node",
                "expansion": "Configuring new control plane node",
            },
            "apply_resources": {
                "replacement": "Applying resources and monitoring replacement",
                "addition": "Applying resources and monitoring worker addition",
                "expansion": "Applying resources and monitoring control plane expansion",
            },
        }

        return descriptions.get(step_name, {}).get(operation_type, f"Processing {step_name}")

    def process_node_operation(self, args: Any, is_addition: bool = False, is_expansion: bool = False) -> None:
        """
        Unified function to handle control plane replacement, expansion, and worker node addition.
        This is the main orchestration method that coordinates all steps of the operation.

        Args:
            args: Parsed command line arguments containing node details and configuration
            is_addition: True for worker node addition, False for control plane operations
            is_expansion: True for control plane expansion, False for replacement

        Note:
            This method handles the complete workflow including:
            - Setup and validation
            - ETCD operations (for control plane operations)
            - Resource backup and removal
            - Configuration file creation
            - Node provisioning and monitoring
            - Completion handling
        """
        start_time = time.time()
        total_steps, operation_params = self._setup_operation_parameters(args, is_addition, is_expansion)
        current_step = 1
        operation_params["start_time"] = start_time

        # Step 1: Setup backup directory
        self.printer.print_step(current_step, total_steps, "Setting up backup directory")
        backup_manager = self.BackupManager(printer=self.printer, execute_oc_command=self.execute_oc_command)
        backup_dir = backup_manager.setup_backup_directory(args.backup_dir)
        current_step += 1

        # Step 2: Handle existing MAC conflicts (if any)
        total_steps = self._handle_existing_mac_conflict(operation_params["replacement_node_mac_address"], total_steps)

        # Step 3: Get template configuration
        step_desc = self._get_step_description(
            "addition" if is_addition else "expansion" if is_expansion else "replacement", "get_template"
        )
        self.printer.print_step(current_step, total_steps, "Getting template configuration")

        template_result = self._get_template_configuration(is_addition, is_expansion, backup_manager)
        if not template_result[0]:  # template_backup_file is None
            return
        template_backup_file, is_worker_template, failed_node = template_result

        # Ensure non-None values for required parameters
        if template_backup_file is None or is_worker_template is None:
            self.printer.print_error("Template configuration returned invalid values")
            return
        current_step += 1

        # Step 4: Handle ETCD operations (if needed)
        bad_node, current_step = self._handle_etcd_operations_step(
            is_addition, is_expansion, args, failed_node, start_time, current_step, total_steps
        )
        if bad_node is None and not is_addition and not is_expansion:
            return  # ETCD operations failed

        # Initialize backup variables
        backup_bmh_name, backup_machine_name = None, None

        # Step 5: Handle resource backup and removal (if needed)
        if not is_addition and not is_expansion:
            # Initialize resource manager if not already done
            if not self.resource_manager:
                self.resource_manager = self.ResourceManager(
                    printer=self.printer,
                    execute_oc_command=self.execute_oc_command,
                    find_bmh_by_pattern=self.find_bmh_by_pattern,
                    format_runtime=self.format_runtime,
                )

            assert self.resource_manager is not None  # Type guard for MyPy
            backup_bmh_name, backup_machine_name, current_step = self.resource_manager.backup_and_remove_resources(
                bad_node,  # Remove the unused failed_node parameter
                backup_manager,
                start_time,
                current_step,
                total_steps,
            )

            # Check if backup process failed
            if backup_bmh_name is None or backup_machine_name is None:
                self.printer.print_error("Resource backup failed - cannot proceed with replacement")
                return

        # Step 6: Create configuration files
        step_desc = self._get_step_description(
            "addition" if is_addition else "expansion" if is_expansion else "replacement", "create_config"
        )
        self.printer.print_step(
            current_step,
            total_steps,
            "Creating configuration files for new worker" if is_addition else "Creating configuration files",
        )

        copied_files = self._create_configuration_files(
            is_addition,
            is_expansion,
            backup_manager,
            backup_dir,
            template_backup_file,
            is_worker_template,
            operation_params,
            failed_node,
            backup_bmh_name,
            backup_machine_name,
        )
        if not copied_files:
            return
        current_step += 1

        # Step 7: Configure replacement node
        step_desc = self._get_step_description(
            "addition" if is_addition else "expansion" if is_expansion else "replacement", "configure_node"
        )
        self.printer.print_step(current_step, total_steps, step_desc)

        self.configure_replacement_node(
            copied_files,
            operation_params["replacement_node"],
            operation_params["replacement_node_ip"],
            operation_params["replacement_node_bmc_ip"],
            operation_params["replacement_node_mac_address"],
            operation_params["replacement_node_role"],
            operation_params["sushy_uid"],
            printer=self.printer,
            NodeConfigurator=self.NodeConfigurator,
            execute_oc_command=self.execute_oc_command,
        )
        current_step += 1

        # Step 8: Apply resources and monitor
        # Initialize resource manager if not already done
        if not self.resource_manager:
            self.resource_manager = self.ResourceManager(
                printer=self.printer,
                execute_oc_command=self.execute_oc_command,
                find_bmh_by_pattern=self.find_bmh_by_pattern,
                format_runtime=self.format_runtime,
            )

        assert self.resource_manager is not None  # Type guard for MyPy
        copied_files, current_step = self.resource_manager.apply_resources_and_monitor(
            copied_files,
            backup_dir,
            operation_params["replacement_node"],
            start_time,
            current_step,
            total_steps,
            is_addition=is_addition,
            is_expansion=is_expansion,
            ResourceMonitor=self.ResourceMonitor,
            handle_provisioning_failure=self.handle_provisioning_failure,
        )

        # Step 9: Re-enable quorum guard for control plane expansion
        if is_expansion:
            current_step = self.re_enable_quorum_guard_after_expansion(
                start_time,
                current_step,
                total_steps,
                printer=self.printer,
                execute_oc_command=self.execute_oc_command,
                format_runtime=self.format_runtime,
            )

        # Final step: Handle successful completion
        self.handle_successful_completion(
            operation_params["replacement_node"],
            start_time,
            is_addition,
            printer=self.printer,
            format_runtime=self.format_runtime,
        )


def handle_successful_completion(
    replacement_node: str, start_time: float, is_addition: bool, printer: Any = None, format_runtime: Any = None
) -> None:
    """
    Handle successful completion of node operation (kept as function for backward compatibility).

    Args:
        replacement_node: Name of the replacement/new node
        start_time: Start time of the operation
        is_addition: True if this was a worker addition, False for control plane operations
        printer: PrintManager instance for output formatting
        format_runtime: Function to format time duration
    """
    total_runtime = format_runtime(start_time, time.time())

    if is_addition:
        printer.print_header(f"Worker node '{replacement_node}' addition completed successfully!")
        printer.print_success("New worker node is ready and available for workloads")
        printer.print_info("The worker node should appear in the OpenShift console and be ready to accept pods")
    else:
        printer.print_header(f"Control plane node '{replacement_node}' operation completed successfully!")
        printer.print_success("The new control plane node is operational and part of the cluster")
        printer.print_info("The control plane should be fully functional with the new node")

    printer.print_info(f"Total runtime: {total_runtime}")
    printer.print_info("Operation completed successfully!")


def handle_provisioning_failure(error_msg: str, format_runtime: Any, start_time: float, printer: Any = None) -> None:
    """
    Handle provisioning failure (kept as function for backward compatibility).

    Args:
        error_msg: Error message describing what went wrong
        format_runtime: Function to format time duration
        start_time: Start time of the operation
        printer: PrintManager instance for output formatting
    """
    total_runtime = format_runtime(start_time, time.time())
    printer.print_error(f"Node operation failed: {error_msg}")
    printer.print_error(f"Total runtime before failure: {total_runtime}")
    printer.print_info("Check the logs above for specific error details")
    printer.print_info("You may need to manually clean up any partially created resources")
