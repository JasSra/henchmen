# Multi-Step Workflows Guide

## Overview

DeployBot Controller now features an intelligent workflow system that guides you through complex operations step-by-step. Each workflow validates inputs, checks prerequisites, and provides approval points for critical actions.

## Features

### ✅ Smart Step Execution
- **Sequential Processing**: Steps execute in order with context passing
- **Validation**: Each step validates before proceeding
- **Approval Points**: Critical steps require manual approval
- **Error Handling**: Failed steps stop workflow with clear error messages
- **Context Chaining**: Results from previous steps inform next steps

### 📊 Visual Progress Tracking
- **OpenAI-Style Sidebar**: Shows all workflow steps with status
- **Real-time Updates**: Steps update automatically as they execute
- **Status Indicators**: Pending (○), In-Progress (◐), Completed (✓), Failed (✗)
- **Color Coding**: Visual feedback for each step state
- **Progress Percentage**: Track overall completion

### 🤖 AI-Powered Intelligence
- **Smart Prompts**: AI determines best approach for each step
- **Function Calling**: Automatically uses available tools
- **Adaptive Logic**: Adjusts based on previous step results
- **Natural Language**: Understands context and requirements

## Available Workflows

### 1. Register New Agent
**Purpose**: Safely onboard a new deployment agent with full validation

**Steps**:
1. **Validate Hostname**: Check format and uniqueness
2. **Check Connectivity**: Verify agent can reach controller (requires approval)
3. **Register**: Add agent to database (requires approval)
4. **Configure**: Set up environment and verify installation

**Required Context**:
- `hostname`: Agent hostname (prompted at start)

**Use Case**: Adding a new server to your deployment fleet

---

### 2. Deploy Application
**Purpose**: Deploy an application with comprehensive pre-flight checks

**Steps**:
1. **Select Target Agent**: AI chooses best agent (requires approval)
2. **Validate Repository**: Check repo exists and ref is valid
3. **Create Deployment Job**: Queue the job (requires approval)
4. **Monitor Deployment**: Watch progress and report status

**Required Context**:
- `repository`: Repository name (e.g., `myorg/app`)
- `ref`: Git reference (branch, tag, or commit SHA)

**Use Case**: Production deployments that need validation before execution

---

### 3. Troubleshoot Failure
**Purpose**: Systematically diagnose and fix deployment issues

**Steps**:
1. **Identify Issue**: Analyze failures and find root cause
2. **Gather Logs**: Collect diagnostic information
3. **Suggest Fix**: Recommend specific remediation (requires approval)
4. **Verify Fix**: Confirm issue is resolved

**Required Context**: None (analyzes recent failures automatically)

**Use Case**: When deployments fail and you need guided troubleshooting

---

### 4. System Health Check
**Purpose**: Comprehensive system assessment with recommendations

**Steps**:
1. **Check All Agents**: Verify connectivity and status
2. **Check Running Jobs**: Review active deployments
3. **Analyze Metrics**: Examine success rates and patterns
4. **Generate Report**: Create actionable health summary

**Required Context**: None

**Use Case**: Regular health monitoring or pre-deployment checks

## How to Use

### Starting a Workflow

#### Method 1: UI Sidebar
1. Click workflow selector in sidebar (right side)
2. Choose workflow from dropdown
3. Click "Start Workflow"
4. Provide required context when prompted

#### Method 2: AI Chat
Ask the AI assistant naturally:
```
"I want to register a new agent called prod-server-03"
"Deploy myapp/frontend to production"
"Help me troubleshoot the recent failures"
"Run a system health check"
```

### During Workflow Execution

**Approval Steps**:
- Green checkmark appears for steps requiring approval
- Review the step results in chat
- Click "✓ Approve" to continue or "✗ Reject" to cancel

**Automatic Steps**:
- Execute without intervention
- Results appear in chat
- Progress shown in sidebar

**Monitoring**:
- Sidebar shows real-time progress
- Each step's status updates automatically
- Chat shows detailed messages from AI

### Canceling a Workflow

Click "Cancel Workflow" button in sidebar at any time

## Workflow Architecture

### Context Accumulation
Each step receives:
- All previous step results
- User-provided context
- Current system state

Example:
```
Step 1: Selects best agent → stores agent_id in context
Step 2: Uses agent_id from context to create job
Step 3: Uses job_id to monitor deployment
```

### Prompt Engineering
The system automatically:
- Builds context-aware prompts for each step
- Passes results between steps
- Formats data for AI consumption
- Extracts structured results

### Validation & Branching
Steps can:
- Validate inputs before execution
- Skip steps based on conditions
- Fail gracefully with clear messages
- Resume from checkpoints (future)

## API Endpoints

### Start Workflow
```bash
POST /v1/ai/workflows/start?workflow_name=register_agent
Content-Type: application/json

{
  "hostname": "prod-server-03"
}
```

### Approve/Reject Step
```bash
POST /v1/ai/workflows/{workflow_id}/approve
Content-Type: application/json

{
  "approved": true,
  "user_input": "optional input"
}
```

### Get Status
```bash
GET /v1/ai/workflows/{workflow_id}
```

### Cancel Workflow
```bash
POST /v1/ai/workflows/{workflow_id}/cancel
```

### List Active Workflows
```bash
GET /v1/ai/workflows
```

### List Definitions
```bash
GET /v1/ai/workflows/definitions
```

## Examples

### Example 1: Register Agent
```
User: "I want to add a new server called staging-01"

AI: Starting workflow...
Step 1/4: Validating hostname 'staging-01'
✓ Hostname is valid and not in use

Step 2/4: Checking connectivity
Attempting to reach staging-01:8080...
[APPROVAL NEEDED] - Ready to register?

User: [Clicks Approve]

Step 3/4: Registering agent
Agent staging-01 added successfully
[APPROVAL NEEDED] - Proceed with configuration?

User: [Clicks Approve]

Step 4/4: Configuring agent
Environment configured, installation verified
✅ Workflow complete! Agent staging-01 is ready.
```

### Example 2: Troubleshoot Failure
```
User: "Why did my last deployment fail?"

AI: Starting troubleshooting workflow...

Step 1/4: Analyzing recent failures
Found 3 failed jobs in last hour
Common issue: Connection timeout to prod-server-02

Step 2/4: Gathering logs
Collected logs from failed jobs
Network errors detected at 14:23 UTC

Step 3/4: Suggesting fix
Root cause: Agent prod-server-02 unreachable
Recommendation: Restart agent or update heartbeat
[APPROVAL NEEDED] - Apply this fix?

User: [Clicks Reject - will handle manually]

Workflow cancelled. Issue documented for manual resolution.
```

## Best Practices

### ✅ DO:
- Review approval steps carefully before approving
- Use workflows for production changes
- Let workflows complete naturally
- Check sidebar for step status

### ❌ DON'T:
- Approve steps without reading results
- Cancel workflows mid-execution unless necessary
- Start multiple conflicting workflows simultaneously

## Future Enhancements

Coming soon:
- **Workflow Templates**: Custom user-defined workflows
- **Scheduled Workflows**: Run on cron or events
- **Rollback Support**: Undo completed workflows
- **Parallel Steps**: Execute independent steps concurrently
- **Conditional Logic**: If/else branching in workflows
- **Workflow History**: Review past executions
- **Export/Import**: Share workflow definitions

## Troubleshooting

**Q: Workflow stuck on a step?**
A: Check if it requires approval. Look for the approve/reject buttons.

**Q: Workflow failed unexpectedly?**
A: Check AI assistant chat for error details. Workflows fail-safe.

**Q: Can't see workflow sidebar?**
A: Start a workflow from the selector or ask AI to start one.

**Q: How to modify a running workflow?**
A: You can only approve/reject or cancel. Modifications require restart.

## Technical Details

- **Engine**: `app/ai_assistant.py` - WorkflowState, WorkflowStep models
- **API**: `app/main.py` - RESTful workflow endpoints
- **UI**: `ui/index_ai.html` - Sidebar component with real-time updates
- **Storage**: In-memory (workflows lost on restart - DB persistence coming)
- **Polling**: 2-second interval for step updates
- **Context Limit**: 20 previous messages for AI context

---

**Last Updated**: October 6, 2025
**Version**: 1.0.0
