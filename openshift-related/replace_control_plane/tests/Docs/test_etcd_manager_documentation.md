# ETCD Manager Test Suite Documentation

## Overview

The `test_etcd_manager.py` file contains comprehensive test coverage for the ETCD management functions responsible for handling ETCD cluster operations during OpenShift control plane node replacement and expansion. This test suite validates critical ETCD operations including member management, quorum guard handling, secret cleanup, and cluster health monitoring.

## Purpose and Context

ETCD is the critical distributed key-value store that serves as the backbone of the Kubernetes control plane, storing all cluster state and configuration data. During control plane node replacement or expansion operations, ETCD cluster integrity must be carefully maintained to prevent data loss and ensure cluster availability. The ETCD manager handles complex operations like:

- Identifying and removing failed ETCD members from the cluster
- Managing quorum guard settings to enable unsafe operations temporarily  
- Cleaning up orphaned ETCD secrets and certificates
- Coordinating ETCD operations across the replacement/expansion workflow

These operations are extremely sensitive and require comprehensive testing to ensure cluster stability and data integrity.

## Test Structure and Organization

### Test Fixtures and Data

The test suite uses realistic ETCD cluster data fixtures:

- **sample_etcd_pods_data**: Real ETCD pod data with running and failed pods
- **sample_etcd_endpoint_health**: ETCD endpoint health status with failed endpoints  
- **sample_etcd_member_list**: Complete ETCD member list with cluster metadata
- **sample_etcd_member_remove_result**: Results after member removal operations
- **sample_etcd_secrets**: ETCD certificate and credential secrets
- **sample_control_plane_nodes**: Control plane node data for node discovery

**Why realistic ETCD fixtures matter**: ETCD operations work with complex cluster metadata including member IDs, client URLs, peer URLs, and cluster revisions. Real production data ensures tests validate behavior against actual ETCD cluster configurations.

## Test Classes and Their Purposes

### 1. TestGetHealthyEtcdPod

**Purpose**: Validates the critical functionality for finding healthy ETCD pods that can be used for cluster operations.

**Why this is tested**: ETCD operations require executing commands against healthy ETCD pods. Using failed or unhealthy pods could result in operation failures or inconsistent cluster state.

**Key Tests**:

#### test_get_healthy_etcd_pod_success
- **What**: Verifies successful identification of healthy ETCD pods excluding failed nodes
- **Why**: Operations must use pods that are actually running and accessible, not just any pod
- **How**: Provides pod data with mixed states, specifies failed node to exclude, verifies correct healthy pod selection
- **Production Impact**: Ensures ETCD operations are executed against reliable, responsive pods

#### test_get_healthy_etcd_pod_exclude_failed_node
- **What**: Tests that the specified failed node is properly excluded from selection
- **Why**: Using the failed node's ETCD pod could cause operations to fail or provide stale data
- **How**: Specifies the first healthy pod's node as "failed", verifies selection of alternative healthy pod
- **Production Impact**: Prevents attempts to use ETCD pods from nodes that are being replaced

#### test_get_healthy_etcd_pod_no_pods_data
- **What**: Tests graceful handling when no ETCD pod data is available
- **Why**: Cluster access issues or network problems may prevent pod data retrieval
- **How**: Mocks oc command to return None, verifies graceful None return
- **Production Impact**: Prevents crashes when cluster access is unavailable

#### test_get_healthy_etcd_pod_no_healthy_pods
- **What**: Tests behavior when no healthy ETCD pods are available
- **Why**: Cluster degradation might result in all ETCD pods being unhealthy
- **How**: Provides pod data with only failed/pending pods, verifies None return
- **Production Impact**: Detects when cluster is too degraded for ETCD operations

#### test_get_healthy_etcd_pod_empty_items
- **What**: Tests handling of empty pod lists from OpenShift API
- **Why**: Edge cases in OpenShift API responses may return empty lists
- **How**: Provides empty items list, verifies graceful handling
- **Production Impact**: Handles API edge cases without crashing

### 2. TestRemoveFailedEtcdMember

**Purpose**: Validates the complex workflow for safely removing failed ETCD members from the cluster.

**Why this is tested**: Failed ETCD member removal is critical for cluster health but extremely dangerous if done incorrectly. Removing the wrong member or failing to remove a failed member can cause data loss or cluster splits.

**Key Tests**:

#### test_remove_failed_etcd_member_success
- **What**: Tests complete failed member removal workflow including endpoint health checking, member identification, and removal
- **Why**: Member removal requires coordinating endpoint health status with member list data to identify the correct failed member
- **How**: Mocks endpoint health with one failed endpoint, member list with corresponding member, verifies removal with correct hex member ID
- **Production Impact**: Ensures failed members are correctly identified and safely removed from ETCD cluster

#### test_remove_failed_etcd_member_no_failed_endpoint
- **What**: Tests behavior when no failed endpoints are detected  
- **Why**: If all endpoints are healthy, no member removal is necessary
- **How**: Provides all healthy endpoints, verifies no member operations are attempted
- **Production Impact**: Prevents unnecessary member operations when cluster is healthy

#### test_remove_failed_etcd_member_member_not_found
- **What**: Tests handling when failed endpoint doesn't correspond to any cluster member
- **Why**: Failed endpoints might not always have corresponding members (e.g., already removed)
- **How**: Provides failed endpoint but member list without matching member, verifies warning message
- **Production Impact**: Handles cases where member might have been removed through other means

#### test_remove_failed_etcd_member_ip_match
- **What**: Tests fallback member matching by IP address when URL matching fails
- **Why**: ETCD member URLs and endpoint URLs might have different ports or formats
- **How**: Provides endpoint and member with same IP but different ports, verifies IP-based matching
- **Production Impact**: Ensures member identification works even with URL format differences

### 3. TestQuorumGuardFunctions

**Purpose**: Validates the critical quorum guard management that enables and disables ETCD safety mechanisms.

**Why this is tested**: Quorum guard is a safety mechanism that prevents unsafe ETCD operations. It must be disabled temporarily for node replacement operations but re-enabled afterward to maintain production safety.

**Key Tests**:

#### test_disable_quorum_guard
- **What**: Tests disabling ETCD quorum guard with appropriate wait times
- **Why**: Quorum guard must be disabled before unsafe operations, with sufficient time for ETCD cluster to adapt
- **How**: Mocks successful patch command, verifies 120-second wait time, validates proper messaging
- **Production Impact**: Ensures quorum guard is properly disabled before dangerous operations

#### test_disable_quorum_guard_already_disabled
- **What**: Tests behavior when quorum guard is already disabled (no changes needed)
- **Why**: Repeated operations shouldn't cause unnecessary delays or cluster disruption
- **How**: Mocks "unchanged" patch response, verifies no sleep delay, validates skip messaging
- **Production Impact**: Optimizes operations by skipping unnecessary waits when guard already disabled

#### test_enable_quorum_guard
- **What**: Tests re-enabling quorum guard with proper wait times
- **Why**: Quorum guard must be restored after operations to ensure production safety
- **How**: Verifies patch command to restore null configuration, validates 60-second wait time
- **Production Impact**: Ensures cluster returns to production-safe configuration after operations

### 4. TestCleanupEtcdSecrets

**Purpose**: Validates cleanup of orphaned ETCD secrets and certificates associated with failed nodes.

**Why this is tested**: Failed nodes leave behind ETCD secrets (certificates, keys) that must be cleaned up to prevent security issues and resource bloat. Cleanup must identify the correct secrets without affecting other nodes.

**Key Tests**:

#### test_cleanup_etcd_secrets_success
- **What**: Tests complete secret cleanup workflow including node discovery and targeted secret deletion
- **Why**: Secret cleanup must identify the full node name and find all related secrets for proper cleanup
- **How**: Mocks node discovery, secret listing, verifies deletion of node-specific secrets with proper delays
- **Production Impact**: Ensures orphaned ETCD secrets are properly removed without affecting other nodes

#### test_cleanup_etcd_secrets_no_nodes
- **What**: Tests fallback behavior when control plane node data cannot be retrieved
- **Why**: Cluster access issues shouldn't prevent secret cleanup operations entirely
- **How**: Mocks failed node retrieval, verifies fallback to short node name, validates warning messaging
- **Production Impact**: Allows secret cleanup to proceed even when cluster node data is inaccessible

#### test_cleanup_etcd_secrets_no_secrets
- **What**: Tests handling when no ETCD secrets can be retrieved
- **Why**: Secret list retrieval failures shouldn't crash the cleanup process
- **How**: Mocks successful node retrieval but failed secret listing, verifies graceful handling
- **Production Impact**: Prevents crashes during secret cleanup when OpenShift API access is limited

#### test_cleanup_etcd_secrets_no_matching_secrets
- **What**: Tests behavior when no secrets match the failed node name
- **Why**: Node names might not match secret naming patterns, or secrets might already be cleaned
- **How**: Provides non-matching secrets, verifies no deletion attempts, validates completion messaging
- **Production Impact**: Handles cases where secrets don't exist or follow different naming patterns

### 5. TestEtcdOperationsFunctions

**Purpose**: Validates high-level ETCD operation orchestration functions that coordinate multiple ETCD operations in workflows.

**Why this is tested**: The high-level functions orchestrate complex workflows involving multiple ETCD operations, timing coordination, and error handling. These functions must handle partial failures gracefully and provide proper workflow progression.

**Key Tests**:

#### test_handle_etcd_operations_for_expansion
- **What**: Tests ETCD operations coordination for control plane expansion scenarios
- **Why**: Control plane expansion requires specific ETCD preparation (disabling quorum guard) but no member removal
- **How**: Verifies quorum guard disabling, step progression, timing tracking, and success messaging
- **Production Impact**: Ensures control plane expansion properly prepares ETCD cluster for additional members

#### test_handle_etcd_operations_for_replacement_success
- **What**: Tests complete ETCD replacement workflow including member removal, quorum guard, and secret cleanup
- **Why**: Control plane replacement requires coordinated ETCD operations in proper sequence with error handling
- **How**: Mocks all sub-operations successfully, verifies correct calling sequence and step progression
- **Production Impact**: Ensures control plane replacement properly handles all ETCD cluster updates

#### test_handle_etcd_operations_for_replacement_no_healthy_pods
- **What**: Tests early failure when no healthy ETCD pods are available
- **Why**: ETCD operations cannot proceed without healthy pods; early detection prevents cascading failures
- **How**: Mocks healthy pod discovery to return None, verifies early exit with error messaging
- **Production Impact**: Prevents attempted operations when cluster is too degraded

#### test_handle_etcd_operations_for_replacement_member_removal_fails
- **What**: Tests workflow failure when ETCD member removal fails
- **Why**: Member removal failure indicates serious cluster issues requiring manual intervention
- **How**: Mocks successful pod discovery but failed member removal, verifies error handling and exit
- **Production Impact**: Ensures failed member removal doesn't lead to incomplete workflows

#### test_re_enable_quorum_guard_after_expansion
- **What**: Tests quorum guard re-enablement after successful expansion operations
- **Why**: Expansion operations must restore production safety mechanisms after completion
- **How**: Verifies quorum guard enablement, timing tracking, completion messaging
- **Production Impact**: Ensures cluster returns to production-safe configuration after expansion

### 6. TestEtcdManagerIntegration

**Purpose**: Validates end-to-end integration of multiple ETCD manager functions in realistic workflows.

**Why this is tested**: Individual function testing doesn't validate proper coordination and sequencing. Integration testing ensures functions work together correctly in real replacement scenarios.

**Key Tests**:

#### test_full_replacement_workflow
- **What**: Tests complete ETCD replacement workflow from start to finish
- **Why**: Control plane replacement requires all ETCD operations to coordinate properly for successful completion
- **How**: Executes handle_etcd_operations_for_replacement with all sub-operations mocked, verifies complete workflow
- **Production Impact**: Validates the entire ETCD replacement process works end-to-end

## ETCD Operation Safety and Testing Strategy

### Critical Safety Mechanisms

The tests validate multiple layers of safety mechanisms:

1. **Member Identification Safety**: Tests ensure failed members are correctly identified through multiple verification methods (endpoint health + member list correlation)

2. **Quorum Guard Management**: Tests validate that quorum guard is disabled only when necessary and re-enabled afterward to maintain cluster safety

3. **Operation Sequencing**: Tests verify that operations occur in the correct order to prevent cluster corruption

4. **Error Handling**: Tests ensure that failed operations don't leave the cluster in inconsistent states

### Realistic Failure Scenarios

Tests cover realistic production failure scenarios:

- **Network partition scenarios**: Failed endpoints with different error types
- **Partial cluster degradation**: Some healthy pods available while others fail
- **API access issues**: OpenShift command failures and data retrieval problems
- **Timing sensitivity**: Operations that require specific wait times and sequencing

### ETCD Cluster State Management

Tests validate proper ETCD cluster state management:

- **Member lifecycle**: Addition, removal, and health monitoring of ETCD members
- **Certificate management**: Cleanup of expired or orphaned certificates and secrets
- **Cluster metadata**: Proper handling of cluster IDs, revisions, and Raft terms
- **Endpoint consistency**: Coordination between client URLs, peer URLs, and health status

## Production Readiness Validation

These tests ensure ETCD operations are production-ready by validating:

### Data Safety
- No operations that could cause data loss or cluster splits
- Proper identification of failed members before removal
- Safe quorum guard handling to prevent unsafe operations

### Operation Reliability
- Graceful handling of partial failures and edge cases
- Proper error detection and recovery mechanisms
- Consistent operation outcomes across different cluster states

### Workflow Coordination
- Correct sequencing of complex multi-step operations
- Proper timing and wait periods for cluster adaptation
- Clean error propagation and workflow termination

### Operational Visibility
- Comprehensive logging of all critical operations
- Clear status reporting and error messaging
- Proper step progression tracking for operational awareness

## Error Handling Philosophy

The ETCD manager tests validate comprehensive error handling:

### Early Detection
- Identify problems before attempting dangerous operations
- Validate cluster health before proceeding with changes
- Check for required resources and access before starting workflows

### Graceful Degradation
- Handle partial failures without cascading errors
- Provide fallback mechanisms where possible
- Clean termination when operations cannot safely proceed

### Recovery Support
- Provide sufficient information for manual recovery
- Avoid leaving cluster in inconsistent intermediate states
- Enable safe retry of failed operations

### Safety First
- Err on the side of caution when cluster integrity is at risk
- Prefer operation failure over potential data loss
- Require explicit confirmation for dangerous operations

## Integration with OpenShift Operations

The tests validate proper integration with OpenShift:

### API Consistency
- Correct use of OpenShift and Kubernetes APIs
- Proper error handling for API failures and timeouts
- Consistent data formats and response handling

### Namespace and Resource Management
- Correct targeting of openshift-etcd namespace resources
- Proper secret and certificate lifecycle management
- Accurate resource identification and manipulation

### Cluster State Coordination
- Synchronization with OpenShift cluster operators
- Proper handling of cluster version and upgrade states
- Coordination with other control plane components

## Maintenance and Evolution

This test suite should be maintained by:

### Version Compatibility
- Update tests for new ETCD versions and API changes
- Validate compatibility with OpenShift version upgrades
- Test against different cluster configurations and scales

### Failure Pattern Updates
- Add tests for new failure modes discovered in production
- Update error handling based on operational experience
- Enhance edge case coverage based on incident analysis

### Performance Validation
- Add timing validations for critical operations
- Test behavior under high load or resource constraints
- Validate timeout handling and recovery mechanisms

### Security Enhancement
- Update certificate and credential handling tests
- Validate new security features and requirements
- Ensure secret cleanup remains comprehensive and secure

The comprehensive nature of these tests ensures that ETCD operations can be confidently used in production OpenShift environments where cluster stability and data integrity are absolutely critical.
