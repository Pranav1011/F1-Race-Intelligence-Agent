import { create } from 'zustand'
import { Message, Session, StoredData } from '@/types'

const STORAGE_KEY = 'f1-ria-sessions'
const STORAGE_VERSION = 1

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

function generateTitle(content: string): string {
  // Take first 30 chars of first message, clean up
  const cleaned = content.replace(/\s+/g, ' ').trim()
  if (cleaned.length <= 30) return cleaned
  return cleaned.substring(0, 30) + '...'
}

interface ChatStore {
  sessions: Session[]
  activeSessionId: string | null
  isStreaming: boolean

  // Computed getters
  getActiveSession: () => Session | undefined
  getMessages: () => Message[]

  // Actions
  createSession: () => string
  switchSession: (id: string) => void
  deleteSession: (id: string) => void
  clearAllSessions: () => void
  renameSession: (id: string, title: string) => void
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => void
  updateLastMessage: (updates: Partial<Message>) => void
  appendToLastMessage: (token: string) => void
  setStreaming: (streaming: boolean) => void
  loadFromStorage: () => void
  saveToStorage: () => void
}

export const useChatStore = create<ChatStore>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  isStreaming: false,

  getActiveSession: () => {
    const { sessions, activeSessionId } = get()
    return sessions.find((s) => s.id === activeSessionId)
  },

  getMessages: () => {
    const session = get().getActiveSession()
    return session?.messages || []
  },

  createSession: () => {
    const id = generateId()
    const now = new Date().toISOString()
    const newSession: Session = {
      id,
      title: 'New Chat',
      createdAt: now,
      updatedAt: now,
      messages: [],
    }

    set((state) => ({
      sessions: [newSession, ...state.sessions],
      activeSessionId: id,
    }))

    get().saveToStorage()
    return id
  },

  switchSession: (id: string) => {
    set({ activeSessionId: id })
    get().saveToStorage()
  },

  deleteSession: (id: string) => {
    set((state) => {
      const newSessions = state.sessions.filter((s) => s.id !== id)
      let newActiveId = state.activeSessionId

      // If deleting active session, switch to first available or null
      if (state.activeSessionId === id) {
        newActiveId = newSessions.length > 0 ? newSessions[0].id : null
      }

      return {
        sessions: newSessions,
        activeSessionId: newActiveId,
      }
    })

    get().saveToStorage()
  },

  clearAllSessions: () => {
    set({
      sessions: [],
      activeSessionId: null,
    })
    get().saveToStorage()
    // Create a fresh session after clearing
    get().createSession()
  },

  renameSession: (id: string, title: string) => {
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === id ? { ...s, title, updatedAt: new Date().toISOString() } : s
      ),
    }))

    get().saveToStorage()
  },

  addMessage: (msg) => {
    const { activeSessionId, sessions } = get()
    if (!activeSessionId) return

    const newMessage: Message = {
      ...msg,
      id: generateId(),
      timestamp: new Date().toISOString(),
    }

    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== activeSessionId) return s

        const updatedSession: Session = {
          ...s,
          messages: [...s.messages, newMessage],
          updatedAt: new Date().toISOString(),
        }

        // Auto-generate title from first user message
        if (s.messages.length === 0 && msg.role === 'user') {
          updatedSession.title = generateTitle(msg.content)
        }

        return updatedSession
      }),
    }))

    // Debounced save
    setTimeout(() => get().saveToStorage(), 500)
  },

  updateLastMessage: (updates) => {
    const { activeSessionId } = get()
    if (!activeSessionId) return

    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== activeSessionId || s.messages.length === 0) return s

        const messages = [...s.messages]
        const lastIdx = messages.length - 1
        messages[lastIdx] = { ...messages[lastIdx], ...updates }

        return { ...s, messages, updatedAt: new Date().toISOString() }
      }),
    }))
  },

  appendToLastMessage: (token: string) => {
    const { activeSessionId } = get()
    if (!activeSessionId) return

    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== activeSessionId || s.messages.length === 0) return s

        const messages = [...s.messages]
        const lastIdx = messages.length - 1
        messages[lastIdx] = {
          ...messages[lastIdx],
          content: messages[lastIdx].content + token,
        }

        return { ...s, messages }
      }),
    }))
  },

  setStreaming: (streaming: boolean) => {
    set({ isStreaming: streaming })

    // Save when streaming ends
    if (!streaming) {
      get().saveToStorage()
    }
  },

  loadFromStorage: () => {
    if (typeof window === 'undefined') return

    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (!stored) {
        // Create initial session if none exist
        get().createSession()
        return
      }

      const data: StoredData = JSON.parse(stored)

      // Version migration if needed
      if (data.version !== STORAGE_VERSION) {
        // Handle migrations here in the future
      }

      set({
        sessions: data.sessions,
        activeSessionId: data.activeSessionId,
      })

      // Create a session if none exist
      if (data.sessions.length === 0) {
        get().createSession()
      }
    } catch (e) {
      console.error('Failed to load sessions from storage:', e)
      get().createSession()
    }
  },

  saveToStorage: () => {
    if (typeof window === 'undefined') return

    const { sessions, activeSessionId } = get()
    const data: StoredData = {
      sessions,
      activeSessionId,
      version: STORAGE_VERSION,
    }

    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch (e) {
      console.error('Failed to save sessions to storage:', e)
    }
  },
}))
