# Chat Session Management - Implementation Guide

## Overview

Added persistent chat sessions with history, archiving, and session switching capabilities.

## Backend Changes

### Database Schema (`app/store.py`)

**New Tables:**

1. **chat_sessions**
   - id (TEXT PRIMARY KEY)
   - user_id (TEXT) - Default: "default"
   - name (TEXT) - Optional session name
   - created_at (TEXT)
   - last_activity (TEXT)
   - archived (BOOLEAN)
   - archived_at (TEXT)

2. **chat_messages**
   - id (INTEGER PRIMARY KEY AUTOINCREMENT)
   - session_id (TEXT FOREIGN KEY)
   - role (TEXT) - "user" or "assistant"
   - content (TEXT)
   - timestamp (TEXT)
   - metadata (TEXT JSON) - Stores quick_actions, action_taken, etc.

**New Methods:**
- `create_chat_session()` - Create new session
- `get_chat_session()` - Get session details
- `list_chat_sessions()` - List all sessions
- `update_session_activity()` - Update last activity timestamp
- `archive_chat_session()` - Archive a session
- `unarchive_chat_session()` - Restore archived session
- `delete_chat_session()` - Delete session and messages
- `save_chat_message()` - Save message to session
- `get_chat_history()` - Load session history

### API Endpoints (`app/main.py`)

**Session Management:**
- `POST /v1/ai/sessions` - Create new session
- `GET /v1/ai/sessions` - List all sessions
- `GET /v1/ai/sessions/{id}` - Get session details
- `GET /v1/ai/sessions/{id}/history` - Get chat history
- `POST /v1/ai/sessions/{id}/archive` - Archive session
- `POST /v1/ai/sessions/{id}/unarchive` - Unarchive session
- `DELETE /v1/ai/sessions/{id}` - Delete session

**Enhanced Chat Endpoint:**
- Updated `/v1/ai/chat` to accept `session_id`
- Auto-loads last 20 messages if session provided
- Auto-saves user and assistant messages
- Creates session if doesn't exist

### AI Models (`app/ai_assistant.py`)

**AIChatRequest Enhanced:**
```python
class AIChatRequest(BaseModel):
    message: str
    conversation_history: List[AIMessage] = []
    session_id: Optional[str] = None  # NEW!
```

## Frontend Changes Needed

### HTML Structure

Add session sidebar to chat widget:

```html
<div class="ai-chat-widget" id="ai-chat-widget">
    <!-- NEW: Session Sidebar -->
    <div class="chat-sessions-sidebar" id="sessions-sidebar">
        <div class="sessions-header">
            <h4>💬 Chats</h4>
            <button class="new-session-btn" onclick="createNewSession()">+</button>
        </div>
        <div class="sessions-list" id="sessions-list">
            <!-- Sessions will be rendered here -->
        </div>
        <div class="archived-toggle">
            <label>
                <input type="checkbox" id="show-archived" onchange="toggleArchivedSessions()">
                Show Archived
            </label>
        </div>
    </div>
    
    <!-- Existing chat area -->
    <div class="chat-main-area">
        <div class="ai-chat-header">
            <button class="toggle-sidebar-btn" onclick="toggleSessionsSidebar()">☰</button>
            <h3>🤖 AI Assistant</h3>
            <div class="session-actions">
                <button onclick="archiveCurrentSession()" title="Archive">📥</button>
                <button onclick="toggleChat()">×</button>
            </div>
        </div>
        <!-- Rest of existing chat UI -->
    </div>
</div>
```

### CSS Styles

```css
.chat-sessions-sidebar {
    width: 200px;
    background: var(--azure-gray-50);
    border-right: 1px solid var(--azure-gray-200);
    display: flex;
    flex-direction: column;
}

.sessions-header {
    padding: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--azure-gray-200);
}

.new-session-btn {
    width: 32px;
    height: 32px;
    border-radius: 4px;
    background: var(--azure-blue);
    color: white;
    border: none;
    font-size: 20px;
    cursor: pointer;
}

.sessions-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
}

.session-item {
    padding: 12px;
    margin-bottom: 4px;
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.2s;
}

.session-item:hover {
    background: var(--azure-gray-100);
}

.session-item.active {
    background: var(--azure-blue);
    color: white;
}

.session-item.archived {
    opacity: 0.6;
}

.chat-main-area {
    flex: 1;
    display: flex;
    flex-direction: column;
}
```

### JavaScript Functions

```javascript
let currentSessionId = null;

// Create new session
async function createNewSession() {
    try {
        const response = await fetch('/v1/ai/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: 'default',
                name: `Chat ${new Date().toLocaleDateString()}`
            })
        });
        
        const data = await response.json();
        currentSessionId = data.session_id;
        
        // Clear current chat
        document.getElementById('ai-messages').innerHTML = '';
        conversationHistory = [];
        
        // Reload sessions list
        await loadSessions();
        
        showWelcomeMessage();
    } catch (error) {
        console.error('Failed to create session:', error);
    }
}

// Load all sessions
async function loadSessions() {
    try {
        const showArchived = document.getElementById('show-archived').checked;
        const response = await fetch(`/v1/ai/sessions?include_archived=${showArchived}`);
        const data = await response.json();
        
        const sessionsList = document.getElementById('sessions-list');
        sessionsList.innerHTML = '';
        
        data.sessions.forEach(session => {
            const item = document.createElement('div');
            item.className = `session-item ${session.archived ? 'archived' : ''} ${session.id === currentSessionId ? 'active' : ''}`;
            item.innerHTML = `
                <div class="session-name">${session.name || 'Unnamed Chat'}</div>
                <div class="session-time">${new Date(session.last_activity).toLocaleString()}</div>
            `;
            item.onclick = () => loadSession(session.id);
            sessionsList.appendChild(item);
        });
    } catch (error) {
        console.error('Failed to load sessions:', error);
    }
}

// Load specific session
async function loadSession(sessionId) {
    try {
        const response = await fetch(`/v1/ai/sessions/${sessionId}/history`);
        const data = await response.json();
        
        currentSessionId = sessionId;
        
        // Clear and reload chat
        const messagesDiv = document.getElementById('ai-messages');
        messagesDiv.innerHTML = '';
        conversationHistory = [];
        
        // Render messages
        data.messages.forEach(msg => {
            addChatMessage(msg.role, msg.content, msg.metadata?.quick_actions);
            conversationHistory.push({ role: msg.role, content: msg.content });
        });
        
        // Update active session UI
        await loadSessions();
    } catch (error) {
        console.error('Failed to load session:', error);
    }
}

// Archive current session
async function archiveCurrentSession() {
    if (!currentSessionId) return;
    
    if (!confirm('Archive this chat session?')) return;
    
    try {
        await fetch(`/v1/ai/sessions/${currentSessionId}/archive`, {
            method: 'POST'
        });
        
        // Create new session
        await createNewSession();
    } catch (error) {
        console.error('Failed to archive session:', error);
    }
}

// Update sendMessage to use current session
async function sendMessage() {
    const input = document.getElementById('ai-input');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Ensure we have a session
    if (!currentSessionId) {
        await createNewSession();
    }
    
    addChatMessage('user', message);
    conversationHistory.push({ role: 'user', content: message });
    
    input.value = '';
    showTypingIndicator();
    
    try {
        const response = await fetch('/v1/ai/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                conversation_history: conversationHistory,
                session_id: currentSessionId  // NEW!
            })
        });
        
        removeTypingIndicator();
        
        if (response.ok) {
            const data = await response.json();
            addChatMessage('assistant', data.response, data.quick_actions);
            
            conversationHistory.push({ role: 'assistant', content: data.response });
            
            // Other existing logic...
        }
    } catch (error) {
        removeTypingIndicator();
        addChatMessage('assistant', 'Sorry, I could not connect to the AI service.');
    }
}

// Initialize session on chat open
function toggleChat() {
    const widget = document.getElementById('ai-chat-widget');
    widget.classList.toggle('open');
    
    if (widget.classList.contains('open')) {
        document.getElementById('ai-input').focus();
        
        // Load sessions and create default if none
        loadSessions().then(async () => {
            if (!currentSessionId) {
                await createNewSession();
            }
        });
    }
}
```

## Usage

### For Users

1. **Start Chatting**: Click the chat icon (💬)
2. **New Session**: Click the "+" button to start fresh
3. **Switch Sessions**: Click any session in the sidebar
4. **Archive Session**: Click the archive button (📥) in header
5. **View Archived**: Toggle "Show Archived" checkbox

### For Developers

**Create Session:**
```bash
curl -X POST http://localhost:8080/v1/ai/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id": "default", "name": "My Chat"}'
```

**List Sessions:**
```bash
curl http://localhost:8080/v1/ai/sessions
```

**Get History:**
```bash
curl http://localhost:8080/v1/ai/sessions/{session_id}/history
```

**Chat with Session:**
```bash
curl -X POST http://localhost:8080/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello",
    "session_id": "your-session-id-here"
  }'
```

## Benefits

✅ **Persistent Conversations**: Never lose chat history
✅ **Multiple Contexts**: Manage different projects separately
✅ **Clean Organization**: Archive old chats
✅ **Auto-Resume**: Conversations pick up where you left off
✅ **Full History**: Review past interactions
✅ **Metadata Storage**: Preserves quick actions and context

## Next Steps

1. Add session renaming
2. Add session search
3. Add export/import functionality
4. Add session sharing (team feature)
5. Add session analytics
