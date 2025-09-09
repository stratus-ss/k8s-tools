# Resource Manager Test Suite Documentation

## Overview

The `test_resource_manager.py` file contains comprehensive test coverage for the `ResourceManager` class, which is responsible for managing Kubernetes resources during OpenShift node operations. This test suite validates critical resource management operations including BareMetalHost discovery, Machine resource handling, MachineSet operations, resource backup and removal, and resource application with monitoring.

## Purpose and Context

The ResourceManager serves as the central coordinator for all Kubernetes resource operations during node replacement, addition, and expansion workflows. It manages the complete lifecycle of resources including:

- **Resource Discovery**: Finding and validating BareMetalHost and Machine resources
- **Resource Backup**: Creating backup copies of critical resources before modifications
- **Resource Removal**: Safely removing failed or conflicting resources from the cluster
- **Resource Application**: Applying new resource configurations and monitoring their provisioning
- **MachineSet Coordination**: Managing MachineSet scaling for controlled worker node provisioning

These operations are critical for maintaining cluster integrity during node operations and ensuring that resource transitions occur safely without causing service disruption.

## Test Structure and Organization

### Test Fixtures and Dependencies

The test suite uses comprehensive mocking to isolate resource management logic:

- **Mock OpenShift commands**: Simulates `oc` command responses for different resource types
- **Sample resource data**: Realistic BMH, Machine, and MachineSet data from production clusters
- **Mock backup manager**: Isolates backup operations from actual file system interactions
- **Mock resource monitor**: Simulates resource provisioning monitoring without cluster dependencies

**Why comprehensive resource mocking is essential**: Resource management operations interact with live Kubernetes APIs and complex resource relationships. Mocking allows testing of resource management logic without requiring functional OpenShift clusters or physical hardware.

## Test Classes and Their Purposes

### 1. TestResourceManagerInitialization

**Purpose**: Validates basic ResourceManager class initialization and dependency injection.

**Why this is tested**: Proper initialization ensures all required dependencies are available for resource management operations.

**Key Tests**:

#### test_initialization_with_all_dependencies
- **What**: Verifies ResourceManager initialization with complete dependency set
- **Why**: Resource management requires access to OpenShift commands, utility functions, and formatting capabilities
- **How**: Creates ResourceManager with all dependencies, verifies proper attribute assignment and cache initialization
- **Production Impact**: Ensures ResourceManager can access all required subsystems for resource operations

#### test_initialization_with_minimal_dependencies
- **What**: Tests ResourceManager initialization with minimal or no dependencies
- **Why**: Some use cases may require ResourceManager with limited functionality or dependency injection
- **How**: Creates ResourceManager without dependencies, verifies graceful handling of None values
- **Production Impact**: Supports flexible ResourceManager usage patterns in different contexts

### 2. TestBMHDataCaching

**Purpose**: Validates BareMetalHost data caching functionality for performance optimization.

**Why this is tested**: BMH data caching reduces API calls to the OpenShift cluster, improving performance and reducing load during resource operations that require repeated BMH lookups.

**Key Tests**:

#### test_get_bmh_data_initial_fetch
- **What**: Tests initial BMH data retrieval and cache population
- **Why**: First data access should fetch from cluster and populate cache for subsequent operations
- **How**: Calls BMH data retrieval, verifies API call execution and cache state updates
- **Production Impact**: Ensures initial BMH data retrieval works correctly and establishes caching baseline

#### test_get_bmh_data_cache_hit
- **What**: Tests BMH data retrieval from cache when cache is valid (within TTL)
- **Why**: Cache hits should avoid redundant API calls, improving performance and reducing cluster load
- **How**: Sets up valid cached data, calls retrieval within TTL, verifies no API calls and cached data return
- **Production Impact**: Optimizes performance by avoiding redundant API calls for recent BMH data

#### test_get_bmh_data_cache_expired
- **What**: Tests BMH data refresh when cache has exceeded time-to-live (TTL)
- **Why**: Expired cache should trigger data refresh to ensure current resource state information
- **How**: Sets up expired cache, calls retrieval beyond TTL, verifies API call execution and cache refresh
- **Production Impact**: Ensures resource state information remains current by refreshing stale cache data

#### test_get_bmh_data_force_refresh
- **What**: Tests forced cache refresh regardless of cache validity
- **Why**: Some operations require current data and should bypass cache even when cache is valid
- **How**: Sets up valid cache, calls retrieval with force refresh flag, verifies API call despite valid cache
- **Production Impact**: Provides mechanism to ensure current data when cache might not reflect recent changes

### 3. TestBMHDataUtilities

**Purpose**: Validates utility functions for working with BareMetalHost data structures.

**Why this is tested**: BMH data utilities provide common functionality for searching and manipulating complex BMH data structures returned by OpenShift APIs.

**Key Tests**:

#### test_find_bmh_data_by_name_found
- **What**: Tests successful BMH data lookup by name when resource exists
- **Why**: BMH data lookup is fundamental for resource operations requiring specific BMH resources
- **How**: Provides BMH data with target resource, calls lookup function, verifies correct resource return
- **Production Impact**: Ensures reliable BMH resource discovery for resource management operations

#### test_find_bmh_data_by_name_not_found
- **What**: Tests BMH data lookup when specified resource doesn't exist
- **Why**: Missing BMH resources should be handled gracefully without breaking resource operations
- **How**: Provides BMH data without target resource, calls lookup function, verifies None return
- **Production Impact**: Handles missing BMH resources gracefully, allowing appropriate error handling

#### test_find_bmh_data_by_name_empty_data
- **What**: Tests BMH data lookup with empty or malformed data structures
- **Why**: API responses might be empty or malformed, requiring robust error handling
- **How**: Provides empty data structures, calls lookup function, verifies None return for all cases
- **Production Impact**: Ensures robust handling of API response edge cases and malformed data

### 4. TestOperationFailureHandling

**Purpose**: Validates consistent failure handling across resource management operations.

**Why this is tested**: Resource operations can fail for various reasons, and consistent failure handling ensures proper error reporting and workflow termination.

**Key Tests**:

#### test_handle_operation_failure_with_runtime
- **What**: Tests operation failure handling with runtime calculation and reporting
- **Why**: Failed operations should provide runtime information for troubleshooting and operational analysis
- **How**: Calls failure handler with error and timing information, verifies runtime calculation and return values
- **Production Impact**: Provides valuable operational data when resource operations fail

#### test_handle_operation_failure_without_format_runtime
- **What**: Tests operation failure handling when runtime formatting is not available
- **Why**: Failure handling should work even when optional formatting functions are not available
- **How**: Calls failure handler without format_runtime dependency, verifies graceful handling
- **Production Impact**: Ensures failure handling is resilient to missing optional dependencies

### 5. TestFindAndValidateBMH

**Purpose**: Validates the combined workflow of finding and validating BareMetalHost resources.

**Why this is tested**: BMH finding and validation is a critical first step in most resource operations, combining data retrieval, pattern matching, and validation.

**Key Tests**:

#### test_find_and_validate_bmh_success
- **What**: Tests successful BMH discovery and validation workflow
- **Why**: Most resource operations depend on finding and validating specific BMH resources
- **How**: Mocks successful data retrieval and pattern matching, verifies complete workflow execution
- **Production Impact**: Validates the foundation workflow for most resource management operations

#### test_find_and_validate_bmh_no_data
- **What**: Tests BMH validation when no BMH data is available from cluster
- **Why**: Cluster connectivity or API issues might prevent BMH data retrieval
- **How**: Mocks data retrieval failure, verifies graceful handling and appropriate return values
- **Production Impact**: Handles cluster connectivity issues gracefully during resource operations

#### test_find_and_validate_bmh_not_found
- **What**: Tests BMH validation when specified BMH pattern is not found in cluster
- **Why**: Missing BMH resources should be detected and handled appropriately
- **How**: Mocks data retrieval success but pattern matching failure, verifies error handling
- **Production Impact**: Detects missing BMH resources and prevents operations on non-existent resources

### 6. TestBackupBMHAndMachineResources

**Purpose**: Validates backup operations for BareMetalHost and associated Machine resources.

**Why this is tested**: Resource backup is critical for recovery scenarios and ensures that original configurations can be restored if operations fail.

**Key Tests**:

#### test_backup_bmh_and_machine_success
- **What**: Tests successful backup of both BMH and Machine resources with proper relationship discovery
- **Why**: BMH and Machine resources have relationships that must be preserved during backup operations
- **How**: Mocks successful resource discovery and backup operations, verifies proper sequence and relationships
- **Production Impact**: Ensures complete resource backup maintains resource relationships for recovery operations

#### test_backup_bmh_and_machine_bmh_not_found
- **What**: Tests backup operation when specified BMH resource cannot be found in data
- **Why**: Missing BMH resources should prevent backup operations and provide clear error indication
- **How**: Provides BMH data without target resource, verifies appropriate failure handling
- **Production Impact**: Prevents backup operations on non-existent resources with clear error reporting

#### test_backup_bmh_and_machine_no_consumer_ref
- **What**: Tests backup handling when BMH has no associated Machine resource (consumer reference)
- **Why**: Some BMH resources might not have associated Machine resources, requiring different handling
- **How**: Removes consumer reference from BMH data, verifies appropriate failure handling
- **Production Impact**: Handles BMH resources without Machine associations gracefully

#### test_backup_bmh_and_machine_failed_machine_fetch
- **What**: Tests backup operation when Machine resource data cannot be retrieved
- **Why**: API failures or missing Machine resources should be handled gracefully
- **How**: Mocks Machine data retrieval failure, verifies appropriate error handling
- **Production Impact**: Handles Machine resource access failures without crashing backup operations

### 7. TestRemoveFailedNodeResources

**Purpose**: Validates resource removal operations for failed node cleanup.

**Why this is tested**: Failed node cleanup requires removing both Machine and BareMetalHost resources in proper sequence with appropriate delays.

**Key Tests**:

#### test_remove_failed_node_resources_success
- **What**: Tests successful removal of both Machine and BMH resources with proper sequencing
- **Why**: Resource removal must occur in correct order (Machine first, then BMH) to avoid resource conflicts
- **How**: Mocks successful resource deletion commands, verifies proper command sequence and step progression
- **Production Impact**: Ensures failed node resources are completely removed without leaving orphaned resources

### 8. TestBackupAndRemoveResources

**Purpose**: Validates the complete workflow combining resource backup and removal operations.

**Why this is tested**: The backup-and-remove workflow is a critical component of node replacement operations, requiring coordination of multiple sub-operations.

**Key Tests**:

#### test_backup_and_remove_resources_success
- **What**: Tests complete successful backup and removal workflow with all sub-operations
- **Why**: Full workflow testing ensures all components coordinate correctly for node replacement operations
- **How**: Mocks all sub-operations successfully, verifies complete workflow execution and result propagation
- **Production Impact**: Validates end-to-end backup and removal workflow for node replacement operations

#### test_backup_and_remove_resources_bmh_failure
- **What**: Tests workflow termination when BMH validation fails
- **Why**: BMH validation failures should prevent subsequent operations and provide clear error indication
- **How**: Mocks BMH validation failure, verifies workflow termination and appropriate error propagation
- **Production Impact**: Prevents backup operations when target BMH resources cannot be validated

#### test_backup_and_remove_resources_backup_failure
- **What**: Tests workflow termination when backup operations fail
- **Why**: Backup failures should prevent resource removal to avoid data loss without backup
- **How**: Mocks backup operation failure, verifies workflow termination without resource removal
- **Production Impact**: Protects against data loss by preventing removal when backup fails

### 9. TestMachineSetOperations

**Purpose**: Validates MachineSet discovery, relationship management, and scaling operations.

**Why this is tested**: MachineSet operations are critical for controlled worker node provisioning and deprovisioning, requiring proper discovery of Machine-to-MachineSet relationships.

**Key Tests**:

#### test_find_machineset_for_machine_success
- **What**: Tests successful discovery of MachineSet associated with a specific Machine resource
- **Why**: Machine-to-MachineSet relationship discovery is required for controlled scaling operations
- **How**: Mocks Machine resource with MachineSet owner reference, verifies correct MachineSet identification
- **Production Impact**: Enables controlled MachineSet scaling by discovering Machine resource relationships

#### test_find_machineset_for_machine_no_owner
- **What**: Tests MachineSet discovery when Machine has no MachineSet owner reference
- **Why**: Some Machine resources are not MachineSet-managed and require different handling
- **How**: Mocks Machine resource without owner references, verifies None return for unmanaged machines
- **Production Impact**: Handles manual Machine resources that are not MachineSet-managed

#### test_find_machineset_for_machine_failed_fetch
- **What**: Tests MachineSet discovery when Machine resource data cannot be retrieved
- **Why**: API failures should be handled gracefully without breaking MachineSet operations
- **How**: Mocks Machine data retrieval failure, verifies None return and graceful handling
- **Production Impact**: Handles API access failures during MachineSet relationship discovery

#### test_get_machineset_by_name_found
- **What**: Tests MachineSet lookup by name within MachineSet collection data
- **Why**: MachineSet name-based lookup is required for direct MachineSet operations
- **How**: Provides MachineSet data with target resource, verifies correct resource identification
- **Production Impact**: Enables direct MachineSet access for scaling and configuration operations

#### test_get_machineset_by_name_not_found
- **What**: Tests MachineSet lookup when specified MachineSet doesn't exist in collection
- **Why**: Missing MachineSet resources should be detected and handled appropriately
- **How**: Provides MachineSet data without target resource, verifies None return
- **Production Impact**: Detects missing MachineSet resources to prevent operations on non-existent resources

#### test_scale_machineset_for_machine_scale_up
- **What**: Tests MachineSet scaling up (increasing replicas) for Machine resource
- **Why**: Scale-up operations are required for worker node addition scenarios
- **How**: Mocks successful MachineSet discovery and scaling command, verifies proper replica calculation
- **Production Impact**: Enables controlled worker node addition through MachineSet scaling

#### test_scale_machineset_for_machine_scale_down
- **What**: Tests MachineSet scaling down (decreasing replicas) for Machine resource
- **Why**: Scale-down operations are required for worker node removal scenarios
- **How**: Mocks successful MachineSet discovery and scaling command, verifies proper replica reduction
- **Production Impact**: Enables controlled worker node removal through MachineSet scaling

#### test_scale_machineset_for_machine_no_machineset
- **What**: Tests scaling operation when Machine has no associated MachineSet
- **Why**: Unmanaged machines cannot be scaled through MachineSet operations
- **How**: Mocks MachineSet discovery failure, verifies False return indicating scaling unavailable
- **Production Impact**: Handles manual machines that cannot be scaled through MachineSet operations

#### test_scale_machineset_for_machine_invalid_direction
- **What**: Tests scaling operation with invalid scaling direction parameter
- **Why**: Invalid parameters should be detected and handled to prevent incorrect operations
- **How**: Provides invalid scaling direction, verifies False return and no scaling operations
- **Production Impact**: Prevents incorrect scaling operations due to parameter validation errors

### 10. TestApplyResourcesAndMonitor

**Purpose**: Validates resource application and provisioning monitoring workflows.

**Why this is tested**: Resource application is the final critical step in node provisioning, requiring proper resource deployment and monitoring of provisioning progress.

**Key Tests**:

#### test_apply_resources_and_monitor_control_plane_success
- **What**: Tests successful control plane resource application and provisioning monitoring
- **Why**: Control plane resources require both Machine and BMH resources with monitoring
- **How**: Mocks successful resource application and monitoring, verifies all control plane resources applied
- **Production Impact**: Validates end-to-end control plane node provisioning with monitoring

#### test_apply_resources_and_monitor_worker_addition_success
- **What**: Tests successful worker node addition with MachineSet scaling instead of Machine application
- **Why**: Worker addition uses MachineSet scaling rather than direct Machine resource application
- **How**: Mocks successful BMH application and MachineSet scaling, verifies Machine resource exclusion
- **Production Impact**: Validates end-to-end worker node addition workflow with proper resource handling

#### test_apply_resources_and_monitor_provisioning_failure
- **What**: Tests resource application workflow when provisioning monitoring detects failures
- **Why**: Provisioning failures should be detected and handled with appropriate failure reporting
- **How**: Mocks successful application but failed monitoring, verifies failure handler invocation
- **Production Impact**: Ensures provisioning failures are detected and reported for troubleshooting

#### test_apply_resources_and_monitor_keyboard_interrupt
- **What**: Tests resource application workflow when monitoring is interrupted by user
- **Why**: User interruptions should be handled gracefully without invoking failure handlers
- **How**: Mocks successful application but interrupted monitoring, verifies no failure handler invocation
- **Production Impact**: Handles user interruptions gracefully during provisioning monitoring

### 11. TestIntegration

**Purpose**: Validates end-to-end integration of resource management workflows.

**Why this is tested**: Integration testing ensures all resource management components work together correctly in complete operational scenarios.

**Key Tests**:

#### test_full_backup_and_remove_workflow
- **What**: Tests complete backup and remove workflow from start to finish
- **Why**: Integration testing validates coordination between all backup and removal components
- **How**: Executes complete workflow with realistic timing and dependencies, verifies all operations
- **Production Impact**: Validates end-to-end backup and removal workflow reliability

#### test_full_apply_and_monitor_workflow
- **What**: Tests complete resource application and monitoring workflow
- **Why**: Integration testing ensures proper coordination between resource application and monitoring
- **How**: Executes complete application workflow, verifies resource deployment and monitoring setup
- **Production Impact**: Validates end-to-end resource provisioning workflow reliability

#### test_caching_performance_workflow
- **What**: Tests that BMH data caching provides expected performance improvements
- **Why**: Caching should reduce API calls and improve performance during repeated operations
- **How**: Performs repeated BMH data access, verifies cache usage reduces API calls
- **Production Impact**: Validates performance optimization through effective data caching

## Resource Management Testing Strategy

### Resource Lifecycle Management

The tests validate comprehensive resource lifecycle management:

1. **Discovery**: Finding and validating existing resources in the cluster
2. **Backup**: Creating recovery copies of critical resource configurations
3. **Removal**: Safely removing failed or conflicting resources
4. **Application**: Deploying new resource configurations
5. **Monitoring**: Tracking provisioning progress and detecting failures

### Resource Relationship Handling

The tests ensure proper resource relationship management:

1. **BMH-Machine Relationships**: Consumer references and resource associations
2. **Machine-MachineSet Relationships**: Owner references and scaling coordination
3. **Resource Dependencies**: Proper sequencing of related resource operations

### Performance and Caching

The tests validate performance optimization strategies:

1. **Data Caching**: Reducing redundant API calls through intelligent caching
2. **Cache Management**: Proper cache lifecycle including TTL and refresh mechanisms
3. **Performance Impact**: Verifying that caching provides expected performance benefits

### Error Handling and Recovery

The tests ensure robust error handling:

1. **API Failures**: Graceful handling of OpenShift API access issues
2. **Resource Conflicts**: Detection and resolution of resource naming or relationship conflicts
3. **Partial Failures**: Appropriate handling when some operations succeed while others fail

## Production Readiness Validation

These tests ensure resource management is production-ready by validating:

### Resource Integrity
- All resource operations maintain data integrity and proper relationships
- Backup operations ensure recovery capability for critical configurations
- Resource removal operations are complete and don't leave orphaned resources

### Operational Reliability
- Resource discovery works reliably across different cluster configurations
- MachineSet operations coordinate properly with cluster autoscaling mechanisms
- Provisioning monitoring provides accurate status reporting and failure detection

### Performance Optimization
- BMH data caching reduces cluster API load during resource operations
- Batch operations minimize the number of individual API calls required
- Efficient resource lookup and validation reduces operation latency

### Error Resilience
- API access failures are handled gracefully with appropriate error reporting
- Resource conflicts are detected and resolved without data loss
- Partial operation failures provide sufficient information for manual recovery

## Maintenance and Evolution

This test suite should be maintained by:

### Resource Schema Updates
- Update test fixtures when Kubernetes resource schemas change
- Add tests for new resource types as they become available
- Maintain compatibility with different OpenShift versions

### Performance Optimization
- Add performance benchmarks for resource operations
- Validate caching effectiveness under different usage patterns
- Test resource operation scalability with large numbers of resources

### Error Scenario Expansion
- Add tests for new error conditions discovered in production
- Expand failure handling validation based on operational experience
- Include network partition and partial cluster failure scenarios

### Integration Validation
- Test integration with new OpenShift operators and controllers
- Validate resource management compatibility with cluster upgrades
- Ensure resource operations work correctly with different hardware types

The comprehensive nature of these tests ensures that resource management operations can be confidently used in production OpenShift environments where resource integrity and operational reliability are critical.
