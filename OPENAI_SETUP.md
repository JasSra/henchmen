# OpenAI API Key Setup

## Your Current Issue

The API key in your `.env` file is invalid or expired. You're seeing this error:
```
Error code: 401 - Incorrect API key provided
```

## How to Fix It

### Step 1: Get a New API Key

1. Go to https://platform.openai.com/api-keys
2. Sign in to your OpenAI account
3. Click "Create new secret key"
4. Give it a name (e.g., "DeployBot Controller")
5. Copy the key immediately (you won't be able to see it again!)

### Step 2: Update Your .env File

1. Open `/Users/jas/code/My/Henchmen/.env`
2. Replace the current `OPENAI_API_KEY` value with your new key:
   ```bash
   OPENAI_API_KEY=sk-your-new-key-here
   ```

### Step 3: Restart the Controller

```bash
# Stop the current controller (Ctrl+C in the terminal)
# Then restart it
make run-ui
```

## What Was Fixed

I've fixed several issues with the AI assistant:

✅ **Method Call Errors** - Changed `get_agents()` → `list_agents()` and `get_jobs()` → `list_jobs()`
✅ **Conversation Context** - Now properly maintains conversation history between messages
✅ **Keyboard Navigation** - Added up/down arrow keys to recall previous messages
✅ **Better Error Handling** - Shows proper error messages from API
✅ **Context Awareness** - AI now remembers the last 20 messages in conversation

## Testing the AI Assistant

After updating your API key and restarting, try these commands:

1. **Simple query**: "How many agents do I have?"
2. **Statistics**: "Show me deployment stats for last 24 hours"
3. **Context test**: "What did I just ask you?" (tests conversation memory)
4. **Keyboard test**: Press ↑ to recall your last message

## Conversation Features

- **Memory**: AI remembers last 20 messages for context
- **Up/Down Arrows**: Navigate through your last 50 messages
- **Quick Actions**: Click any quick action button to send pre-built queries
- **Voice Commands**: Click 🎤 to use voice input (requires microphone permission)

## Troubleshooting

### Still getting 401 errors?
- Make sure you copied the entire API key (they're very long)
- Check for extra spaces before/after the key
- Verify the key starts with `sk-`

### AI not responding?
- Check the terminal for error messages
- Verify `AI_ENABLED=true` in .env
- Make sure the controller restarted successfully

### Voice commands not working?
- Allow microphone permissions in your browser
- Voice only works with HTTPS or localhost
- Check browser console for WebRTC errors
