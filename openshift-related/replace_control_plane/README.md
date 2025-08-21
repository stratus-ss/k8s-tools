# OpenShift Node Replacement Tool

A powerful command-line tool designed to automate the replacement of a failed control plane node in an OpenShift Container Platform cluster. This script handles the entire lifecycle of the replacement process, from identifying the failed node and safely removing it from the etcd cluster to provisioning and integrating a new node.

## ✨ Features

### 🚀 Core Capabilities
- **Automated Control Plane Recovery** - Complete 12-step replacement process
- **ETCD Cluster Management** - Safe member removal and quorum guard handling  
- **Smart CSR Handling** - Automatic certificate approval after 10-minute threshold

### 🛡️ Safety Features  
- **Quorum Guard Management** - Automatic disable/enable with verification
- **Resource Validation** - Confirms successful removal before proceeding
- **Backup & Restore** - Preserves BMH, machine, and secret configurations

### 📊 Monitoring & Reporting
- **Real-time Progress** - Step-by-step status with timing information
- **CSR Status Tracking** - Visual indicators for certificate approval state
- **Success/Failure Reporting** - Clear outcome summaries with next steps

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Failed Node   │    │  ETCD Recovery  │    │ Resource Backup │
│   Detection     │───▶│   & Cleanup     │───▶│  & Validation   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Node Ready    │    │  4-Phase        │    │ Replacement     │
│  & Monitoring   │◀───│  Provisioning   │◀───│ Configuration   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📋 Prerequisites

### Required Software
- **Python 3.8+** with PyYAML support
- **OpenShift CLI (`oc`)** - Authenticated to target cluster
> [!NOTE]
> Currently the program assumes you have already authenticated and have a valid session.
> Initial iteration uses the `oc` commands instead of talking directly to the API  

- **Cluster Admin Access** - Required for ETCD and machine operations
- **Network Access** - To BMC interfaces and cluster APIs

### Supported Platforms
- **OpenShift 4.x** on bare metal
- **RHEL/CentOS/Fedora** administration hosts
- **BMC-enabled Hardware** (iDRAC, iLO, Libvirt + Sushy, etc.)

### Infrastructure Requirements
- Healthy ETCD quorum (at least 2/3 members functional)
- Available replacement hardware with BMC access
- Network connectivity to replacement node BMC
- Existing network configuration for replacement node

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/stratus-ss/k8s-tools.git
cd openshift-related
```

### 2. Set Up Environment (Development Only)
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (optional - for development)
make install
```

### 3. Run Control Plane Replacement
```bash
python3 replace_control_plane/replace_control_plane.py \
  --replacement_node "ocp-control3" \
  --replacement_node_ip "192.168.1.13" \
  --replacement_node_bmc_ip "192.168.100.13" \
  --replacement_node_mac_address "aa:bb:cc:dd:ee:f3" \
  --replacement_node_role "control" \
  --backup_dir "/home/admin/backups/cluster1"
```

## 📖 Detailed Usage

### Command Line Arguments

| Argument | Required | Description | Example |
|----------|----------|-------------|---------|
| `--replacement_node` | ✅ | Name of replacement node | `ocp-control3` |
| `--replacement_node_ip` | ✅ | IP address for replacement | `192.168.1.13` |
| `--replacement_node_bmc_ip` | ✅ | BMC IP for hardware control | `192.168.100.13` |
| `--replacement_node_mac_address` | ✅ | Boot MAC address | `aa:bb:cc:dd:ee:f3` |
| `--replacement_node_role` | ✅ | Node role (`control`/`master`) | `control` |
| `--backup_dir` | ❌ | Custom backup directory | `/path/to/backups` |
| `--sushy_uid` | ❌ | Redfish system UID override | `c4f5c-40d6-ad72-a3879c` |
| `--debug` | ❌ | Enable detailed logging | - |


## 🔄 Process Overview

The tool executes a comprehensive 12-step process:

### Phase 1: Preparation & Discovery
1. **Setup** - Initialize backup directory and validate configuration
2. **Discovery** - Identify failed control plane node automatically
3. **ETCD Recovery** - Remove failed member from ETCD cluster

### Phase 2: Cluster Preparation  
4. **Quorum Guard** - Temporarily disable for safe operations
5. **Secret Cleanup** - Remove ETCD secrets for failed node
6. **Resource Backup** - Save BMH, machine, and network configurations

### Phase 3: Resource Management
7. **Resource Removal** - Clean removal of failed BMH and machine
8. **Validation** - Confirm successful resource cleanup
9. **Configuration** - Prepare replacement node configurations

### Phase 4: Provisioning & Recovery
10. **Deployment** - Apply secrets and BMH for replacement node
11. **Monitoring** - 4-phase provisioning with CSR management
12. **Finalization** - Re-enable quorum guard with verification


## 🛠️ Development

### Setup Development Environment
```bash
# Clone and setup
git clone https://github.com/stratus-ss/k8s-tools.git
cd openshift-related

# Create virtual environment  
python3 -m venv .venv
source .venv/bin/activate

# Install development dependencies
make install
```

### Available Make Targets
```bash
make help          # Show all available commands
make format        # Format code with black (120 char lines)
make lint          # Lint code with flake8  
make check         # Check formatting without changes
make test          # Run syntax and import tests
make fix           # Format and lint together
make clean         # Remove Python cache files
make validate      # Quick script validation
make all           # Run format, lint, and test
```

### Code Quality Standards
- **Line Length**: 120 characters maximum
- **Formatting**: Black code formatter
- **Linting**: Flake8 with custom rules
- **Documentation**: Google-style docstrings
- **Testing**: Unit tests for all components



### Configuration Management
- **`pyproject.toml`** - Python project configuration
- **`.flake8`** - Linting rules and exclusions  
- **`Makefile`** - Development workflow automation

## 🚨 Troubleshooting

### Common Issues

#### BMH Not Becoming Available
```bash
# Check BMH status
oc get bmh <node-name> -n openshift-machine-api

# Check BMH details  
oc describe bmh <node-name> -n openshift-machine-api

# Verify BMC connectivity
ping <bmc-ip>
```

#### ETCD Recovery Failures
```bash
# Check ETCD pod health
oc get pods -n openshift-etcd -l app=etcd

# Verify ETCD endpoints
oc exec -n openshift-etcd <etcd-pod> -- etcdctl endpoint health

# Check ETCD member list
oc exec -n openshift-etcd <etcd-pod> -- etcdctl member list
```

#### CSR Approval Issues
```bash
# List pending CSRs
oc get csr | grep Pending

# Manually approve CSRs
oc adm certificate approve <csr-name>

# Watch CSR creation
oc get csr --watch
```


## 📄 License

This repo is licensed under the GPL3 - see the [LICENSE](https://github.com/stratus-ss/k8s-tools/blob/main/LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines:

### Code Quality Requirements
- All code must pass `make all` (format, lint, test)
- Maintain 120-character line length limit
- Include docstrings for new functions/classes
- Add unit tests for new functionality
- Update documentation as needed

### Issues & Bug Reports
Please use GitHub Issues for:
- 🐛 Bug reports with reproduction steps
- 💡 Feature requests with use cases
- 📚 Documentation improvements
- ❓ Questions about usage


## ⭐ Acknowledgments

- **OpenShift Community** - For comprehensive documentation and tools
- **Cursor.AI** - The initial project was written by converting known steps in bash to python. Cursor was used for regex, loop checks and other related tasks
