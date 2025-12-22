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
export type ChartType =
  // Generic chart types
  | 'line'
  | 'bar'
  | 'scatter'
  | 'table'
  | 'area'
  // Distribution charts
  | 'box_plot'
  | 'histogram'
  | 'violin_plot'
  // Line charts
  | 'lap_progression'
  | 'lap_comparison'
  | 'lap_time_comparison'
  | 'delta_line'
  // F1-specific chart types
  | 'tire_strategy'
  | 'gap_evolution'
  | 'position_battle'
  | 'sector_heatmap'
  | 'sector_comparison'
  | 'race_progress'
  | 'bar_chart'

export interface Visualization {
  id: string
  type: ChartType
  title: string
  data: Record<string, unknown>[]
  config?: VisualizationConfig
  drivers?: string[] // For F1-specific charts
}

export interface VisualizationConfig {
  xAxis?: string
  yAxis?: string | string[]
  colors?: Record<string, string> | string[]
  legend?: boolean
  tooltip?: boolean
  // F1-specific config
  maxLaps?: number
  totalLaps?: number
  highlightOvertakes?: boolean
  showDelta?: boolean
  compoundColors?: Record<string, string>
  driverStats?: Record<string, unknown>
  raceName?: string
  year?: number
  // Delta/comparison config
  referenceDriver?: string
  comparisonDriver?: string
  binWidth?: number
}

// WebSocket message types
export type WSMessageType =
  | 'message'
  | 'session'
  | 'interpreted'
  | 'metadata'
  | 'token'
  | 'visualization'
  | 'tool_start'
  | 'tool_progress'
  | 'tool_end'
  | 'ui_mode'
  | 'status'
  | 'error'
  | 'done'

// Query interpretation result
export interface QueryInterpretation {
  original: string
  expanded: string
  corrections: Array<{
    original: string
    corrected: string
    type: string
    confidence?: number
  }>
  intent: string
  confidence: number
}

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
  tool_name?: string
  success?: boolean
  result_summary?: string
  progress?: number
  mode?: string
  stage?: string
  message?: string
  detail?: string
  error?: string
  // Interpreted event fields
  original?: string
  expanded?: string
  corrections?: QueryInterpretation['corrections']
  intent?: string
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
