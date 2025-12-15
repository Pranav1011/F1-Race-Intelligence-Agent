# Phase 4: Frontend UI Enhancement - Design Document

## Overview

Enhance the frontend with streaming responses, session persistence, proper component architecture, and a Claude-like artifact panel for visualizations.

## Goals

1. **Streaming responses** - Real-time token-by-token display using WebSocket
2. **Session persistence** - Remember chat history across page refreshes with multiple sessions
3. **Component architecture** - Extract reusable components, add Zustand state management
4. **Artifact panel** - Collapsible side panel for visualizations (like Claude's artifact viewer)

---

## Layout Design

### Default State (Chat Only)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Header: F1 Race Intelligence Agent                                 │
├──────────┬──────────────────────────────────────────────────────────┤
│ Sessions │                                                          │
│ ──────── │                                                          │
│ + New    │                    Chat Area                             │
│          │              (messages + input)                          │
│ Today    │                                                          │
│ • Chat 1 │                                                          │
│ • Chat 2 │                                                          │
│          │                                                          │
│ Yesterday│                                                          │
│ • Chat 3 │                                                          │
├──────────┴──────────────────────────────────────────────────────────┤
│  [Toggle Sidebar]                              [Input] [Send]       │
└─────────────────────────────────────────────────────────────────────┘
```

### With Visualization (Split Panel)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Header                                                             │
├──────────┬─────────────────────────────┬────────────────────────────┤
│ Sessions │         Chat Area           │    Artifact Panel    [✕]  │
│          │                             │    ─────────────────       │
│ + New    │  User: Compare VER vs NOR   │    [Chart/Viz here]       │
│          │        tire deg...          │                            │
│ • Chat 1 │                             │    Lap Time Comparison     │
│ • Chat 2 │  Assistant: Here's the      │    ┌────────────────┐     │
│          │  comparison...              │    │  📊 Chart      │     │
│          │                             │    └────────────────┘     │
│          │                             │                            │
└──────────┴─────────────────────────────┴────────────────────────────┘
```

### Behavior

- **Sidebar**: Collapsible, hidden on mobile, shows session history grouped by date
- **Artifact panel**: Hidden by default, slides in from right when viz data arrives, toggle button to show/hide
- **Chat**: Always visible, shrinks when artifact panel opens

---

## Component Architecture

### File Structure

```
frontend/
├── app/
│   ├── page.tsx                 # Main layout, orchestrates panels
│   └── globals.css              # Keep existing
├── components/
│   ├── chat/
│   │   ├── ChatArea.tsx         # Message list + input
│   │   ├── MessageBubble.tsx    # Single message (user/assistant)
│   │   ├── MessageInput.tsx     # Input field + send button
│   │   ├── TypingIndicator.tsx  # Streaming dots animation
│   │   └── SuggestedPrompts.tsx # Empty state prompts
│   ├── layout/
│   │   ├── Sidebar.tsx          # Session list + new chat button
│   │   ├── Header.tsx           # Top bar with branding
│   │   └── ArtifactPanel.tsx    # Collapsible right panel
│   └── visualizations/
│       └── ChartRenderer.tsx    # Renders chart specs from backend
├── stores/
│   ├── chat-store.ts            # Messages, sessions, active session
│   └── ui-store.ts              # Sidebar open, artifact panel open
├── hooks/
│   ├── useWebSocket.ts          # WebSocket connection + streaming
│   └── useLocalStorage.ts       # Persist sessions to localStorage
├── lib/
│   └── api.ts                   # API client utilities
└── types/
    └── index.ts                 # Message, Session, Visualization types
```

---

## State Management (Zustand)

### Chat Store

```typescript
// stores/chat-store.ts
interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  metadata?: {
    queryType?: string
    responseType?: string
    confidence?: number
  }
  visualization?: Visualization
}

interface Session {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  messages: Message[]
}

interface ChatStore {
  sessions: Session[]
  activeSessionId: string | null
  isStreaming: boolean

  // Computed
  activeSession: () => Session | undefined
  messages: () => Message[]

  // Actions
  createSession: () => string
  switchSession: (id: string) => void
  deleteSession: (id: string) => void
  renameSession: (id: string, title: string) => void
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => void
  appendToLastMessage: (token: string) => void
  setStreaming: (streaming: boolean) => void
  loadFromStorage: () => void
  saveToStorage: () => void
}
```

### UI Store

```typescript
// stores/ui-store.ts
interface Visualization {
  id: string
  type: 'line' | 'bar' | 'scatter' | 'table'
  title: string
  data: any[]
  config?: Record<string, any>
}

interface UIStore {
  sidebarOpen: boolean
  artifactPanelOpen: boolean
  currentArtifact: Visualization | null

  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  toggleArtifactPanel: () => void
  setArtifactPanelOpen: (open: boolean) => void
  setArtifact: (viz: Visualization | null) => void
  clearArtifact: () => void
}
```

---

## WebSocket Streaming

### Protocol

```
1. User sends message
2. Frontend connects to ws://localhost:8000/api/v1/chat/ws
3. Frontend sends: { type: "message", content: "...", session_id: "..." }
4. Backend streams:
   - { type: "session", session_id: "..." }
   - { type: "metadata", query_type: "...", confidence: 0.9 }
   - { type: "token", token: "Max" }
   - { type: "token", token: " Ver" }
   - { type: "token", token: "stappen" }
   - { type: "visualization", spec: {...} }
   - { type: "done" }
5. Frontend updates UI in real-time
```

### useWebSocket Hook

```typescript
// hooks/useWebSocket.ts
interface UseWebSocketOptions {
  url: string
  onToken: (token: string) => void
  onVisualization: (spec: Visualization) => void
  onMetadata: (meta: { queryType: string; confidence: number }) => void
  onDone: () => void
  onError: (error: string) => void
}

interface UseWebSocketReturn {
  sendMessage: (content: string, sessionId: string) => void
  isConnected: boolean
  isStreaming: boolean
  disconnect: () => void
}
```

### UX During Streaming

- Input disabled while streaming
- Typing indicator shows until first token arrives
- Tokens appear with smooth animation
- Message metadata displayed after completion

---

## Session Persistence

### localStorage Schema

```typescript
// Key: "f1-ria-sessions"
interface StoredData {
  sessions: Session[]
  activeSessionId: string | null
  version: number  // For future migrations
}
```

### Auto-save Behavior

- Save to localStorage on every message (debounced 500ms)
- Auto-generate session title from first user message (truncated to ~30 chars)
- Load sessions on app mount
- Create new session if none exist

### Session List Grouping

- **Today** - Sessions from today
- **Yesterday** - Sessions from yesterday
- **Previous 7 days** - Older sessions
- Sorted by `updatedAt` descending within each group

---

## Implementation Order

1. **Types** - Define all TypeScript interfaces
2. **Stores** - Implement Zustand stores (chat + ui)
3. **Hooks** - useWebSocket, useLocalStorage
4. **Components** - Build from bottom up:
   - MessageBubble, MessageInput, TypingIndicator
   - ChatArea, SuggestedPrompts
   - Sidebar, Header, ArtifactPanel
   - ChartRenderer
5. **Integration** - Wire up in page.tsx
6. **Testing** - Manual testing of all flows

---

## Success Criteria

- [ ] Messages stream token-by-token in real-time
- [ ] Chat history persists across page refreshes
- [ ] Multiple sessions can be created and switched between
- [ ] Artifact panel opens when visualization data arrives
- [ ] Artifact panel can be toggled open/closed
- [ ] Sidebar can be collapsed on desktop
- [ ] Responsive on mobile (sidebar hidden, artifact panel full-width)
