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
  onDone?: () => void
  onError?: (error: string) => void
}

interface UseWebSocketReturn {
  sendMessage: (content: string, sessionId: string, userId?: string) => void
  isConnected: boolean
  isStreaming: boolean
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
  } = options

  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setIsConnected(false)
    setIsStreaming(false)
  }, [])

  const sendMessage = useCallback(
    (content: string, sessionId: string, userId?: string) => {
      // Close existing connection if any
      if (wsRef.current) {
        wsRef.current.close()
      }

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
        setIsStreaming(true)

        const message: WSOutgoingMessage = {
          type: 'message',
          content,
          session_id: sessionId,
          user_id: userId,
        }
        ws.send(JSON.stringify(message))
      }

      ws.onmessage = (event) => {
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
              setIsStreaming(false)
              if (onDone) {
                onDone()
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
        if (onError) {
          onError('Connection error. Please try again.')
        }
        setIsStreaming(false)
      }

      ws.onclose = () => {
        setIsConnected(false)
        setIsStreaming(false)
        wsRef.current = null
      }
    },
    [url, onToken, onVisualization, onMetadata, onSessionId, onStatus, onInterpreted, onToolUpdate, onDone, onError]
  )

  return {
    sendMessage,
    isConnected,
    isStreaming,
    disconnect,
  }
}
