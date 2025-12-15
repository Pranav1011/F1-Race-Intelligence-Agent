// Message types
export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  metadata?: MessageMetadata
  visualization?: Visualization
}

export interface MessageMetadata {
  queryType?: string
  responseType?: string
  confidence?: number
}

// Session types
export interface Session {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  messages: Message[]
}

// Visualization types
export type ChartType = 'line' | 'bar' | 'scatter' | 'table' | 'area'

export interface Visualization {
  id: string
  type: ChartType
  title: string
  data: Record<string, unknown>[]
  config?: VisualizationConfig
}

export interface VisualizationConfig {
  xAxis?: string
  yAxis?: string | string[]
  colors?: string[]
  legend?: boolean
  tooltip?: boolean
}

// WebSocket message types
export type WSMessageType =
  | 'message'
  | 'session'
  | 'metadata'
  | 'token'
  | 'visualization'
  | 'tool_start'
  | 'tool_end'
  | 'ui_mode'
  | 'error'
  | 'done'

export interface WSIncomingMessage {
  type: WSMessageType
  session_id?: string
  token?: string
  query_type?: string
  response_type?: string
  confidence?: number
  spec?: Visualization
  tool?: {
    name: string
    id: string
  }
  tool_id?: string
  mode?: string
  error?: string
}

export interface WSOutgoingMessage {
  type: 'message'
  content: string
  session_id: string
  user_id?: string
}

// Storage types
export interface StoredData {
  sessions: Session[]
  activeSessionId: string | null
  version: number
}

// API response types
export interface ChatResponse {
  content: string
  session_id: string
  query_type: string
  response_type: string
  confidence: number
  error: string | null
  visualizations: Visualization[]
}
