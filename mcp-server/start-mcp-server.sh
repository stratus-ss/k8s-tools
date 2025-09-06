#!/bin/bash
# Kubernetes MCP Server Startup Script
# Designed for rhel8-k8s.stratus.lab cluster

set -euo pipefail

# Configuration
MCP_SERVER_PORT=3001
LOG_LEVEL=4
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level=$1
    shift
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    case $level in
        INFO)  echo -e "${GREEN}[INFO]${NC} ${timestamp} $*" ;;
        WARN)  echo -e "${YELLOW}[WARN]${NC} ${timestamp} $*" ;;
        ERROR) echo -e "${RED}[ERROR]${NC} ${timestamp} $*" ;;
        DEBUG) echo -e "${BLUE}[DEBUG]${NC} ${timestamp} $*" ;;
    esac
}

# Check prerequisites
check_prerequisites() {
    log INFO "Checking prerequisites..."
    
    # Check if kubeconfig exists
    if [[ ! -f "$KUBECONFIG_PATH" ]]; then
        log ERROR "Kubeconfig not found at $KUBECONFIG_PATH"
        log INFO "Please ensure kubectl is configured or set KUBECONFIG environment variable"
        exit 1
    fi
    
    # Check kubectl connectivity
    if ! kubectl cluster-info &>/dev/null; then
        log ERROR "Cannot connect to Kubernetes cluster"
        log INFO "Please check your kubeconfig and cluster connectivity"
        exit 1
    fi
    
    # Check if port is available
    if netstat -tuln | grep -q ":$MCP_SERVER_PORT "; then
        log ERROR "Port $MCP_SERVER_PORT is already in use"
        exit 1
    fi
    
    log INFO "Prerequisites check passed"
}

# Install MCP server if not present
install_mcp_server() {
    local install_method="${1:-npx}"
    
    case $install_method in
        npx)
            if command -v npx &> /dev/null; then
                log INFO "Using npx installation method"
                MCP_COMMAND="npx kubernetes-mcp-server@latest"
            else
                log ERROR "npx not found. Please install Node.js or use another installation method"
                exit 1
            fi
            ;;
        uvx)
            if command -v uvx &> /dev/null; then
                log INFO "Using uvx installation method"
                MCP_COMMAND="uvx kubernetes-mcp-server@latest"
            else
                log ERROR "uvx not found. Please install uv or use another installation method"
                exit 1
            fi
            ;;
        binary)
            local binary_path="$SCRIPT_DIR/kubernetes-mcp-server"
            if [[ -f "$binary_path" ]]; then
                log INFO "Using binary installation method"
                MCP_COMMAND="$binary_path"
            else
                log ERROR "Binary not found at $binary_path"
                log INFO "Please download the binary from https://github.com/containers/kubernetes-mcp-server/releases"
                exit 1
            fi
            ;;
        *)
            log ERROR "Unknown installation method: $install_method"
            log INFO "Supported methods: npx, uvx, binary"
            exit 1
            ;;
    esac
}

# Start MCP server
start_server() {
    local mode="${1:-normal}"
    
    log INFO "Starting Kubernetes MCP Server..."
    log INFO "Port: $MCP_SERVER_PORT"
    log INFO "Log Level: $LOG_LEVEL"
    log INFO "Kubeconfig: $KUBECONFIG_PATH"
    log INFO "Mode: $mode"
    
    # Build command arguments
    local args=(
        "--port" "$MCP_SERVER_PORT"
        "--log-level" "$LOG_LEVEL"
        "--kubeconfig" "$KUBECONFIG_PATH"
        "--list-output" "table"
    )
    
    # Add mode-specific arguments
    case $mode in
        readonly)
            args+=("--read-only")
            log INFO "Running in READ-ONLY mode"
            ;;
        safe)
            args+=("--disable-destructive")
            log INFO "Running in SAFE mode (destructive operations disabled)"
            ;;
        normal)
            log INFO "Running in NORMAL mode (full access)"
            ;;
        *)
            log ERROR "Unknown mode: $mode"
            log INFO "Supported modes: normal, readonly, safe"
            exit 1
            ;;
    esac
    
    log INFO "Starting server with command: $MCP_COMMAND ${args[*]}"
    log INFO "MCP endpoints will be available at:"
    log INFO "  - HTTP: http://localhost:$MCP_SERVER_PORT/mcp"
    log INFO "  - SSE:  http://localhost:$MCP_SERVER_PORT/sse"
    
    # Start the server
    exec $MCP_COMMAND "${args[@]}"
}

# Main function
main() {
    local install_method="${1:-npx}"
    local mode="${2:-normal}"
    
    log INFO "Kubernetes MCP Server Startup"
    log INFO "Cluster: rhel8-k8s.stratus.lab"
    
    check_prerequisites
    install_mcp_server "$install_method"
    start_server "$mode"
}

# Help function
show_help() {
    cat << EOF
Kubernetes MCP Server Startup Script

Usage: $0 [INSTALL_METHOD] [MODE]

INSTALL_METHOD:
  npx     - Use npx (requires Node.js) [default]
  uvx     - Use uvx (requires Python/uv)
  binary  - Use downloaded binary

MODE:
  normal    - Full access to cluster [default]
  readonly  - Read-only access only
  safe      - Disable destructive operations

Environment Variables:
  KUBECONFIG     - Path to kubeconfig file (default: ~/.kube/config)
  MCP_PORT       - MCP server port (default: 3001)
  MCP_LOG_LEVEL  - Logging level 0-9 (default: 4)

Examples:
  $0                    # Start with npx in normal mode
  $0 uvx readonly       # Start with uvx in read-only mode
  $0 binary safe        # Start with binary in safe mode

EOF
}

# Parse command line arguments
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    show_help
    exit 0
fi

# Override defaults from environment
MCP_SERVER_PORT="${MCP_PORT:-$MCP_SERVER_PORT}"
LOG_LEVEL="${MCP_LOG_LEVEL:-$LOG_LEVEL}"

# Run main function
main "${1:-npx}" "${2:-normal}"
