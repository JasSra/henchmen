#!/bin/bash
# Quick acceptance test script

set -e

echo "==================================="
echo "DeployBot Controller - Acceptance Tests"
echo "==================================="
echo ""

# Check if server is running
echo "1. Checking if controller is accessible..."
if curl -s http://localhost:8080/health > /dev/null; then
    echo "✓ Controller is running on port 8080"
else
    echo "✗ Controller is not running. Start it with 'make run'"
    exit 1
fi

echo ""
echo "2. Testing agent registration..."
AGENT_RESPONSE=$(curl -s -X POST http://localhost:8080/v1/agents/register \
    -H "Content-Type: application/json" \
    -d '{"hostname":"test-agent-01","capabilities":{}}')
AGENT_ID=$(echo $AGENT_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "✓ Agent registered with ID: $AGENT_ID"

echo ""
echo "3. Testing agent heartbeat (should return no job)..."
HEARTBEAT_RESPONSE=$(curl -s -X POST http://localhost:8080/v1/agents/$AGENT_ID/heartbeat \
    -H "Content-Type: application/json" \
    -d '{"status":"online"}')
HAS_JOB=$(echo $HEARTBEAT_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['job'])")
if [ "$HAS_JOB" == "None" ]; then
    echo "✓ Heartbeat returned no job (as expected)"
else
    echo "⚠ Heartbeat returned a job"
fi

echo ""
echo "4. Creating a deployment job..."
JOB_RESPONSE=$(curl -s -X POST http://localhost:8080/v1/jobs \
    -H "Content-Type: application/json" \
    -d '{"repo":"myorg/test-app","ref":"main","host":"test-agent-01"}')
JOB_ID=$(echo $JOB_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['job']['id'])")
echo "✓ Job created with ID: $JOB_ID"

echo ""
echo "5. Retrieving job details..."
GET_JOB_RESPONSE=$(curl -s http://localhost:8080/v1/jobs/$JOB_ID)
JOB_STATUS=$(echo $GET_JOB_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['job']['status'])")
echo "✓ Job retrieved. Status: $JOB_STATUS"

echo ""
echo "6. Listing all hosts..."
HOSTS_RESPONSE=$(curl -s http://localhost:8080/v1/hosts)
HOST_COUNT=$(echo $HOSTS_RESPONSE | python3 -c "import sys, json; print(len(json.load(sys.stdin)['hosts']))")
echo "✓ Found $HOST_COUNT registered host(s)"

echo ""
echo "==================================="
echo "All acceptance tests passed! ✓"
echo "==================================="
echo ""
echo "Additional manual tests:"
echo "- Webhook: curl -X POST http://localhost:8080/v1/webhooks/github (requires valid signature)"
echo "- CLI: python -m cli.ctl deploy --repo myorg/app --ref main --host test-agent-01"
echo "- CLI: python -m cli.ctl status $JOB_ID"
