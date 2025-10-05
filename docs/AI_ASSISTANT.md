# DeployBot AI Assistant - Complete Guide

## 🤖 Overview

DeployBot Controller now includes an **AI-Powered Assistant** that enables you to:

- **Chat with natural language** - Ask questions and give commands in plain English
- **Use voice commands** - Speak your deployment commands
- **Get smart insights** - AI monitors your system and provides proactive alerts
- **Perform all 20+ common tasks** - Just by asking the AI assistant

## ✨ Features

### 1. Natural Language Chat Interface

**Ask questions like:**
- "Show me all active agents"
- "What deployments are running?"
- "Deploy myorg/web-app version v1.2.3 to web-01"
- "Show me recent failures"
- "Give me deployment stats for the last 24 hours"
- "Cancel job abc123"
- "Check the health of agent web-01"
- "What's the deployment history for myorg/api?"

The AI understands context and can handle follow-up questions.

### 2. Voice Commands 🎤

**Speak your commands:**
1. Click the microphone button
2. Speak your command
3. AI transcribes and executes

**Example voice commands:**
- "Deploy the web app to production"
- "Show me what's failing"
- "Check all agents"
- "Get stats"

### 3. Smart Monitoring & Insights

AI automatically analyzes your deployment system and provides insights:

**Health Monitoring:**
- Detects stale agents (not responding)
- Identifies high failure rates
- Warns about job queue buildups
- Celebrates successful deployments

**Proactive Alerts:**
- "⚠️ 3 agents haven't sent heartbeat in 30+ seconds"
- "❌ High failure rate: 5 deployments failed in the last hour"
- "✅ All agents healthy: 10 agents active and responding"
- "✅ High success rate: 95% in the last hour"

### 4. Quick Actions

One-click shortcuts for common tasks:
- 🤖 **Check Agents** - See all connected agents
- 📊 **Running Jobs** - View active deployments
- ⚠️ **Recent Failures** - Troubleshoot issues
- 📈 **24h Stats** - Get performance metrics

## 🚀 Quick Start

### 1. Configure OpenAI API Key

Create or update your `.env` file:

```bash
# Copy from example
cp .env.example .env

# Edit .env and add your OpenAI API key
OPENAI_API_KEY=sk-your-actual-api-key-here
AI_MODEL=gpt-4o-mini
AI_ENABLED=true
```

**Get an API key:**
- Go to https://platform.openai.com/api-keys
- Create a new API key
- Copy it to your `.env` file

### 2. Start the Controller

```bash
make run-ui
```

The AI assistant will automatically activate if a valid API key is provided.

### 3. Open the Dashboard

Navigate to http://localhost:8080

You'll see:
- ✨ **AI Assistant Active** badge in the header
- 🤖 **AI Assistant** floating button (bottom right)
- Quick action buttons for common tasks
- AI Insights panel (when issues are detected)

### 4. Chat with the AI

**Click the 🤖 floating button** to open the chat widget.

**Try these commands:**
```
"Show me all agents"
"Deploy myorg/app main to web-01"
"What's failing?"
"Give me stats for the last hour"
"Check if web-02 is healthy"
"Show deployment history for myorg/api"
```

## 📋 AI Capabilities - All 20+ Common Tasks

The AI assistant can perform these operations via function calling:

### Agent Management
1. **List all agents** - See connected deployment workers
2. **Check agent status** - Verify specific agent health
3. **Check agent health** - Analyze all agents for issues

### Deployment Operations
4. **Create deployment** - Deploy apps to servers
5. **List jobs** - View all deployment jobs
6. **Filter jobs by status** - Show pending/running/success/failed
7. **Filter jobs by host** - See deployments for specific server
8. **Get job details** - Detailed info about a deployment
9. **Cancel job** - Stop pending/running deployments

### Monitoring & Analytics
10. **Get deployment stats** - Success rates, totals, time windows
11. **Get recent failures** - Troubleshoot failed deployments
12. **Get deployment history** - Track deployments over time
13. **Check system health** - Overall system status

### Insights & Recommendations
14. **Identify stale agents** - Detect unresponsive workers
15. **Alert on high failure rates** - Warn when too many failures
16. **Detect queue buildups** - Identify bottlenecks
17. **Celebrate successes** - Positive feedback on high success rates
18. **Suggest troubleshooting** - Recommend fixes for issues
19. **Provide deployment best practices** - AI guidance
20. **Answer questions** - Explain how DeployBot works

## 🎤 Voice Commands

### Setup Microphone

The first time you use voice commands:
1. Browser will ask for microphone permission
2. Click "Allow"
3. Microphone icon will turn red when recording

### Using Voice Commands

1. **Click the 🎤 button** in the chat widget
2. **Speak clearly**: "Deploy web app to production server"
3. **Click again to stop** recording
4. AI transcribes and executes your command

### Best Practices

- Speak clearly and at normal pace
- Use full names: "web-zero-one" not "web 01"
- Be specific: "Deploy myorg/app branch main to web-01"
- Check transcription before confirming

## 🧠 Smart Insights

The AI monitors your system every 30 seconds and provides insights.

### Types of Insights

**⚠️ Warning**
- Stale agents detected
- Job queue buildup
- Potential issues

**❌ Error**
- High failure rates
- Critical problems
- Urgent attention needed

**✅ Success**
- All agents healthy
- High success rates
- System performing well

**ℹ️ Info**
- General information
- Helpful tips
- System updates

### Insight Examples

```
⚠️ Stale Agents Detected
3 agent(s) haven't sent heartbeat in 30+ seconds
💡 Check if agents are running: web-01, web-02, web-03

❌ High Failure Rate
5 deployments failed in the last hour
💡 Check recent error logs and agent connectivity

✅ All Agents Healthy
10 agent(s) active and responding

✅ High Success Rate
95.5% success rate in the last hour
```

## 💬 Example Conversations

### Deploy an Application

**You:** "Deploy myorg/web-app to web-01"

**AI:** "I'll deploy myorg/web-app (main branch) to web-01 for you."
- Creates deployment job
- Shows job ID
- Confirms status

### Check System Status

**You:** "How's everything looking?"

**AI:** "Let me check your system health..."
- Shows active agents
- Recent deployment stats
- Any warnings or issues

### Troubleshoot Failures

**You:** "Why are deployments failing?"

**AI:** "I found 3 recent failures. Let me analyze..."
- Lists failed jobs
- Identifies patterns
- Suggests fixes

### Get Deployment History

**You:** "Show me deployments for web-02 in the last 24 hours"

**AI:** "Here's the deployment history..."
- Lists all deployments
- Shows success/failure counts
- Provides statistics

## 🔧 API Endpoints

### Chat with AI
```bash
POST /v1/ai/chat
Content-Type: application/json

{
  "message": "Show me all agents",
  "history": [
    {"role": "user", "content": "previous message"},
    {"role": "assistant", "content": "previous response"}
  ]
}
```

**Response:**
```json
{
  "response": "Here are all your active agents...",
  "action_taken": "list_agents",
  "data": {
    "count": 5,
    "agents": [...]
  }
}
```

### Voice Command
```bash
POST /v1/ai/voice/upload
Content-Type: multipart/form-data

file: audio.wav (or .mp3, .m4a, .webm)
```

**Response:**
```json
{
  "transcription": "deploy web app to production",
  "response": "I'll deploy the web app to production...",
  "action_taken": "create_deployment",
  "data": {...}
}
```

### Get Insights
```bash
GET /v1/ai/insights
```

**Response:**
```json
[
  {
    "type": "warning",
    "title": "Stale Agents Detected",
    "message": "2 agent(s) haven't sent heartbeat...",
    "suggestion": "Check if agents are running: web-01, web-02",
    "timestamp": "2025-10-05T12:30:00Z"
  }
]
```

### Check AI Status
```bash
GET /v1/ai/status
```

**Response:**
```json
{
  "enabled": true,
  "model": "gpt-4o-mini",
  "features": {
    "chat": true,
    "voice": true,
    "insights": true
  }
}
```

## 🎨 UI Components

### AI Chat Widget
- **Location**: Bottom right corner
- **Open/Close**: Click the 🤖 floating button
- **Features**:
  - Chat history preserved during session
  - Voice input button
  - Send button or press Enter
  - Auto-scroll to latest message
  - Typing indicators

### Quick Action Buttons
- Pre-built queries for common tasks
- One-click access to frequent operations
- Updates main dashboard when executed

### AI Insights Panel
- Appears when issues detected
- Color-coded by severity
- Includes suggestions and recommendations
- Auto-refreshes every 30 seconds

## ⚙️ Configuration

### Environment Variables

```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-your-key-here     # Required
AI_MODEL=gpt-4o-mini                 # Model to use
AI_ENABLED=true                      # Enable/disable AI
```

### Supported Models

- `gpt-4o-mini` - **Recommended** (fast, affordable)
- `gpt-4o` - More capable, slower, more expensive
- `gpt-4-turbo` - Alternative
- `gpt-3.5-turbo` - Cheaper, less capable

### Cost Estimation

**gpt-4o-mini pricing (as of Oct 2025):**
- Input: $0.150 per 1M tokens
- Output: $0.600 per 1M tokens

**Typical usage:**
- Chat message: ~500-1000 tokens
- Voice transcription: $0.006 per minute
- ~100 interactions/day ≈ $0.10-0.50/day

## 🔒 Security Considerations

**API Key Protection:**
- Never commit `.env` to version control
- Use environment variables in production
- Rotate keys regularly

**Rate Limiting:**
- OpenAI enforces rate limits
- Consider caching responses
- Add request throttling for production

**Data Privacy:**
- Chat history stored in memory only
- No persistent storage of conversations
- Logs may contain deployment details

## 🐛 Troubleshooting

### AI Not Available

**Error:** "AI assistant not available"

**Solutions:**
1. Check `OPENAI_API_KEY` in `.env`
2. Verify API key is valid
3. Ensure `AI_ENABLED=true`
4. Restart controller

### Voice Commands Not Working

**Error:** "Microphone access denied"

**Solutions:**
1. Grant microphone permissions in browser
2. Use HTTPS (required for microphone in some browsers)
3. Check browser compatibility (Chrome/Edge recommended)

### Slow Responses

**Causes:**
- Large chat history
- Complex queries
- OpenAI API latency

**Solutions:**
- Clear chat (refresh page)
- Use simpler queries
- Check OpenAI status

### Rate Limit Exceeded

**Error:** "Rate limit exceeded"

**Solutions:**
- Wait a few minutes
- Upgrade OpenAI plan
- Implement request throttling

## 📊 Performance Tips

**For Fast Responses:**
- Use `gpt-4o-mini` model
- Keep queries concise
- Limit chat history to 10 messages

**For Better Accuracy:**
- Use `gpt-4o` model
- Provide more context
- Ask specific questions

**Cost Optimization:**
- Use `gpt-4o-mini` (cheapest)
- Cache common queries
- Limit insight refresh frequency

## 🎯 Use Cases

### DevOps Engineer
- "Deploy latest version to staging"
- "Show me production deployment history"
- "Check health of all production agents"

### Team Lead
- "What's our deployment success rate today?"
- "How many deployments in the last week?"
- "Are there any failing deployments?"

### On-Call Engineer
- "What's broken?"
- "Show recent failures"
- "Deploy hotfix to all web servers"

### New Team Member
- "How do I deploy to production?"
- "What agents do we have?"
- "Show me how to check deployment status"

## 🚀 Advanced Features

### Multi-Step Commands

**You:** "Deploy myorg/app to staging, wait for success, then deploy to production"

**AI:** Currently executes one step at a time, but you can chain commands in conversation.

### Context Awareness

The AI remembers the last 10 messages in your conversation, allowing for follow-up questions:

**You:** "Show me agents"
**AI:** *lists agents*
**You:** "What about their deployment history?"
**AI:** *shows history for previously mentioned agents*

### Smart Defaults

If you don't specify:
- Branch → defaults to `main`
- Status → shows all
- Time window → last 24 hours

## 📝 Best Practices

1. **Be Specific** - Include repo names, hostnames, branches
2. **Ask Follow-ups** - AI remembers context
3. **Use Quick Actions** - Faster for common tasks
4. **Check Insights** - Review AI recommendations regularly
5. **Voice for Speed** - Faster than typing for known commands

## 🔮 Future Enhancements

Potential features (not yet implemented):
- Multi-step deployment workflows
- Scheduled deployments via AI
- Integration with Slack/Teams
- Custom AI training on your deployment patterns
- Predictive failure analysis
- Automated rollback recommendations

## 📚 Related Documentation

- [Main README](../README.md) - Project overview
- [Quick Reference](../QUICK_REFERENCE.md) - Command cheat sheet
- [Architecture](./ARCHITECTURE.md) - System design
- [Deployment Guide](./DEPLOYMENT.md) - Production setup

## 💡 Tips & Tricks

**Keyboard Shortcuts:**
- `Enter` in chat → Send message
- `Esc` → Close chat widget

**Voice Command Tips:**
- Say "comma" for pauses
- Use full names: "web-zero-one"
- Speak commands like sentences

**Quick Queries:**
- "Status" → System overview
- "Agents" → List agents
- "Jobs" → Recent deployments
- "Failures" → Recent errors
- "Stats" → Deployment metrics

---

**Need Help?** Just ask the AI assistant: "How do I [task]?"
