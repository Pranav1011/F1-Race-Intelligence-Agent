'use client'

import { useEffect, useCallback, useState } from 'react'
import { MotionConfig } from 'framer-motion'
import { useChatStore } from '@/stores/chat-store'
import { useUIStore } from '@/stores/ui-store'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useBackendHealth } from '@/hooks/useBackendHealth'
import { Header } from '@/components/layout/Header'
import { Sidebar } from '@/components/layout/Sidebar'
import { ArtifactPanel } from '@/components/layout/ArtifactPanel'
import { ChatArea } from '@/components/chat/ChatArea'
import { API_ENDPOINTS } from '@/utils/api'

const DISCONNECTED_MESSAGE =
  'Lost the connection to the backend before the answer finished. Check that the API is running, then send your question again.'

export default function Home() {
  const {
    activeSessionId,
    getMessages,
    streamStatus,
    streamTarget,
    startStream,
    appendToStream,
    updateStreamMessage,
    recordStreamError,
    finishStream,
    interpretations,
    setStreamInterpretation,
    dismissInterpretation,
    setConnection,
    loadFromStorage,
  } = useChatStore()

  const { setArtifact } = useUIStore()

  // Track current status message for loading indicator
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [statusDetail, setStatusDetail] = useState<string | null>(null)
  const [statusProgress, setStatusProgress] = useState<number | null>(null)

  // Load sessions from localStorage on mount
  useEffect(() => {
    loadFromStorage()
  }, [loadFromStorage])

  useBackendHealth(API_ENDPOINTS.health, setConnection)

  const clearStatus = useCallback(() => {
    setStatusMessage(null)
    setStatusDetail(null)
    setStatusProgress(null)
  }, [])

  // WebSocket connection
  const { sendMessage: wsSendMessage } = useWebSocket({
    url: API_ENDPOINTS.chatWs,
    onInterpreted: (interp) => {
      // Shown in the session the answer belongs to, then auto-hidden after 5 seconds
      const target = useChatStore.getState().streamTarget
      if (!target) return
      setStreamInterpretation(interp)
      setTimeout(() => dismissInterpretation(target.sessionId, interp), 5000)
    },
    onToken: (token) => {
      // Clear status message when we start receiving tokens
      clearStatus()
      appendToStream(token)
    },
    onVisualization: (viz) => {
      // Only open the panel if the user is still looking at the answering session
      const { streamTarget: target, activeSessionId: active } = useChatStore.getState()
      if (target?.sessionId === active) {
        setArtifact(viz)
      }
      updateStreamMessage({ visualization: viz })
    },
    onMetadata: (meta) => {
      updateStreamMessage({ metadata: meta })
    },
    onStatus: (status) => {
      // Update status message for loading indicator
      setStatusMessage(status.message)
      setStatusDetail(status.detail || null)
      setStatusProgress(status.progress || null)
    },
    onDone: (error) => {
      clearStatus()
      finishStream(error)
    },
    onError: (error) => {
      recordStreamError(error)
    },
    onConnect: () => {
      setConnection('connected')
    },
    onDisconnect: () => {
      setConnection('disconnected')
      clearStatus()
      finishStream(DISCONNECTED_MESSAGE)
    },
  })

  // Handle sending a message
  const handleSendMessage = useCallback(
    (content: string) => {
      // Adds the user message and the assistant placeholder to the active
      // session and pins the stream to them; refuses while an answer streams
      const target = startStream(content)
      if (!target) return

      wsSendMessage(content, target.sessionId)
    },
    [startStream, wsSendMessage]
  )

  const isStreaming = streamStatus === 'streaming'
  const isStreamingHere = isStreaming && streamTarget?.sessionId === activeSessionId

  const messages = getMessages()
  const interpretation = activeSessionId ? interpretations[activeSessionId] ?? null : null

  return (
    <MotionConfig reducedMotion="user">
      <div className="flex h-screen bg-background-primary text-text-primary overflow-hidden">
        {/* Sidebar */}
        <Sidebar />

        {/* Main content area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header */}
          <Header />

          {/* Chat + Artifact Panel */}
          <div className="flex-1 flex overflow-hidden">
            {/* Chat area */}
            <main className="flex-1 min-w-0">
              <ChatArea
                messages={messages}
                isStreaming={isStreamingHere}
                inputDisabled={isStreaming}
                answeringElsewhere={isStreaming && !isStreamingHere}
                onSendMessage={handleSendMessage}
                statusMessage={isStreamingHere ? statusMessage : null}
                interpretation={interpretation}
                showInterpretation={interpretation !== null}
              />
            </main>

            {/* Artifact Panel */}
            <ArtifactPanel />
          </div>
        </div>
      </div>
    </MotionConfig>
  )
}
