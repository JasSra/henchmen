# Interactive Workflow Guidance System

## Overview

DeployBot now features an **AI-powered interactive workflow guidance system** that makes complex DevOps tasks simple and approachable. Users are guided step-by-step through workflows with conversational AI, smart input prompts, and visual progress tracking.

## ✨ Key Features

### 1. **Conversational Workflow Triggers**
Users can start workflows naturally in the chat:
- "Help me register a new agent"
- "I want to deploy an application"
- "Fix this failed deployment"
- "Run a health check"

The AI recognizes intent and launches the appropriate workflow automatically.

### 2. **Beautiful Workflow Cards**
When users type "show workflows" or open the chat for the first time, they see visually stunning gradient cards for each workflow:

- 🚀 **Register New Agent** (Purple gradient)
- 📦 **Deploy Application** (Pink gradient)  
- 🔧 **Troubleshoot Failure** (Blue gradient)
- 💊 **System Health Check** (Green gradient)

Each card shows:
- Icon and title
- Description of what the workflow does
- Number of guided steps
- "Start →" button

### 3. **Interactive Input Types**
Workflows can request different types of input from users:

| Input Type | Description | Example |
|------------|-------------|---------|
| `text` | Free-form text | Repository name |
| `choice` | Select from options | Environment: production/staging/dev |
| `number` | Numeric value | Port number |
| `hostname` | Valid hostname | web-server-01 |
| `date` | Date value | 2025-10-15 |
| `secret` | Sensitive data | API key (masked) |
| `email` | Email address | user@example.com |
| `url` | Valid URL | https://example.com |

### 4. **Smart AI Guidance**
The AI assistant:
- **Understands context**: Knows which workflow is active and what step you're on
- **Asks for inputs**: "What's the hostname of the server you want to add?"
- **Presents choices**: "What environment will this agent serve? (production/staging/development/qa)"
- **Requests approvals**: "Ready to test the connection? This will verify the agent can reach the controller."
- **Tracks progress**: "Step 3/6: Checking connectivity..."
- **Celebrates success**: "✅ Agent registered successfully!"

### 5. **Visual Progress Tracking**
- Progress bars show completion percentage
- Step-by-step checklist with status indicators:
  - ⏳ Pending
  - ▶️ In Progress (animated)
  - ✅ Completed
  - ❌ Failed
  - ⏭️ Skipped

### 6. **Context-Aware Suggestions**
The AI provides smart suggestions based on:
- Current workflow state
- Available next actions
- User's conversation history

Examples:
- Active workflow: "✅ Yes, proceed" | "❌ No, cancel"
- Choice input: Shows the actual choices as buttons
- No workflow: "🚀 Register a new agent" | "📦 Deploy an application"

## 📋 Enhanced Workflows

### Register Agent Workflow (6 steps)
1. **Get Hostname** (Input: hostname)
   - Prompt: "What's the hostname of the server you want to add?"
   - Validation: Alphanumeric, hyphens, dots only

2. **Validate Hostname** (Automatic)
   - Checks format and duplicates

3. **Select Environment** (Input: choice)
   - Options: production, staging, development, qa

4. **Check Connectivity** (Approval Required)
   - Tests connection to controller

5. **Register Agent** (Approval Required)
   - Adds agent to database

6. **Configure Agent** (Automatic)
   - Sets up environment and verifies installation

### Deploy Application Workflow (6 steps)
1. **Get Repository** (Input: text)
   - Prompt: "What repository would you like to deploy?"
   
2. **Get Git Reference** (Input: text)
   - Prompt: "Which branch, tag, or commit?"

3. **Select Agent** (Input: choice)
   - Lists available agents to choose from

4. **Validate Repository** (Automatic)
   - Verifies repo exists and ref is valid

5. **Create Deployment Job** (Approval Required)
   - Queues the deployment

6. **Monitor Deployment** (Automatic)
   - Watches progress and reports status

### Troubleshoot Failure Workflow (4 steps)
1. **Identify Issue** - AI analyzes recent failures
2. **Gather Logs** - Collects diagnostic information
3. **Suggest Fix** - AI recommends remediation
4. **Apply Fix** (Approval) - Implements solution

### System Health Check Workflow (3 steps)
1. **Check Agents** - Verifies all agents are healthy
2. **Check Services** - Tests connectivity and resources
3. **Generate Report** - Creates summary with recommendations

## 🎨 User Experience Flow

### Example: Registering a New Agent

**User opens chat** → Sees welcome message + workflow cards

**User clicks "Register New Agent" card** or types "help me register an agent"

```
AI: "I can help you register a new agent! 🚀 I'll guide you through a 
     6-step process to safely onboard your server.
     
     Step 1/6: Get Hostname
     What's the hostname of the server you want to add?"
```

**User:** "web-server-01"

```
AI: "Great! Starting the agent registration workflow for web-server-01.
     
     Step 2/6: Validating hostname... ✅
     The hostname looks good and isn't already registered.
     
     Step 3/6: Select Environment
     What environment will this agent serve?
     • production
     • staging  
     • development
     • qa"
```

**User clicks:** "production" (or types it)

```
AI: "Perfect! This will be a production agent.
     
     Step 4/6: Checking connectivity...
     Ready to test the connection? This will verify the agent can reach 
     the controller."
```

**User:** "Yes" (or clicks ✅ Yes, proceed)

```
AI: "Testing connection to web-server-01... ✅ Connected successfully!
     
     Step 5/6: Register Agent
     Ready to add web-server-01 to the database?"
```

**User:** "Yes"

```
AI: "Registering agent... ✅ Agent registered!
     
     Step 6/6: Configuring agent...
     Setting up environment... ✅ Configuration complete!
     
     🎉 Success! Agent web-server-01 is now registered and ready to 
     receive deployments."
```

## 🔧 Technical Implementation

### Backend (Python)

#### Enhanced WorkflowStep Model
```python
class WorkflowStep(BaseModel):
    id: str
    title: str
    description: str
    status: str = "pending"
    prompt: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    requires_approval: bool = False
    validation_fn: Optional[str] = None
    
    # NEW: Interactive input handling
    requires_input: bool = False
    input_type: Optional[str] = None  # choice, text, number, etc.
    input_label: Optional[str] = None
    input_choices: Optional[List[str]] = None
    input_validation: Optional[str] = None
    input_placeholder: Optional[str] = None
    user_input: Optional[str] = None
```

#### AI System Prompt Enhancement
The system prompt now includes:
- Workflow guidance instructions
- Input type handling rules
- Communication style guidelines
- Step-by-step navigation patterns
- **Active workflow context injection**

When a workflow is running, the AI receives:
```python
**ACTIVE WORKFLOWS IN THIS SESSION:**
- register_agent (ID: abc123)
  Status: running
  Progress: Step 3/6
  Current: Select Environment - Choose the environment type
  📝 Needs input (choice): What environment will this agent serve?
  Options: production, staging, development, qa
```

### Frontend (JavaScript + CSS)

#### Workflow Cards
Gradient cards with:
- Custom color schemes per workflow type
- Hover animations (lift effect)
- Click handlers to start workflows
- Responsive grid layout

#### Enhanced Chat Messages
- HTML rendering for formatted content
- Bold text with `**text**`
- Emoji enlargement
- Line break support

#### Special Commands
- "show workflows" - Displays workflow cards
- "workflows" - Same as above
- Auto-show on first chat open

## 📊 Suggested Actions Algorithm

The AI generates contextual suggestions based on:

1. **Active Workflow State** (highest priority)
   - If step requires approval: Show "✅ Yes, proceed" / "❌ No, cancel"
   - If step needs choice input: Show the actual choices
   - Otherwise: Show workflow-specific actions

2. **User Intent Keywords**
   - "agent" mentions → Show "🚀 Register a new agent"
   - "deploy" mentions → Show "📦 Deploy an application"
   - "fail/error" mentions → Show "🔧 Troubleshoot failures"
   - "help" mentions → Show all workflows

3. **Context-Based Defaults**
   - Agent context: Stats, jobs, failures
   - Job context: Running jobs, failures, history
   - Metrics context: Health, 24h view, success rate
   - Error context: Logs, failed jobs, connectivity

4. **Fallback Suggestions**
   - 🚀 Register a new agent
   - 📦 Deploy an application
   - Show all agents
   - List recent jobs

## 🚀 Getting Started

### For Users

1. **Open the AI chat** (💬 icon in bottom-right)
2. **See workflow cards** automatically
3. **Click a card** or type naturally:
   - "I need to add a server"
   - "Deploy my app"
   - "Something is broken"
4. **Follow the AI's guidance** - it will ask you questions step-by-step
5. **Provide inputs** when requested
6. **Approve critical steps** when asked
7. **Watch progress** in the chat and sidebar

### For Developers

#### Adding a New Workflow

1. **Define workflow steps** in `ai_assistant.py`:
```python
"my_workflow": [
    WorkflowStep(
        id="get_input",
        title="Get User Input",
        description="Request information from user",
        requires_input=True,
        input_type="text",
        input_label="What's your input?",
        input_placeholder="Enter value here"
    ),
    WorkflowStep(
        id="process",
        title="Process Data",
        description="Do something with the input",
        prompt="Process the user's input: {user_input}",
        requires_approval=True
    )
]
```

2. **Add workflow card** to `index_ai.html`:
```javascript
{
    name: 'my_workflow',
    icon: '⚡',
    title: 'My Workflow',
    description: 'Does something awesome',
    steps: 2,
    className: 'my-custom-gradient'
}
```

3. **Add CSS gradient** (optional):
```css
.workflow-card.my-custom-gradient {
    background: linear-gradient(135deg, #ff6b6b 0%, #feca57 100%);
}
```

## 📈 Future Enhancements

- [ ] Custom workflow builder UI
- [ ] Workflow templates library
- [ ] Parallel steps execution
- [ ] Conditional branching
- [ ] Workflow scheduling
- [ ] Rollback support
- [ ] History and analytics
- [ ] Shareable workflow links
- [ ] Workflow versioning
- [ ] Multi-user collaboration

## 🎯 Best Practices

### For Workflow Design
1. **Keep steps focused** - One clear action per step
2. **Add approval gates** before destructive actions
3. **Provide helpful prompts** - Explain what will happen
4. **Use appropriate input types** - Match the data you need
5. **Validate inputs** - Use regex or custom validation
6. **Give feedback** - Show progress and results

### For User Communication
1. **Be conversational** - Sound human, not robotic
2. **Explain context** - Why are we doing this step?
3. **Show progress** - How many steps remain?
4. **Celebrate wins** - Acknowledge success!
5. **Handle errors gracefully** - Offer solutions, not just errors

## 🆘 Troubleshooting

### Workflows not showing in chat
- Refresh the page
- Check browser console for errors
- Verify `/v1/ai/workflows/definitions` endpoint

### AI not recognizing workflow intent
- Be more explicit: "start register agent workflow"
- Or use the workflow cards directly

### Input not being captured
- Check WorkflowStep has `requires_input=True`
- Verify `input_type` is set
- Ensure `input_label` is user-friendly

## 📝 Summary

The interactive workflow guidance system transforms complex DevOps tasks into simple, conversational experiences. Users are guided step-by-step with:
- ✅ Natural language interaction
- ✅ Beautiful visual presentation
- ✅ Smart context awareness
- ✅ Interactive input handling
- ✅ Progress tracking
- ✅ Contextual suggestions

**Result:** DevOps tasks are now as easy as having a conversation! 🚀
