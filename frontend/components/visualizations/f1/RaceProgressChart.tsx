'use client'

import { useMemo, useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Group } from '@visx/group'
import { scaleLinear, scaleOrdinal } from '@visx/scale'
import { useTooltip, TooltipWithBounds } from '@visx/tooltip'
import { localPoint } from '@visx/event'
import { ParentSize } from '@visx/responsive'

// Types
interface LapData {
  lap: number
  driver: string
  position: number
  gap: number // Gap to leader in seconds
  compound: string
  lapTime?: number
  pitStop?: boolean
}

interface RaceProgressProps {
  data: LapData[]
  drivers: string[]
  totalLaps: number
  title?: string
}

// F1 Team Colors
const TEAM_COLORS: Record<string, { primary: string; secondary: string }> = {
  VER: { primary: '#3671C6', secondary: '#1B3A6A' },
  PER: { primary: '#3671C6', secondary: '#1B3A6A' },
  HAM: { primary: '#27F4D2', secondary: '#00A19C' },
  RUS: { primary: '#27F4D2', secondary: '#00A19C' },
  LEC: { primary: '#E8002D', secondary: '#8B0000' },
  SAI: { primary: '#E8002D', secondary: '#8B0000' },
  NOR: { primary: '#FF8000', secondary: '#CC6600' },
  PIA: { primary: '#FF8000', secondary: '#CC6600' },
  ALO: { primary: '#229971', secondary: '#0D503D' },
  STR: { primary: '#229971', secondary: '#0D503D' },
  GAS: { primary: '#FF87BC', secondary: '#FF69B4' },
  OCO: { primary: '#FF87BC', secondary: '#FF69B4' },
  ALB: { primary: '#64C4FF', secondary: '#005AFF' },
  SAR: { primary: '#64C4FF', secondary: '#005AFF' },
  BOT: { primary: '#52E252', secondary: '#00C000' },
  ZHO: { primary: '#52E252', secondary: '#00C000' },
  MAG: { primary: '#B6BABD', secondary: '#808080' },
  HUL: { primary: '#B6BABD', secondary: '#808080' },
  TSU: { primary: '#6692FF', secondary: '#0000FF' },
  RIC: { primary: '#6692FF', secondary: '#0000FF' },
}

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: '#FF3333',
  MEDIUM: '#FFD700',
  HARD: '#EEEEEE',
  INTERMEDIATE: '#43B02A',
  WET: '#0067AD',
}

// Car Icon Component
function CarIcon({ color, size = 24 }: { color: string; size?: number }) {
  return (
    <svg width={size} height={size * 0.4} viewBox="0 0 60 24" fill="none">
      {/* Car body */}
      <path
        d="M5 12 L10 8 L20 6 L45 6 L55 10 L55 16 L50 18 L15 18 L5 16 Z"
        fill={color}
        stroke="#000"
        strokeWidth="1"
      />
      {/* Cockpit */}
      <ellipse cx="30" cy="10" rx="8" ry="3" fill="#000" opacity="0.6" />
      {/* Front wing */}
      <rect x="52" y="6" width="6" height="12" rx="1" fill={color} stroke="#000" strokeWidth="0.5" />
      {/* Rear wing */}
      <rect x="2" y="8" width="4" height="8" rx="1" fill={color} stroke="#000" strokeWidth="0.5" />
      {/* Wheels */}
      <circle cx="15" cy="18" r="4" fill="#1a1a1a" stroke="#333" strokeWidth="1" />
      <circle cx="45" cy="18" r="4" fill="#1a1a1a" stroke="#333" strokeWidth="1" />
      {/* Wheel highlights */}
      <circle cx="15" cy="18" r="2" fill="#333" />
      <circle cx="45" cy="18" r="2" fill="#333" />
    </svg>
  )
}

// Pit Stop Icon
function PitIcon() {
  return (
    <motion.div
      initial={{ scale: 0 }}
      animate={{ scale: 1 }}
      className="absolute -top-6 left-1/2 -translate-x-1/2"
    >
      <div className="bg-yellow-500 text-black text-[10px] font-bold px-1.5 py-0.5 rounded">
        PIT
      </div>
    </motion.div>
  )
}

// Tooltip styles
const tooltipStyles = {
  backgroundColor: 'rgba(15, 15, 15, 0.95)',
  border: '1px solid rgba(255, 255, 255, 0.1)',
  borderRadius: '12px',
  color: '#fff',
  fontSize: '13px',
  padding: '12px 16px',
  boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
  backdropFilter: 'blur(8px)',
}

function RaceProgressChartInner({
  data,
  drivers,
  totalLaps,
  width,
  height,
}: RaceProgressProps & { width: number; height: number }) {
  const [currentLap, setCurrentLap] = useState(1)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playSpeed, setPlaySpeed] = useState(500) // ms per lap

  const {
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
    tooltipData,
    hideTooltip,
    showTooltip,
  } = useTooltip<LapData>()

  // Auto-play animation
  useEffect(() => {
    if (!isPlaying) return

    const interval = setInterval(() => {
      setCurrentLap((prev) => {
        if (prev >= totalLaps) {
          setIsPlaying(false)
          return prev
        }
        return prev + 1
      })
    }, playSpeed)

    return () => clearInterval(interval)
  }, [isPlaying, totalLaps, playSpeed])

  // Margins
  const margin = { top: 60, right: 100, bottom: 60, left: 80 }
  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  // Get data for current lap
  const currentLapData = useMemo(() => {
    return data.filter((d) => d.lap === currentLap)
  }, [data, currentLap])

  // Get race progress (% complete)
  const raceProgress = (currentLap / totalLaps) * 100

  // Scales
  const xScale = scaleLinear({
    domain: [0, Math.max(...data.map((d) => d.gap), 60)],
    range: [innerWidth, 0], // Reversed so leader is on the right
  })

  const yScale = scaleLinear({
    domain: [1, Math.max(...drivers.map((_, i) => i + 1), 20)],
    range: [0, innerHeight],
  })

  // Position label scale (for animation)
  const positionHeight = innerHeight / Math.max(drivers.length, 10)

  return (
    <div className="relative w-full">
      {/* Header with race progress */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-4">
          <h3 className="text-xl font-bold text-white">Race Progress</h3>
          <div className="flex items-center gap-2 bg-background-tertiary rounded-full px-4 py-2">
            <span className="text-f1-gray text-sm">Lap</span>
            <span className="text-white font-bold text-lg">{currentLap}</span>
            <span className="text-f1-gray text-sm">/ {totalLaps}</span>
          </div>
        </div>

        {/* Playback controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCurrentLap(1)}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
            title="Reset"
          >
            <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
              <path d="M4 4a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2H4zm0 2h12v8H4V6z" />
            </svg>
          </button>
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="px-4 py-2 bg-f1-red hover:bg-f1-red/80 rounded-lg font-medium transition-colors"
          >
            {isPlaying ? 'Pause' : 'Play'}
          </button>
          <select
            value={playSpeed}
            onChange={(e) => setPlaySpeed(Number(e.target.value))}
            className="bg-background-tertiary text-white rounded-lg px-3 py-2 text-sm"
          >
            <option value={1000}>1x</option>
            <option value={500}>2x</option>
            <option value={250}>4x</option>
            <option value={100}>10x</option>
          </select>
        </div>
      </div>

      {/* Race progress bar */}
      <div className="relative h-2 bg-background-tertiary rounded-full mb-6 overflow-hidden">
        <motion.div
          className="absolute h-full bg-gradient-to-r from-f1-red to-orange-500 rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${raceProgress}%` }}
          transition={{ duration: 0.3 }}
        />
        <input
          type="range"
          min={1}
          max={totalLaps}
          value={currentLap}
          onChange={(e) => setCurrentLap(Number(e.target.value))}
          className="absolute inset-0 w-full opacity-0 cursor-pointer"
        />
      </div>

      {/* Main visualization - Track style view */}
      <div
        className="relative rounded-2xl overflow-hidden"
        style={{
          background: 'linear-gradient(180deg, #0a0a0a 0%, #1a1a1a 100%)',
          height: height,
        }}
      >
        {/* Track markers */}
        <div className="absolute inset-0">
          {/* Start/Finish line */}
          <div className="absolute right-[80px] top-0 bottom-0 w-1 bg-gradient-to-b from-white/0 via-white/30 to-white/0" />

          {/* Track lines */}
          {[...Array(10)].map((_, i) => (
            <div
              key={i}
              className="absolute top-0 bottom-0 w-px bg-white/5"
              style={{ left: `${(i + 1) * 10}%` }}
            />
          ))}
        </div>

        <svg width={width} height={height}>
          <defs>
            {/* Gradient for leader */}
            <linearGradient id="leaderGlow" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#E10600" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#E10600" stopOpacity="0" />
            </linearGradient>
          </defs>

          <Group left={margin.left} top={margin.top}>
            {/* Position ladder on left */}
            {drivers.slice(0, 20).map((_, i) => (
              <g key={`pos-${i}`}>
                <text
                  x={-50}
                  y={yScale(i + 1) + positionHeight / 2}
                  fill="#666"
                  fontSize="12"
                  textAnchor="end"
                  dominantBaseline="middle"
                >
                  P{i + 1}
                </text>
                {/* Position line */}
                <line
                  x1={-30}
                  x2={innerWidth + 20}
                  y1={yScale(i + 1) + positionHeight / 2}
                  y2={yScale(i + 1) + positionHeight / 2}
                  stroke="#333"
                  strokeWidth="1"
                  strokeDasharray="2,4"
                />
              </g>
            ))}

            {/* Cars */}
            <AnimatePresence mode="popLayout">
              {currentLapData
                .sort((a, b) => a.position - b.position)
                .map((lapData) => {
                  const color = TEAM_COLORS[lapData.driver]?.primary || '#888'
                  const xPos = xScale(lapData.gap)
                  const yPos = yScale(lapData.position) + positionHeight / 2

                  return (
                    <motion.g
                      key={lapData.driver}
                      initial={{ opacity: 0, x: xPos }}
                      animate={{
                        opacity: 1,
                        x: xPos,
                        y: yPos - 12,
                      }}
                      transition={{
                        type: 'spring',
                        stiffness: 100,
                        damping: 20,
                        duration: 0.3,
                      }}
                      onMouseEnter={(e) => {
                        const point = localPoint(e) || { x: 0, y: 0 }
                        showTooltip({
                          tooltipData: lapData,
                          tooltipLeft: point.x,
                          tooltipTop: point.y,
                        })
                      }}
                      onMouseLeave={hideTooltip}
                      style={{ cursor: 'pointer' }}
                    >
                      {/* Car glow for leader */}
                      {lapData.position === 1 && (
                        <rect
                          x={-80}
                          y={-5}
                          width={80}
                          height={34}
                          fill="url(#leaderGlow)"
                          rx="4"
                        />
                      )}

                      {/* Car */}
                      <foreignObject x={-60} y={0} width={60} height={24}>
                        <CarIcon color={color} size={60} />
                      </foreignObject>

                      {/* Driver code badge */}
                      <g transform="translate(-80, 4)">
                        <rect
                          width={20}
                          height={16}
                          fill={color}
                          rx="2"
                        />
                        <text
                          x={10}
                          y={12}
                          fill="#fff"
                          fontSize="8"
                          fontWeight="bold"
                          textAnchor="middle"
                        >
                          {lapData.driver}
                        </text>
                      </g>

                      {/* Tire compound indicator */}
                      <circle
                        cx={10}
                        cy={12}
                        r={6}
                        fill={COMPOUND_COLORS[lapData.compound?.toUpperCase()] || '#888'}
                        stroke="#000"
                        strokeWidth="1"
                      />

                      {/* Pit stop indicator */}
                      {lapData.pitStop && (
                        <g transform="translate(-30, -20)">
                          <rect
                            width={24}
                            height={14}
                            fill="#FFD700"
                            rx="2"
                          />
                          <text
                            x={12}
                            y={10}
                            fill="#000"
                            fontSize="8"
                            fontWeight="bold"
                            textAnchor="middle"
                          >
                            PIT
                          </text>
                        </g>
                      )}
                    </motion.g>
                  )
                })}
            </AnimatePresence>

            {/* Gap scale at bottom */}
            <g transform={`translate(0, ${innerHeight + 20})`}>
              <text x={innerWidth} y={20} fill="#666" fontSize="11" textAnchor="end">
                Leader
              </text>
              {[0, 10, 20, 30, 40, 50, 60].map((gap) => (
                <g key={gap} transform={`translate(${xScale(gap)}, 0)`}>
                  <line y1={0} y2={10} stroke="#444" />
                  <text y={25} fill="#666" fontSize="10" textAnchor="middle">
                    {gap === 0 ? '' : `+${gap}s`}
                  </text>
                </g>
              ))}
            </g>
          </Group>
        </svg>

        {/* Tooltip */}
        {tooltipOpen && tooltipData && (
          <TooltipWithBounds
            top={tooltipTop}
            left={tooltipLeft}
            style={tooltipStyles}
          >
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <div
                  className="w-4 h-4 rounded"
                  style={{
                    backgroundColor: TEAM_COLORS[tooltipData.driver]?.primary || '#888',
                  }}
                />
                <span className="font-bold text-lg">{tooltipData.driver}</span>
                <span className="text-f1-gray">P{tooltipData.position}</span>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <span className="text-f1-gray">Gap to Leader:</span>
                <span className="text-white font-medium">
                  {tooltipData.gap === 0 ? 'Leader' : `+${tooltipData.gap.toFixed(3)}s`}
                </span>
                <span className="text-f1-gray">Tire:</span>
                <div className="flex items-center gap-2">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{
                      backgroundColor:
                        COMPOUND_COLORS[tooltipData.compound?.toUpperCase()] || '#888',
                    }}
                  />
                  <span className="text-white">{tooltipData.compound}</span>
                </div>
                {tooltipData.lapTime && (
                  <>
                    <span className="text-f1-gray">Lap Time:</span>
                    <span className="text-white font-mono">
                      {(tooltipData.lapTime / 1000).toFixed(3)}s
                    </span>
                  </>
                )}
              </div>
              {tooltipData.pitStop && (
                <div className="pt-2 mt-2 border-t border-white/10 text-yellow-400 text-sm font-medium">
                  Pit Stop this lap
                </div>
              )}
            </div>
          </TooltipWithBounds>
        )}
      </div>
    </div>
  )
}

// Responsive wrapper
export function RaceProgressChart(props: RaceProgressProps) {
  if (!props.data || props.data.length === 0) {
    return (
      <div className="flex items-center justify-center h-96 bg-background-secondary rounded-2xl border border-white/5">
        <div className="text-center">
          <div className="text-4xl mb-4">🏎️</div>
          <p className="text-f1-gray">No race data available</p>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full">
      {props.title && (
        <h3 className="text-xl font-bold text-white mb-4">{props.title}</h3>
      )}
      <ParentSize>
        {({ width }) => (
          <RaceProgressChartInner
            {...props}
            width={Math.max(width, 600)}
            height={500}
          />
        )}
      </ParentSize>
    </div>
  )
}

export { RaceProgressChart as default }
