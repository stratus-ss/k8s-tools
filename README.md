# k8s-tools

A comprehensive collection of Kubernetes and OpenShift administration tools for cluster management, automation, and development workflows.

## 🚀 Overview

This repository contains a diverse set of tools and utilities designed to simplify Kubernetes and OpenShift cluster operations, from ETCD backup management to complete control plane replacement automation. Whether you're managing bare metal clusters, performing routine maintenance, or developing AI-powered workflows, these tools provide enterprise-grade solutions for common infrastructure challenges.

## 📋 Table of Contents

- [Tools Overview](#-tools-overview)
- [Quick Start](#-quick-start)
- [Detailed Tool Documentation](#-detailed-tool-documentation)
- [Installation Guide](#-installation-guide)
- [Usage Examples](#-usage-examples)
- [Contributing](#-contributing)
- [License](#-license)

## 🛠️ Tools Overview

### Core Kubernetes Tools

| Tool | Language | Purpose | Status |
|------|----------|---------|--------|
| **[etcdBackup](#etcd-backup-tool)** | Go | On-demand ETCD database backup with multiple storage backends | ✅ Production Ready |
| **[pullSecretUser](#pull-secret-auditing-tool)** | Go | Audit and discover pull secrets across cluster projects | ✅ Production Ready |
| **[serviceAccount_Secrets](#service-account-secrets-tool)** | Go | Find and manage service account secrets | ✅ Production Ready |
| **[watchResource](#resource-monitoring-tool)** | Go | Monitor and manage Seldon ML deployments | ✅ Production Ready |

### OpenShift Management Tools

| Tool | Language | Purpose | Status |
|------|----------|---------|--------|
| **[replace_control_plane](#openshift-control-plane-management)** | Python | Complete control plane replacement, expansion, and worker node addition | ✅ Production Ready |
| **[installation-helpers](#openshift-installation-helpers)** | YAML/Scripts | OpenShift installation templates and automation | ✅ Production Ready |

### Infrastructure & Development

| Tool | Language | Purpose | Status |
|------|----------|---------|--------|
| **[k8s_install_scripts](#kubernetes-installation-scripts)** | Bash/YAML | Vanilla Kubernetes installation and post-setup automation | ✅ Production Ready |
| **[mcp-server](#mcp-server-integration)** | Bash/Config | Model Context Protocol server integration for AI-powered workflows | ✅ Production Ready |

## 🏃‍♂️ Quick Start

### Prerequisites

- **Go 1.17+** (for Go tools)
- **Python 3.8+** (for Python tools)
- **kubectl** with cluster-admin access
- **oc** CLI (for OpenShift tools)
- **Docker** (for some integrations)

### Basic Installation

```bash
# Clone the repository
git clone https://github.com/stratus-ss/k8s-tools.git
cd k8s-tools

# Build Go tools
cd etcdBackup && go build -o etcdBackup . && cd ..
cd pullSecretUser && go build -o auditPullSecrets . && cd ..
cd serviceAccount_Secrets && go build -o get_svc_account_from_secrets . && cd ..

# Setup Python environment (for OpenShift tools)
cd openshift-related/replace_control_plane
python3 -m venv venv
source venv/bin/activate
pip install -e .
cd ../..
```

## 📖 Detailed Tool Documentation

### ETCD Backup Tool

**Location**: `etcdBackup/`  
**Purpose**: Comprehensive ETCD database backup solution with multiple storage backend support

#### Features
- ✅ **NFS PVC Support** - Backup to Network File System volumes
- ✅ **Dynamic Storage** - Backup to dynamically provisioned persistent volumes
- ✅ **Local Downloads** - Pull backups directly to local machine
- ✅ **Dual Storage** - Simultaneous backup to both NFS and dynamic storage
- ✅ **Error Handling** - Robust error handling for unbound PVCs and job failures
- ✅ **Cluster Integration** - Works with any cluster-admin authenticated user

#### Quick Usage
```bash
# NFS backup
./etcdBackup -kube-config=/path/to/kubeconfig -use-nfs=true \
  -nfs-server=192.168.1.100 -nfs-path=/storage/etcd_backups -debug=true

# Dynamic storage backup
./etcdBackup -kube-config=/path/to/kubeconfig -use-dynamic-storage -debug=true

# Local backup
./etcdBackup -kube-config=/path/to/kubeconfig -use-pvc=false \
  -local-backup-dir=./backups -debug=true
```

📄 **[Complete ETCD Backup Documentation](etcdBackup/README.md)**

---

### OpenShift Control Plane Management

**Location**: `openshift-related/replace_control_plane/`  
**Purpose**: Enterprise-grade automation for OpenShift bare metal cluster management

#### Operation Modes
- 🔄 **Control Plane Replacement** - Replace failed control plane nodes (default)
- 📈 **Control Plane Expansion** - Add new control plane nodes (3→5 or 5→7)
- 👷 **Worker Node Addition** - Expand cluster compute capacity

#### Key Features
- ✅ **4-Phase Provisioning** - BMH → Machine → Node → Ready monitoring
- ✅ **ETCD Management** - Safe member removal and cluster recovery
- ✅ **CSR Auto-Approval** - Automatic certificate approval after threshold
- ✅ **Smart Templates** - Intelligent template selection and configuration
- ✅ **Comprehensive Testing** - 26 tests with 100% coverage

#### Architecture Options
- **Monolithic**: Single-file deployment (`replace_control_plane.py`)
- **Modular**: Professional component structure (`replace_control_plane_modular.py`)

#### Quick Usage Examples
```bash
# Control plane replacement
python3 replace_control_plane.py \
  --replacement_node "ocp-control4.example.com" \
  --replacement_node_ip "192.168.1.14" \
  --replacement_node_bmc_ip "192.168.100.14" \
  --replacement_node_mac_address "aa:bb:cc:dd:ee:f4" \
  --replacement_node_role "control" --debug

# Control plane expansion  
python3 replace_control_plane.py \
  --replacement_node "ocp-control4.example.com" \
  --replacement_node_ip "192.168.1.14" \
  --replacement_node_bmc_ip "192.168.100.14" \
  --replacement_node_mac_address "aa:bb:cc:dd:ee:f4" \
  --replacement_node_role "control" \
  --expand-control-plane --debug
```

📄 **[Complete OpenShift Control Plane Documentation](openshift-related/replace_control_plane/README.md)**

---

### Pull Secret Auditing Tool

**Location**: `pullSecretUser/`  
**Purpose**: Cluster-wide pull secret discovery and auditing

#### Features
- 🔍 **Comprehensive Scanning** - Searches all namespaces for pull secrets
- 👤 **User-Specific Search** - Find secrets containing specific usernames
- 🚀 **Performance Optimized** - Option to skip OpenShift system projects
- 📊 **Detailed Output** - Shows secret name, project, username, and password
- 🔧 **Flexible Configuration** - Supports custom data types and multiple search criteria

#### Usage
```bash
# Basic usage - find 'deployer' service account
./auditPullSecrets -kube-config=/path/to/kubeconfig -service-account=deployer

# Find specific username with debug output
./auditPullSecrets -kube-config=/path/to/kubeconfig \
  -service-account=myuser -debug=true
```

---

### Service Account Secrets Tool

**Location**: `serviceAccount_Secrets/`  
**Purpose**: Service account secret management and discovery

#### Features
- 🎯 **Targeted Search** - Find secrets associated with specific service accounts
- 📋 **Annotation-Based** - Uses service account annotations for filtering
- ⚡ **Efficient Scanning** - Skips OpenShift system projects by default
- 📖 **Clear Output** - Displays namespace, secret name, and account name

#### Usage
```bash
# Find secrets for service account
./get_svc_account_from_secrets -kube-config=/path/to/kubeconfig \
  -service-account=deployer
```

---

### Resource Monitoring Tool

**Location**: `watchResource/`  
**Purpose**: Seldon deployment management and monitoring

#### Features
- 🤖 **ML Platform Integration** - Native Seldon Core support
- 📊 **Resource Management** - List and create Seldon deployments
- 🔧 **Client Library** - Reusable Go client for Seldon operations
- ⚙️ **Auto-Configuration** - Uses in-cluster or kubeconfig authentication

---

### Kubernetes Installation Scripts

**Location**: `k8s_install_scripts/`  
**Purpose**: Vanilla Kubernetes cluster setup and post-installation configuration

#### Components
- 📋 **kubeadmcfg.conf** - Production-ready kubeadm configuration
- 🚀 **post-install-setup.sh** - Complete post-installation automation

#### Features
- 🌐 **CNI Integration** - Kube-OVN network setup
- 🔧 **Ingress Controller** - HAProxy ingress with SSL/TLS
- 📊 **Monitoring Stack** - Prometheus and Grafana deployment
- 🔍 **Observability** - Pre-configured dashboards and alerting

#### Quick Setup
```bash
# Initialize cluster with custom config
sudo kubeadm init --config=k8s_install_scripts/kubeadmcfg.conf

# Run post-installation automation
cd k8s_install_scripts
chmod +x post-install-setup.sh
./post-install-setup.sh
```

---

### OpenShift Installation Helpers

**Location**: `openshift-related/installation-helpers/`  
**Purpose**: OpenShift bare metal installation automation and templates

#### Features
- 📋 **Install Config Templates** - Jinja2-based configuration templates
- 🔧 **BMH Templates** - BareMetalHost configuration generators
- 🔐 **Secret Management** - BMC and network secret templates
- 🛡️ **Security Integration** - HTPasswd provider configuration

#### Components
- `install-config-template.j2` - Main installation configuration template
- `baremetal-host-template.j2` - BareMetalHost resource template
- `baremetal-hosts-config-generator.yaml` - Automated BMH generation
- `htpasswd_cr.yaml` - HTPasswd authentication setup

---

### MCP Server Integration

**Location**: `mcp-server/`  
**Purpose**: Model Context Protocol server integration for AI-powered development workflows

#### Features
- 🤖 **7 Integrated MCP Servers** - Kubernetes, GitHub, Memory Bank, Context7, etc.
- 🔧 **Service Management** - Systemd service configuration
- 🚀 **Auto-Start Scripts** - Intelligent startup with health checks
- 📊 **Multi-Mode Operation** - Normal, readonly, and safe modes
- 🔍 **Comprehensive Logging** - Structured logging with multiple levels

#### Available MCP Servers
1. **kubernetes-mcp-server** - Kubernetes cluster management
2. **cursor-chat-history** - Chat history persistence
3. **cursor-buddy-mcp** - Project management and todos
4. **github** - GitHub API integration
5. **allpepper-memory-bank** - Project memory and context
6. **context7** - AI-powered library documentation
7. **contextkeeper** - C# codebase analysis

📄 **[Complete MCP Server Configuration Guide](MCP_SERVER_CONFIGURATION_GUIDE.md)**

## 💡 Usage Examples

### Complete ETCD Backup Strategy
```bash
#!/bin/bash
# Daily ETCD backup script
BACKUP_DATE=$(date +%Y%m%d)
KUBECONFIG_PATH="/path/to/kubeconfig"
NFS_SERVER="192.168.1.100"
NFS_PATH="/storage/etcd_backups/$BACKUP_DATE"

# Create backup with both NFS and dynamic storage
./etcdBackup/etcdBackup \
  -kube-config="$KUBECONFIG_PATH" \
  -use-nfs=true \
  -use-dynamic-storage=true \
  -nfs-server="$NFS_SERVER" \
  -nfs-path="$NFS_PATH" \
  -debug=true

if [ $? -eq 0 ]; then
    echo "ETCD backup completed successfully for $BACKUP_DATE"
else
    echo "ETCD backup failed for $BACKUP_DATE" >&2
    exit 1
fi
```

### Security Audit Workflow
```bash
#!/bin/bash
# Complete cluster security audit
KUBECONFIG_PATH="/path/to/kubeconfig"
AUDIT_DATE=$(date +%Y%m%d)
REPORT_DIR="./security-audit-$AUDIT_DATE"

mkdir -p "$REPORT_DIR"

echo "=== Starting Security Audit for $(date) ===" | tee "$REPORT_DIR/audit.log"

# Audit pull secrets
echo "Auditing pull secrets..." | tee -a "$REPORT_DIR/audit.log"
./pullSecretUser/auditPullSecrets \
  -kube-config="$KUBECONFIG_PATH" \
  -service-account=deployer \
  -debug=true > "$REPORT_DIR/pull-secrets.txt"

# Audit service account secrets
echo "Auditing service account secrets..." | tee -a "$REPORT_DIR/audit.log"
./serviceAccount_Secrets/get_svc_account_from_secrets \
  -kube-config="$KUBECONFIG_PATH" \
  -service-account=deployer > "$REPORT_DIR/service-account-secrets.txt"

echo "Security audit completed. Results in $REPORT_DIR/"
```

## 🔧 Installation Guide

### System Requirements

#### Minimum Requirements
- **OS**: Linux (RHEL/CentOS/Ubuntu/Fedora)
- **CPU**: 2 cores
- **Memory**: 4GB RAM
- **Storage**: 20GB free space
- **Network**: Internet connectivity for package downloads

#### Software Dependencies
- **Go 1.17+** (for Go-based tools)
- **Python 3.8+** (for OpenShift tools)
- **Node.js 16+** (for MCP servers)
- **Docker** (for containerized components)
- **kubectl** (Kubernetes client)
- **oc** (OpenShift client, for OpenShift tools)

### Complete Installation

```bash
# 1. Clone repository
git clone https://github.com/stratus-ss/k8s-tools.git
cd k8s-tools

# 2. Install system dependencies (Ubuntu/Debian)
sudo apt update
sudo apt install -y curl wget git build-essential

# Install Go
curl -L https://golang.org/dl/go1.21.0.linux-amd64.tar.gz | sudo tar -C /usr/local -xz
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
source ~/.bashrc

# Install Python dependencies
sudo apt install -y python3 python3-pip python3-venv

# Install Node.js (for MCP servers)
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# 3. Build Go tools
cd etcdBackup && go build -o etcdBackup . && cd ..
cd pullSecretUser && go build -o auditPullSecrets . && cd ..
cd serviceAccount_Secrets && go build -o get_svc_account_from_secrets . && cd ..
cd watchResource && go build . && cd ..

# 4. Setup Python environment
cd openshift-related/replace_control_plane
python3 -m venv venv
source venv/bin/activate
pip install -e .[dev]
make test  # Run tests to verify installation
cd ../..

# 5. Configure MCP servers (optional)
cp mcp-server/start-mcp-server.sh /usr/local/bin/
chmod +x /usr/local/bin/start-mcp-server.sh
# Follow MCP_SERVER_CONFIGURATION_GUIDE.md for complete setup
```

## 🧪 Development

### Development Setup

```bash
# Clone and setup development environment
git clone https://github.com/stratus-ss/k8s-tools.git
cd k8s-tools

# Setup Go development
go mod tidy

# Setup Python development
cd openshift-related/replace_control_plane
python3 -m venv venv
source venv/bin/activate
pip install -e .[dev]

# Run tests
pytest tests/ --cov=modules --cov-report=html  # Python tests
go test ./...                                   # Go tests
```

### Code Quality Standards

- **Go**: `gofmt`, `golint`, `go vet`
- **Python**: `black`, `flake8`, `mypy` (120 character line length)
- **Shell**: `shellcheck` for bash scripts
- **Documentation**: Comprehensive docstrings and README updates

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

### Types of Contributions
- 🐛 **Bug Reports** - Issue reproduction steps and environment details
- 💡 **Feature Requests** - Enhancement proposals with use cases
- 📖 **Documentation** - Improvements to guides and examples
- 🔧 **Code Contributions** - New features, bug fixes, optimizations

### Development Standards
- All code must pass existing tests and linting
- New features require tests and documentation
- Follow existing code style and patterns
- Include comprehensive commit messages

## 📄 License

This project is licensed under the **GPL-3.0 License** - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **OpenShift/Red Hat** - Enterprise Kubernetes platform and documentation
- **Kubernetes Community** - Container orchestration and ecosystem
- **Metal³ Project** - Bare metal provisioning framework
- **ETCD Community** - Distributed key-value store
- **Contributors** - All developers who have improved these tools

## 📚 Additional Resources

### Documentation Links
- [OpenShift Documentation](https://docs.openshift.com/) - Official OpenShift guides
- [Kubernetes Documentation](https://kubernetes.io/docs/) - Official Kubernetes documentation
- [ETCD Documentation](https://etcd.io/docs/) - ETCD administration guides
- [Metal³ Documentation](https://metal3.io/) - Bare metal provisioning

### Related Projects
- [kubernetes-mcp-server](https://github.com/containers/kubernetes-mcp-server) - MCP integration
- [cursor-buddy-mcp](https://github.com/omar-haris/cursor-buddy-mcp) - Project management
- [Seldon Core](https://github.com/SeldonIO/seldon-core) - ML deployment platform

---

**Repository**: [github.com/stratus-ss/k8s-tools](https://github.com/stratus-ss/k8s-tools)  
**Maintained by**: stratus  
**Last Updated**: December 2024
