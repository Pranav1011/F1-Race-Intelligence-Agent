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

const INTERRUPTED_ON_LOAD =
  'This answer was interrupted before it finished (the page was reloaded or closed). Send the question again.'

/**
 * Lifecycle of the single in-flight answer:
 *   idle      -> streaming  (startStream)
 *   streaming -> idle       (finishStream without error)
 *   streaming -> error      (finishStream with error: done.error, error frame,
 *                            or socket closed before done)
 *   error     -> streaming  (next startStream)
 *   streaming -> idle       (target session deleted: stream abandoned)
 * Only 'streaming' disables the input, so no state can block it forever.
 */
export type StreamStatus = 'idle' | 'streaming' | 'error'

/** Where the in-flight answer is written, fixed when the message is sent. */
export interface StreamTarget {
  sessionId: string
  messageId: string
}

interface ChatStore {
  sessions: Session[]
  activeSessionId: string | null
  streamStatus: StreamStatus
  streamTarget: StreamTarget | null

  // Computed getters
  getActiveSession: () => Session | undefined
  getMessages: () => Message[]

  // Actions
  createSession: () => string
  switchSession: (id: string) => void
  deleteSession: (id: string) => void
  clearAllSessions: () => void
  renameSession: (id: string, title: string) => void
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>, sessionId?: string) => string | null
  startStream: (content: string) => StreamTarget | null
  appendToStream: (token: string) => void
  updateStreamMessage: (updates: Partial<Message>) => void
  recordStreamError: (error: string) => void
  finishStream: (error?: string | null) => void
  loadFromStorage: () => void
  saveToStorage: () => void
}

function updateMessage(
  sessions: Session[],
  target: StreamTarget,
  update: (message: Message) => Message
): Session[] {
  return sessions.map((s) => {
    if (s.id !== target.sessionId) return s
    return {
      ...s,
      messages: s.messages.map((m) => (m.id === target.messageId ? update(m) : m)),
    }
  })
}

// An empty assistant message in storage is a stream that never finished.
function markInterruptedAnswers(session: Session): Session {
  const interrupted = session.messages.some(
    (m) => m.role === 'assistant' && m.content === '' && !m.error
  )
  if (!interrupted) return session
  return {
    ...session,
    messages: session.messages.map((m) =>
      m.role === 'assistant' && m.content === '' && !m.error
        ? { ...m, error: INTERRUPTED_ON_LOAD }
        : m
    ),
  }
}

export const useChatStore = create<ChatStore>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  streamStatus: 'idle',
  streamTarget: null,

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
    if (get().streamTarget?.sessionId === id) {
      set({ streamStatus: 'idle', streamTarget: null })
    }

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
      streamStatus: 'idle',
      streamTarget: null,
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

  addMessage: (msg, sessionId) => {
    const targetSessionId = sessionId ?? get().activeSessionId
    if (!targetSessionId) return null

    const newMessage: Message = {
      ...msg,
      id: generateId(),
      timestamp: new Date().toISOString(),
    }

    set((state) => ({
      sessions: state.sessions.map((s) => {
        if (s.id !== targetSessionId) return s

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
    return newMessage.id
  },

  startStream: (content: string) => {
    if (get().streamStatus === 'streaming') return null

    const sessionId = get().activeSessionId ?? get().createSession()
    get().addMessage({ role: 'user', content }, sessionId)
    const messageId = get().addMessage({ role: 'assistant', content: '' }, sessionId)
    if (!messageId) return null

    const target = { sessionId, messageId }
    set({ streamStatus: 'streaming', streamTarget: target })
    return target
  },

  appendToStream: (token: string) => {
    const target = get().streamTarget
    if (!target) return
    set((state) => ({
      sessions: updateMessage(state.sessions, target, (m) => ({
        ...m,
        content: m.content + token,
      })),
    }))
  },

  updateStreamMessage: (updates) => {
    const target = get().streamTarget
    if (!target) return
    set((state) => ({
      sessions: updateMessage(state.sessions, target, (m) => ({ ...m, ...updates })),
    }))
  },

  recordStreamError: (error: string) => {
    get().updateStreamMessage({ error })
  },

  finishStream: (error) => {
    if (error) {
      get().recordStreamError(error)
    }
    set({ streamStatus: error ? 'error' : 'idle', streamTarget: null })
    get().saveToStorage()
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
        sessions: data.sessions.map(markInterruptedAnswers),
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
