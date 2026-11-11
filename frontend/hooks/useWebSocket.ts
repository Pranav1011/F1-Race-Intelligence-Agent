'use client'

import { useCallback, useRef, useState } from 'react'
import { WSIncomingMessage, WSOutgoingMessage, Visualization, MessageMetadata, QueryInterpretation } from '@/types'

interface StatusUpdate {
  stage: string
  message: string
  detail?: string
  progress?: number
}

interface ToolUpdate {
  toolId: string
  toolName?: string
  status: 'start' | 'progress' | 'end'
  progress?: number
  message?: string
  success?: boolean
  resultSummary?: string
}

interface UseWebSocketOptions {
  url: string
  onToken?: (token: string) => void
  onVisualization?: (viz: Visualization) => void
  onMetadata?: (meta: MessageMetadata) => void
  onSessionId?: (sessionId: string) => void
  onStatus?: (status: StatusUpdate) => void
  onInterpreted?: (interpretation: QueryInterpretation) => void
  onToolUpdate?: (update: ToolUpdate) => void
  // Server finished the answer; error is set when the agent reported a failure
  onDone?: (error: string | null) => void
  // Server sent an error frame (a done frame still follows)
  onError?: (error: string) => void
  // Socket opened, so the backend is reachable
  onConnect?: () => void
  // The message could not be sent, or the socket closed before a done frame
  // arrived (server down, restarted, network)
  onDisconnect?: () => void
}

interface UseWebSocketReturn {
  sendMessage: (content: string, sessionId: string, userId?: string) => void
  isConnected: boolean
  disconnect: () => void
}

export function useWebSocket(options: UseWebSocketOptions): UseWebSocketReturn {
  const {
    url,
    onToken,
    onVisualization,
    onMetadata,
    onSessionId,
    onStatus,
    onInterpreted,
    onToolUpdate,
    onDone,
    onError,
    onConnect,
    onDisconnect,
  } = options

  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  const disconnect = useCallback(() => {
    const ws = wsRef.current
    // Clear the ref first so this socket's onclose is treated as stale
    wsRef.current = null
    ws?.close()
    setIsConnected(false)
  }, [])

  const sendMessage = useCallback(
    (content: string, sessionId: string, userId?: string) => {
      // Replace any previous socket; its late events are ignored as stale
      const previous = wsRef.current
      let ws: WebSocket
      try {
        ws = new WebSocket(url)
      } catch (e) {
        console.error('Failed to open WebSocket:', e)
        wsRef.current = null
        previous?.close()
        setIsConnected(false)
        onDisconnect?.()
        return
      }
      wsRef.current = ws
      previous?.close()
      let doneReceived = false

      ws.onopen = () => {
        if (wsRef.current !== ws) return
        setIsConnected(true)
        onConnect?.()

        const message: WSOutgoingMessage = {
          type: 'message',
          content,
          session_id: sessionId,
          user_id: userId,
        }
        ws.send(JSON.stringify(message))
      }

      ws.onmessage = (event) => {
        if (wsRef.current !== ws) return
        try {
          const data: WSIncomingMessage = JSON.parse(event.data)

          switch (data.type) {
            case 'session':
              if (data.session_id && onSessionId) {
                onSessionId(data.session_id)
              }
              break

            case 'interpreted':
              if (onInterpreted && data.original) {
                onInterpreted({
                  original: data.original,
                  expanded: data.expanded || data.original,
                  corrections: data.corrections || [],
                  intent: data.intent || 'general',
                  confidence: data.confidence || 0,
                })
              }
              break

            case 'metadata':
              if (onMetadata) {
                onMetadata({
                  queryType: data.query_type,
                  responseType: data.response_type,
                  confidence: data.confidence,
                })
              }
              break

            case 'token':
              if (data.token && onToken) {
                onToken(data.token)
              }
              break

            case 'visualization':
              if (data.spec && onVisualization) {
                onVisualization(data.spec)
              }
              break

            case 'status':
              if (data.stage && onStatus) {
                onStatus({
                  stage: data.stage,
                  message: data.message || '',
                  detail: data.detail,
                  progress: data.progress,
                })
              }
              break

            case 'tool_start':
              if (onToolUpdate && data.tool_id) {
                onToolUpdate({
                  toolId: data.tool_id,
                  toolName: data.tool_name,
                  status: 'start',
                  message: data.message,
                })
              }
              break

            case 'tool_progress':
              if (onToolUpdate && data.tool_id) {
                onToolUpdate({
                  toolId: data.tool_id,
                  status: 'progress',
                  progress: data.progress,
                  message: data.message,
                })
              }
              break

            case 'tool_end':
              if (onToolUpdate && data.tool_id) {
                onToolUpdate({
                  toolId: data.tool_id,
                  toolName: data.tool_name,
                  status: 'end',
                  success: data.success,
                  resultSummary: data.result_summary,
                })
              }
              break

            case 'error':
              if (data.error && onError) {
                onError(data.error)
              }
              break

            case 'done':
              doneReceived = true
              if (onDone) {
                onDone(data.error || null)
              }
              // Close connection after done
              ws.close()
              break
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }

      ws.onerror = (event) => {
        console.error('WebSocket error:', event)
      }

      // onclose follows every onerror, so a failed or dropped connection is
      // reported once, here
      ws.onclose = () => {
        if (wsRef.current !== ws) return
        wsRef.current = null
        setIsConnected(false)
        if (!doneReceived && onDisconnect) {
          onDisconnect()
        }
      }
    },
    [url, onToken, onVisualization, onMetadata, onSessionId, onStatus, onInterpreted, onToolUpdate, onDone, onError, onConnect, onDisconnect]
  )

  return {
    sendMessage,
    isConnected,
    disconnect,
  }
}
