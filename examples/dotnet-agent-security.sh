#!/bin/bash
# Example: Running .NET Agent with Security Features

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  DeployBot .NET Agent - Security Configuration Examples       ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Basic Configuration (Development)
echo "1. Basic Configuration (Development/Testing)"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'
export CONTROLLER_URL=http://localhost:8080
export AGENT_HOSTNAME=$(hostname)
export HEARTBEAT_INTERVAL=5

# Run agent
dotnet run
EOF
echo ""

# Token-based Authentication
echo "2. Token-based Authentication (Recommended)"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'
export CONTROLLER_URL=https://controller.example.com:8080
export AGENT_HOSTNAME=$(hostname)
export AGENT_TOKEN=your-secret-token-here

# Token is sent as Bearer token in Authorization header
# Token is persisted in agent-state.json for reconnection
dotnet run
EOF
echo ""

# TLS with Custom CA
echo "3. TLS with Custom CA Certificate"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'
export CONTROLLER_URL=https://controller.example.com:8080
export AGENT_TOKEN=your-secret-token-here
export CA_CERT_FILE=/etc/deploybot/ca-cert.pem

# Agent validates controller certificate against custom CA
dotnet run
EOF
echo ""

# Mutual TLS (mTLS)
echo "4. Mutual TLS - Client Certificate Authentication"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'
export CONTROLLER_URL=https://controller.example.com:8080
export CLIENT_CERT_FILE=/etc/deploybot/client-cert.pem
export CLIENT_KEY_FILE=/etc/deploybot/client-key.pem
export CA_CERT_FILE=/etc/deploybot/ca-cert.pem

# Agent presents certificate to controller
# Controller validates agent certificate
# Highest security for production
dotnet run
EOF
echo ""

# Development Mode (Insecure)
echo "5. Development Mode - Skip Certificate Validation"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'
export CONTROLLER_URL=https://localhost:8080
export ALLOW_INSECURE=true
export AGENT_TOKEN=dev-token

# ⚠️ WARNING: Only for development/testing!
# Skips TLS certificate validation
dotnet run
EOF
echo ""

# Production Configuration
echo "6. Production Configuration (Full Security)"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'
export CONTROLLER_URL=https://controller.example.com:8080
export AGENT_HOSTNAME=prod-web-01
export AGENT_TOKEN=$(cat /etc/deploybot/token.secret)
export AGENT_WORK_DIR=/var/lib/deploybot/work
export AGENT_DATA_DIR=/var/lib/deploybot/data
export CLIENT_CERT_FILE=/etc/deploybot/certs/client-cert.pem
export CLIENT_KEY_FILE=/etc/deploybot/certs/client-key.pem
export CA_CERT_FILE=/etc/deploybot/certs/ca-cert.pem
export HEARTBEAT_INTERVAL=10

# Full security with mTLS and token auth
# Proper directories for production
dotnet /opt/deploybot/DeploybotAgent.dll
EOF
echo ""

# State Persistence Example
echo "7. State Persistence"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'
# Agent state is saved to: $AGENT_DATA_DIR/agent-state.json
# Example state file:
{
  "AgentId": "agent-12345",
  "AgentToken": "secret-token-xyz",
  "Hostname": "web-server-01",
  "RegisteredAt": "2024-01-15T10:30:00Z"
}

# Benefits:
# - Survives agent restarts
# - No re-registration needed
# - Token persisted securely
# - Easy inspection and backup
EOF
echo ""

# Health Metrics Example
echo "8. Health Metrics in Heartbeats"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'
# Metrics sent with every heartbeat:
{
  "status": "online",
  "metrics": {
    "cpu_percent": 45.2,
    "memory_mb": 512,
    "disk_free_gb": 128,
    "docker_containers": 5
  },
  "capabilities": [
    "deploy",
    "docker",
    "git",
    "dotnet"
  ]
}

# Controller can use metrics for:
# - Health monitoring
# - Load balancing
# - Capacity planning
# - Alerting
EOF
echo ""

# Certificate Generation Example
echo "9. Generate Self-Signed Certificates (Testing)"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat << 'EOF'
# Create CA certificate
openssl req -x509 -new -nodes -days 365 \
  -keyout ca-key.pem -out ca-cert.pem \
  -subj "/CN=DeployBot CA"

# Create client certificate
openssl genrsa -out client-key.pem 2048
openssl req -new -key client-key.pem -out client.csr \
  -subj "/CN=agent-client"
openssl x509 -req -in client.csr -CA ca-cert.pem \
  -CAkey ca-key.pem -CAcreateserial -out client-cert.pem -days 365

# Use in agent:
export CLIENT_CERT_FILE=./client-cert.pem
export CLIENT_KEY_FILE=./client-key.pem
export CA_CERT_FILE=./ca-cert.pem
EOF
echo ""

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Security Best Practices                                       ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "✓ Always use HTTPS in production"
echo "✓ Enable token authentication"
echo "✓ Use mutual TLS for highest security"
echo "✓ Store tokens in secure files with restricted permissions"
echo "✓ Rotate tokens periodically"
echo "✓ Monitor heartbeat metrics for anomalies"
echo "✓ Never use ALLOW_INSECURE=true in production"
echo "✓ Keep agent state directory secure (600/700 permissions)"
echo ""
