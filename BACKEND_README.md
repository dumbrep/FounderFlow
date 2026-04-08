# FounderFlow Backend API

## Overview
This backend provides HTTP API endpoints for the FounderFlow frontend, integrating with all MCP servers (Email, Instagram, LinkedIn, Hiring, Meet Schedule, Lead Gen).

## Architecture

```
Frontend (React) → Backend (FastAPI) → Agent (LangGraph) → MCP Servers → External Services
```

## Setup & Installation

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start All MCP Servers
```bash
python run.py
```

This launches 6 MCP servers:
- **Email Server** - Port 8001
- **Meet Schedule Server** - Port 8002  
- **LinkedIn Server** - Port 8003
- **Hiring Server** - Port 8004
- **Instagram Server** - Port 8000
- **Lead Gen Server** - Port 8006

### 3. Start Backend Server
```bash
python backend.py
```

Backend runs on **Port 8005**

### 4. Start Frontend
```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

### POST `/chat`
Main conversation endpoint with HITL (Human-in-the-Loop) support.

**Request:**
```json
{
  "query": "Send an email to john@example.com about the meeting",
  "session_id": "optional-session-uuid"
}
```

**Response:**
```json
{
  "session_id": "uuid-of-session",
  "message": "AI response or confirmation",
  "needs_approval": true,
  "approval_summary": "**Email Draft**\nSubject: Meeting\nTo: john@example.com\n..."
}
```

### GET `/health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "sessions": 3
}
```

## Workflow Examples

### Email Workflow
1. User: "Draft an email to john@example.com about tomorrow's meeting"
2. Backend: Calls `composeEmail` tool → Returns draft for approval
3. User: "yes" → Backend: Calls `sendEmail` tool → Email sent ✅

### LinkedIn Posting
1. User: "Create a LinkedIn post about AI innovation"
2. Backend: Calls `generateLinkedInPost` → Returns draft
3. User: "make it more professional" → Backend: Revises draft
4. User: "yes" → Backend: Calls `postLinkedIn` → Posted ✅

### Hiring Form
1. User: "Create a job application form"
2. Backend: Calls `createHiringForm` → Form created
3. Returns: Form URL and ID

## Session Management

- Each user conversation maintains a separate session
- Sessions track conversation history and pending approvals
- Session ID is returned in every response for continuity
- Sessions persist in memory (reset on server restart)

## HITL (Human-in-the-Loop) Flow

1. **Tool Execution**: Agent calls a tool (e.g., composeEmail)
2. **Approval Required**: Backend returns `needs_approval: true` with preview
3. **User Decision**:
   - Type "yes" → Proceed with final action
   - Provide feedback → Agent revises and asks for approval again
   - Cancel → Start new request

## Port Configuration

| Service | Port |
|---------|------|
| Backend API | 8005 |
| Instagram MCP | 8000 |
| Email MCP | 8001 |
| Meet Schedule MCP | 8002 |
| LinkedIn MCP | 8003 |
| Hiring MCP | 8004 |
| Lead Gen MCP | 8006 |

## Environment Variables

Required in `.env`:
```env
OPENAI_API_KEY=your_api_key_here
# Instagram
long_lived_token=your_instagram_token
ig_user_id=your_instagram_user_id
# Email
APP_EMAIL=your_gmail
APP_PASSCODE=your_app_password
# LinkedIn (via Zapier)
MCP_API_KEY=your_zapier_mcp_key
```

## Troubleshooting

### "Cannot communicate with FounderFlow engine"
- Ensure backend is running on port 8005
- Check all MCP servers are running

### "ModuleNotFoundError"
- Run `pip install -r requirements.txt`

### "Port already in use"
- Check if another process is using ports 8000-8006
- Stop conflicting processes

## Development

### Adding New MCP Server
1. Create server in `servers/` folder
2. Add to `run.py` SERVERS list
3. Update `backend.py` MultiServerMCPClient config
4. Add tools to TOOL_OUTPUT_TYPE map
5. Update SYSTEM_PROMPT with workflow instructions

### Testing
```bash
# Test backend health
curl http://localhost:8005/health

# Test chat endpoint
curl -X POST http://localhost:8005/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Hello"}'
```

## Architecture Details

### Agent State
Tracks conversation context:
- `messages`: Chat history
- `previous_draft`: Email/LinkedIn draft being revised
- `image_url`: Generated image URL
- `linkedin_draft`: LinkedIn post being edited
- `hiring_draft`: Job post being edited
- `lead_report`: Lead generation results
- `pending_approval`: Boolean flag for HITL
- `approval_data`: Data waiting for approval

### Tool State Mapping
Maps tool outputs to state keys for revision workflows:
- `composeEmail` → `previous_draft`
- `generateLinkedInPost` → `linkedin_draft`
- `createImage` → `image_url`
- `searchLeads` → `lead_report`

This enables the agent to reference previous outputs when user requests revisions.
