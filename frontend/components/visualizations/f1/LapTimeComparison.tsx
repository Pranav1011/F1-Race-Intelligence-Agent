'use client'

import { useMemo, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Group } from '@visx/group'
import { LinePath, Bar, Circle } from '@visx/shape'
import { curveMonotoneX } from '@visx/curve'
import { scaleLinear, scaleOrdinal } from '@visx/scale'
import { AxisBottom, AxisLeft } from '@visx/axis'
import { GridRows } from '@visx/grid'
import { useTooltip, TooltipWithBounds } from '@visx/tooltip'
import { localPoint } from '@visx/event'
import { ParentSize } from '@visx/responsive'
import { bisector } from 'd3-array'

// Types
interface LapTimeData {
  lap: number
  driver: string
  lapTime: number // in seconds
  compound: string
  sector1?: number
  sector2?: number
  sector3?: number
  delta?: number // delta to other driver
}

interface LapTimeComparisonProps {
  data: LapTimeData[]
  drivers: string[]
  title?: string
  showDelta?: boolean
}

// Driver colors (2024 season)
const DRIVER_COLORS: Record<string, { primary: string; gradient: string[] }> = {
  VER: { primary: '#3671C6', gradient: ['#3671C6', '#1B3A6A'] },
  PER: { primary: '#3671C6', gradient: ['#3671C6', '#1B3A6A'] },
  HAM: { primary: '#27F4D2', gradient: ['#27F4D2', '#00A19C'] },
  RUS: { primary: '#27F4D2', gradient: ['#27F4D2', '#00A19C'] },
  LEC: { primary: '#E8002D', gradient: ['#E8002D', '#8B0000'] },
  SAI: { primary: '#E8002D', gradient: ['#E8002D', '#8B0000'] },
  NOR: { primary: '#FF8000', gradient: ['#FF8000', '#CC6600'] },
  PIA: { primary: '#FF8000', gradient: ['#FF8000', '#CC6600'] },
  ALO: { primary: '#229971', gradient: ['#229971', '#0D503D'] },
  STR: { primary: '#229971', gradient: ['#229971', '#0D503D'] },
}

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: '#FF3333',
  MEDIUM: '#FFD700',
  HARD: '#EEEEEE',
  INTERMEDIATE: '#43B02A',
  WET: '#0067AD',
}

// Format time
const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  if (mins > 0) {
    return `${mins}:${secs.toFixed(3).padStart(6, '0')}`
  }
  return secs.toFixed(3)
}

// Tooltip styles
const tooltipStyles = {
  backgroundColor: 'rgba(15, 15, 15, 0.95)',
  border: '1px solid rgba(255, 255, 255, 0.1)',
  borderRadius: '16px',
  color: '#fff',
  fontSize: '13px',
  padding: '16px 20px',
  boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.05)',
  backdropFilter: 'blur(12px)',
}

const bisectLap = bisector<LapTimeData, number>((d) => d.lap).left

function LapTimeComparisonChart({
  data,
  drivers,
  width,
  height,
  showDelta = true,
}: LapTimeComparisonProps & { width: number; height: number }) {
  const [hoveredDriver, setHoveredDriver] = useState<string | null>(null)
  const [selectedLap, setSelectedLap] = useState<number | null>(null)

  const {
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
    tooltipData,
    hideTooltip,
    showTooltip,
  } = useTooltip<{ lap: number; data: LapTimeData[] }>()

  // Margins
  const margin = { top: 40, right: 140, bottom: 60, left: 70 }
  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  // Group data by driver
  const dataByDriver = useMemo(() => {
    const grouped: Record<string, LapTimeData[]> = {}
    drivers.forEach((d) => {
      grouped[d] = data.filter((item) => item.driver === d).sort((a, b) => a.lap - b.lap)
    })
    return grouped
  }, [data, drivers])

  // Calculate scales
  const { xScale, yScale, deltaScale } = useMemo(() => {
    const allLaps = data.map((d) => d.lap)
    const allTimes = data.map((d) => d.lapTime).filter((t) => t > 0)
    const allDeltas = data.map((d) => d.delta || 0).filter((d) => d !== 0)

    const minTime = Math.min(...allTimes) * 0.995
    const maxTime = Math.max(...allTimes) * 1.005
    const maxAbsDelta = Math.max(...allDeltas.map(Math.abs), 1)

    return {
      xScale: scaleLinear({
        domain: [Math.min(...allLaps), Math.max(...allLaps)],
        range: [0, innerWidth],
      }),
      yScale: scaleLinear({
        domain: [maxTime, minTime], // Inverted - faster times at top
        range: [innerHeight, 0],
      }),
      deltaScale: scaleLinear({
        domain: [-maxAbsDelta, maxAbsDelta],
        range: [40, -40],
      }),
    }
  }, [data, innerWidth, innerHeight])

  // Stats calculation
  const stats = useMemo(() => {
    const result: Record<string, { avg: number; fastest: number; fastestLap: number }> = {}
    drivers.forEach((driver) => {
      const driverData = dataByDriver[driver] || []
      const times = driverData.map((d) => d.lapTime).filter((t) => t > 0)
      if (times.length > 0) {
        const fastest = Math.min(...times)
        const fastestLap = driverData.find((d) => d.lapTime === fastest)?.lap || 0
        result[driver] = {
          avg: times.reduce((a, b) => a + b, 0) / times.length,
          fastest,
          fastestLap,
        }
      }
    })
    return result
  }, [drivers, dataByDriver])

  // Tooltip handler
  const handleTooltip = useCallback(
    (event: React.MouseEvent<SVGRectElement>) => {
      const point = localPoint(event) || { x: 0, y: 0 }
      const x = point.x - margin.left
      const lap = Math.round(xScale.invert(x))

      const lapData = data.filter((d) => d.lap === lap)
      if (lapData.length > 0) {
        setSelectedLap(lap)
        showTooltip({
          tooltipData: { lap, data: lapData },
          tooltipLeft: xScale(lap) + margin.left,
          tooltipTop: point.y,
        })
      }
    },
    [xScale, data, margin.left, showTooltip]
  )

  return (
    <div className="relative w-full">
      {/* Stats cards */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {drivers.map((driver) => {
          const driverStats = stats[driver]
          const color = DRIVER_COLORS[driver]?.primary || '#888'

          return (
            <motion.div
              key={driver}
              className="relative overflow-hidden rounded-2xl p-4"
              style={{
                background: `linear-gradient(135deg, ${color}20 0%, transparent 50%)`,
                border: `1px solid ${color}40`,
              }}
              onMouseEnter={() => setHoveredDriver(driver)}
              onMouseLeave={() => setHoveredDriver(null)}
              whileHover={{ scale: 1.02 }}
              transition={{ type: 'spring', stiffness: 300 }}
            >
              <div className="flex items-center gap-3 mb-3">
                <div
                  className="w-1 h-10 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <div>
                  <div className="text-white font-bold text-lg">{driver}</div>
                  <div className="text-f1-gray text-sm">
                    {dataByDriver[driver]?.length || 0} laps
                  </div>
                </div>
              </div>
              {driverStats && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-f1-gray text-xs uppercase tracking-wide">
                      Fastest Lap
                    </div>
                    <div className="text-white font-mono text-xl font-bold">
                      {formatTime(driverStats.fastest)}
                    </div>
                    <div className="text-f1-gray text-xs">
                      Lap {driverStats.fastestLap}
                    </div>
                  </div>
                  <div>
                    <div className="text-f1-gray text-xs uppercase tracking-wide">
                      Average
                    </div>
                    <div className="text-white font-mono text-xl">
                      {formatTime(driverStats.avg)}
                    </div>
                  </div>
                </div>
              )}
              {/* Glow effect on hover */}
              <div
                className="absolute inset-0 opacity-0 transition-opacity pointer-events-none"
                style={{
                  background: `radial-gradient(circle at 50% 50%, ${color}30 0%, transparent 70%)`,
                  opacity: hoveredDriver === driver ? 1 : 0,
                }}
              />
            </motion.div>
          )
        })}
      </div>

      {/* Main chart */}
      <div
        className="relative rounded-2xl overflow-hidden"
        style={{
          background: 'linear-gradient(180deg, #0f0f0f 0%, #1a1a1a 100%)',
          border: '1px solid rgba(255, 255, 255, 0.05)',
        }}
      >
        <svg width={width} height={height}>
          <defs>
            {/* Line gradients for each driver */}
            {drivers.map((driver) => {
              const colors = DRIVER_COLORS[driver]?.gradient || ['#888', '#444']
              return (
                <linearGradient
                  key={`gradient-${driver}`}
                  id={`line-gradient-${driver}`}
                  x1="0%"
                  y1="0%"
                  x2="100%"
                  y2="0%"
                >
                  <stop offset="0%" stopColor={colors[0]} />
                  <stop offset="100%" stopColor={colors[1]} />
                </linearGradient>
              )
            })}

            {/* Glow filter */}
            <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          <Group left={margin.left} top={margin.top}>
            {/* Grid */}
            <GridRows
              scale={yScale}
              width={innerWidth}
              stroke="#333"
              strokeOpacity={0.3}
              strokeDasharray="2,4"
            />

            {/* Lap time lines */}
            {drivers.map((driver) => {
              const driverData = dataByDriver[driver] || []
              const color = DRIVER_COLORS[driver]?.primary || '#888'
              const isHighlighted = !hoveredDriver || hoveredDriver === driver

              return (
                <g key={driver}>
                  {/* Line shadow/glow */}
                  <LinePath
                    data={driverData.filter((d) => d.lapTime > 0)}
                    x={(d) => xScale(d.lap)}
                    y={(d) => yScale(d.lapTime)}
                    stroke={color}
                    strokeWidth={8}
                    strokeOpacity={isHighlighted ? 0.2 : 0}
                    curve={curveMonotoneX}
                  />

                  {/* Main line */}
                  <LinePath
                    data={driverData.filter((d) => d.lapTime > 0)}
                    x={(d) => xScale(d.lap)}
                    y={(d) => yScale(d.lapTime)}
                    stroke={`url(#line-gradient-${driver})`}
                    strokeWidth={isHighlighted ? 3 : 1.5}
                    strokeOpacity={isHighlighted ? 1 : 0.3}
                    curve={curveMonotoneX}
                  />

                  {/* Fastest lap marker */}
                  {stats[driver] && (
                    <g
                      transform={`translate(${xScale(stats[driver].fastestLap)}, ${yScale(stats[driver].fastest)})`}
                    >
                      <Circle
                        r={8}
                        fill={color}
                        stroke="#fff"
                        strokeWidth={2}
                        filter="url(#glow)"
                      />
                      <text
                        y={-15}
                        fill="#fff"
                        fontSize="10"
                        textAnchor="middle"
                        fontWeight="bold"
                      >
                        FASTEST
                      </text>
                    </g>
                  )}

                  {/* Compound indicators on hover */}
                  {(hoveredDriver === driver || selectedLap) &&
                    driverData.map((d) => (
                      <Circle
                        key={`compound-${d.lap}`}
                        cx={xScale(d.lap)}
                        cy={yScale(d.lapTime)}
                        r={4}
                        fill={COMPOUND_COLORS[d.compound?.toUpperCase()] || '#888'}
                        stroke="#000"
                        strokeWidth={1}
                        opacity={d.lap === selectedLap ? 1 : 0.5}
                      />
                    ))}
                </g>
              )
            })}

            {/* Selected lap line */}
            {selectedLap && (
              <motion.line
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                x1={xScale(selectedLap)}
                x2={xScale(selectedLap)}
                y1={0}
                y2={innerHeight}
                stroke="#E10600"
                strokeWidth={2}
                strokeDasharray="4,4"
              />
            )}

            {/* Axes */}
            <AxisBottom
              top={innerHeight}
              scale={xScale}
              stroke="#444"
              tickStroke="#444"
              tickLabelProps={() => ({
                fill: '#888',
                fontSize: 11,
                textAnchor: 'middle',
              })}
              label="Lap"
              labelProps={{
                fill: '#888',
                fontSize: 12,
                textAnchor: 'middle',
              }}
            />

            <AxisLeft
              scale={yScale}
              stroke="#444"
              tickStroke="#444"
              tickFormat={(v) => formatTime(v as number)}
              tickLabelProps={() => ({
                fill: '#888',
                fontSize: 10,
                textAnchor: 'end',
                fontFamily: 'monospace',
              })}
              label="Lap Time"
              labelProps={{
                fill: '#888',
                fontSize: 12,
                textAnchor: 'middle',
              }}
              labelOffset={50}
            />

            {/* Invisible rect for tooltip */}
            <rect
              x={0}
              y={0}
              width={innerWidth}
              height={innerHeight}
              fill="transparent"
              onMouseMove={handleTooltip}
              onMouseLeave={() => {
                hideTooltip()
                setSelectedLap(null)
              }}
            />
          </Group>

          {/* Legend */}
          <Group left={width - margin.right + 20} top={margin.top}>
            {drivers.map((driver, i) => {
              const color = DRIVER_COLORS[driver]?.primary || '#888'
              return (
                <g
                  key={driver}
                  transform={`translate(0, ${i * 30})`}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={() => setHoveredDriver(driver)}
                  onMouseLeave={() => setHoveredDriver(null)}
                >
                  <rect
                    x={0}
                    y={-8}
                    width={100}
                    height={24}
                    fill={hoveredDriver === driver ? `${color}20` : 'transparent'}
                    rx={4}
                  />
                  <line x1={0} x2={20} y1={0} y2={0} stroke={color} strokeWidth={3} />
                  <text x={28} y={4} fill="#fff" fontSize="12" fontWeight="medium">
                    {driver}
                  </text>
                </g>
              )
            })}
          </Group>
        </svg>

        {/* Tooltip */}
        {tooltipOpen && tooltipData && (
          <TooltipWithBounds
            top={tooltipTop}
            left={tooltipLeft}
            style={tooltipStyles}
          >
            <div className="space-y-3">
              <div className="text-lg font-bold text-white border-b border-white/10 pb-2">
                Lap {tooltipData.lap}
              </div>
              {tooltipData.data
                .sort((a, b) => a.lapTime - b.lapTime)
                .map((d, i) => {
                  const color = DRIVER_COLORS[d.driver]?.primary || '#888'
                  const isFastest = i === 0

                  return (
                    <div
                      key={d.driver}
                      className="flex items-center justify-between gap-6"
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: color }}
                        />
                        <span className="font-medium">{d.driver}</span>
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{
                            backgroundColor:
                              COMPOUND_COLORS[d.compound?.toUpperCase()] || '#888',
                          }}
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-mono ${isFastest ? 'text-purple-400 font-bold' : 'text-white'}`}
                        >
                          {formatTime(d.lapTime)}
                        </span>
                        {i > 0 && (
                          <span className="text-red-400 text-sm">
                            +{(d.lapTime - tooltipData.data[0].lapTime).toFixed(3)}
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}

              {/* Sector times if available */}
              {tooltipData.data[0]?.sector1 && (
                <div className="pt-2 mt-2 border-t border-white/10">
                  <div className="text-xs text-f1-gray uppercase mb-2">Sectors</div>
                  {tooltipData.data.map((d) => (
                    <div key={d.driver} className="flex items-center gap-2 text-xs">
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{
                          backgroundColor: DRIVER_COLORS[d.driver]?.primary || '#888',
                        }}
                      />
                      <span className="w-8">{d.driver}</span>
                      <span className="font-mono text-f1-gray">
                        S1: {d.sector1?.toFixed(3)}
                      </span>
                      <span className="font-mono text-f1-gray">
                        S2: {d.sector2?.toFixed(3)}
                      </span>
                      <span className="font-mono text-f1-gray">
                        S3: {d.sector3?.toFixed(3)}
                      </span>
                    </div>
                  ))}
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
export function LapTimeComparison(props: LapTimeComparisonProps) {
  if (!props.data || props.data.length === 0) {
    return (
      <div className="flex items-center justify-center h-96 bg-background-secondary rounded-2xl border border-white/5">
        <div className="text-center">
          <div className="text-4xl mb-4">⏱️</div>
          <p className="text-f1-gray">No lap time data available</p>
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
          <LapTimeComparisonChart
            {...props}
            width={Math.max(width, 600)}
            height={450}
          />
        )}
      </ParentSize>
    </div>
  )
}

export { LapTimeComparison as default }
