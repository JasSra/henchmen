#!/usr/bin/env python3
"""
Example: Deploying with .NET Agent vs SSH

This script demonstrates both deployment modes:
1. Agent-based deployment (with .NET agent)
2. Agentless SSH-based deployment
"""
import asyncio
import os
from app.ssh_connector import SSHConnector, SSHCredentials


async def example_ssh_deployment():
    """
    Example: Deploy using SSH without an agent
    """
    print("=" * 60)
    print("SSH-Based Agentless Deployment Example")
    print("=" * 60)
    
    # Configure SSH credentials
    # In production, load from secure config/vault
    credentials = SSHCredentials(
        hostname=os.getenv("TARGET_HOST", "example.com"),
        port=int(os.getenv("SSH_PORT", "22")),
        username=os.getenv("SSH_USER", "deploybot"),
        private_key=os.getenv("SSH_KEY_PATH", "~/.ssh/deploybot_key")
    )
    
    print(f"\n1. Connecting to {credentials.hostname}...")
    
    # Create SSH connector
    connector = SSHConnector(credentials)
    
    # Connect to host
    connected = await connector.connect()
    if not connected:
        print("✗ Failed to connect via SSH")
        return
    
    print("✓ Connected successfully")
    
    try:
        # Check Docker is available
        print("\n2. Checking Docker availability...")
        docker_available = await connector.check_docker_installed()
        
        if not docker_available:
            print("✗ Docker not available on target host")
            return
        
        print("✓ Docker is available")
        
        # Get current containers
        print("\n3. Listing current containers...")
        containers = await connector.get_docker_containers()
        print(f"   Found {len(containers)} running containers")
        for container in containers:
            print(f"   - {container['name']}: {container['status']}")
        
        # Get system metrics
        print("\n4. Fetching system metrics...")
        metrics = await connector.get_system_metrics()
        print(f"   CPU: {metrics.get('cpu_percent', 'N/A')}%")
        print(f"   Memory: {metrics.get('memory_percent', 'N/A')}%")
        print(f"   Disk Free: {metrics.get('disk_free', 'N/A')}")
        
        # Example: Clone a repository
        print("\n5. Cloning repository (example)...")
        repo_url = "https://github.com/example/demo-app.git"
        print(f"   Repository: {repo_url}")
        print("   (Skipping actual clone in example)")
        
        # Example deployment would look like:
        # result = await connector.execute_deployment(
        #     repo_url=repo_url,
        #     ref="main",
        #     container_name="demo-app"
        # )
        
        print("\n✓ SSH deployment example completed successfully")
        
    finally:
        # Always disconnect
        await connector.disconnect()
        print("\n6. Disconnected from host")


async def example_agent_deployment():
    """
    Example: Deploy using .NET Agent
    
    Note: This requires a running .NET agent on the target server.
    The agent polls the controller for jobs and executes them locally.
    """
    print("\n" + "=" * 60)
    print("Agent-Based Deployment Example")
    print("=" * 60)
    
    # In agent-based mode:
    # 1. .NET agent runs on target server
    # 2. Agent registers with controller: POST /v1/agents/register
    # 3. Agent sends heartbeat: POST /v1/agents/{id}/heartbeat
    # 4. Controller creates job: POST /v1/jobs
    # 5. Agent receives job on next heartbeat
    # 6. Agent executes job locally
    # 7. Agent reports completion (future)
    
    print("\n.NET Agent workflow:")
    print("1. ✓ Agent installed on target server")
    print("2. ✓ Agent registers with controller")
    print("   - Hostname: web-01")
    print("   - Capabilities: dotnet, docker")
    print("3. ✓ Agent polls controller every 5 seconds")
    print("4. → Controller creates deployment job")
    print("5. ✓ Agent receives job on heartbeat")
    print("6. ✓ Agent executes deployment locally")
    print("   - Clone repository")
    print("   - Build Docker image")
    print("   - Deploy container")
    print("7. ✓ Deployment complete")
    
    print("\nAgent advantages:")
    print("  • Real-time job execution")
    print("  • Better performance for frequent deployments")
    print("  • Direct access to local Docker daemon")
    print("  • Persistent connection to controller")


def print_comparison():
    """Print comparison between deployment modes"""
    print("\n" + "=" * 60)
    print("Deployment Mode Comparison")
    print("=" * 60)
    
    print("\n┌─────────────────┬─────────────────┬─────────────────┐")
    print("│ Feature         │ Agent-Based     │ SSH-Based       │")
    print("├─────────────────┼─────────────────┼─────────────────┤")
    print("│ Installation    │ Required        │ Not Required    │")
    print("│ Latency         │ Low             │ Medium          │")
    print("│ Infrastructure  │ Complex         │ Simple          │")
    print("│ Maintenance     │ Agents to manage│ SSH keys only   │")
    print("│ Best For        │ Production      │ Ad-hoc/Dev      │")
    print("│ Security        │ Cert-based      │ SSH keys        │")
    print("└─────────────────┴─────────────────┴─────────────────┘")


def print_usage():
    """Print usage instructions"""
    print("\n" + "=" * 60)
    print("Usage Instructions")
    print("=" * 60)
    
    print("\nFor SSH deployment:")
    print("  1. Set environment variables:")
    print("     export TARGET_HOST=your-server.com")
    print("     export SSH_USER=deploybot")
    print("     export SSH_KEY_PATH=~/.ssh/deploybot_key")
    print("  2. Run: python examples/deployment_example.py ssh")
    
    print("\nFor agent deployment:")
    print("  1. Install .NET agent on target server:")
    print("     make build-dotnet-agent")
    print("     # Copy to server and start")
    print("  2. Run: python examples/deployment_example.py agent")
    
    print("\nFor API deployment:")
    print("  # SSH-based")
    print("  curl -X POST http://localhost:8080/v1/deploy/ssh \\")
    print("    -H 'Content-Type: application/json' \\")
    print("    -d '{...}'")
    
    print("\n  # Agent-based")
    print("  curl -X POST http://localhost:8080/v1/jobs \\")
    print("    -H 'Content-Type: application/json' \\")
    print("    -d '{\"repo\": \"myorg/app\", \"ref\": \"main\", \"host\": \"web-01\"}'")


async def main():
    """Main entry point"""
    import sys
    
    print("\nDeployBot Deployment Modes Example")
    print("=" * 60)
    
    mode = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    if mode == "ssh":
        await example_ssh_deployment()
    elif mode == "agent":
        await example_agent_deployment()
    elif mode == "compare":
        print_comparison()
    else:
        print_usage()
        print_comparison()
        print("\nNote: This is a demonstration script.")
        print("For actual deployments, use the API endpoints or AI assistant.")


if __name__ == "__main__":
    asyncio.run(main())
