'use client'

import { useMemo, useCallback } from 'react'
import { Group } from '@visx/group'
import { scaleBand } from '@visx/scale'
import { AxisBottom, AxisLeft } from '@visx/axis'
import { useTooltip, TooltipWithBounds, defaultStyles } from '@visx/tooltip'
import { localPoint } from '@visx/event'
import { ParentSize } from '@visx/responsive'
import { interpolateRdYlGn } from 'd3-scale-chromatic'

// Types
interface SectorData {
  driver: string
  sector1: number
  sector2: number
  sector3: number
  lapTime?: number
  lap?: number
}

interface SectorHeatmapProps {
  data: SectorData[]
  title?: string
  showDelta?: boolean // Show delta from fastest instead of absolute times
}

// Tooltip styles
const tooltipStyles = {
  ...defaultStyles,
  backgroundColor: '#1A1A1A',
  border: '1px solid #333',
  borderRadius: '8px',
  color: '#fff',
  fontSize: '12px',
  padding: '8px 12px',
}

// Format time in seconds to mm:ss.xxx or ss.xxx
function formatTime(seconds: number): string {
  if (seconds >= 60) {
    const mins = Math.floor(seconds / 60)
    const secs = (seconds % 60).toFixed(3)
    return `${mins}:${secs.padStart(6, '0')}`
  }
  return seconds.toFixed(3)
}

// Format delta
function formatDelta(delta: number): string {
  const sign = delta >= 0 ? '+' : ''
  return `${sign}${delta.toFixed(3)}`
}

function SectorHeatmapChart({
  data,
  width,
  height,
  showDelta = false,
}: SectorHeatmapProps & { width: number; height: number }) {
  const {
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
    tooltipData,
    hideTooltip,
    showTooltip,
  } = useTooltip<{
    driver: string
    sector: string
    time: number
    delta: number
    isBest: boolean
  }>()

  // Margins
  const margin = { top: 20, right: 80, bottom: 50, left: 80 }
  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  // Get unique drivers
  const drivers = useMemo(
    () => Array.from(new Set(data.map((d) => d.driver))),
    [data]
  )

  const sectors = ['S1', 'S2', 'S3']

  // Calculate best sector times and deltas
  const sectorStats = useMemo(() => {
    const bestS1 = Math.min(...data.map((d) => d.sector1).filter((v) => v > 0))
    const bestS2 = Math.min(...data.map((d) => d.sector2).filter((v) => v > 0))
    const bestS3 = Math.min(...data.map((d) => d.sector3).filter((v) => v > 0))

    const worstS1 = Math.max(...data.map((d) => d.sector1).filter((v) => v > 0))
    const worstS2 = Math.max(...data.map((d) => d.sector2).filter((v) => v > 0))
    const worstS3 = Math.max(...data.map((d) => d.sector3).filter((v) => v > 0))

    return {
      best: { S1: bestS1, S2: bestS2, S3: bestS3 },
      worst: { S1: worstS1, S2: worstS2, S3: worstS3 },
      range: {
        S1: worstS1 - bestS1,
        S2: worstS2 - bestS2,
        S3: worstS3 - bestS3,
      },
    }
  }, [data])

  // Scales
  const xScale = scaleBand({
    domain: sectors,
    range: [0, innerWidth],
    padding: 0.1,
  })

  const yScale = scaleBand({
    domain: drivers,
    range: [0, innerHeight],
    padding: 0.1,
  })

  // Color scale - green (fast) to red (slow)
  // We need to invert because low delta = good = green
  const getColorForSector = useCallback(
    (sectorName: string, value: number) => {
      const best = sectorStats.best[sectorName as keyof typeof sectorStats.best]
      const range = sectorStats.range[sectorName as keyof typeof sectorStats.range]
      const delta = value - best

      // Normalize delta to 0-1 range (0 = best = green, 1 = worst = red)
      const normalized = range > 0 ? delta / range : 0

      // Use green-to-red color scale (inverted so 0 = green)
      return interpolateRdYlGn(1 - normalized)
    },
    [sectorStats]
  )

  // Get sector value for a driver
  const getSectorValue = useCallback(
    (driver: string, sectorIndex: number): number => {
      const driverData = data.find((d) => d.driver === driver)
      if (!driverData) return 0

      switch (sectorIndex) {
        case 0:
          return driverData.sector1
        case 1:
          return driverData.sector2
        case 2:
          return driverData.sector3
        default:
          return 0
      }
    },
    [data]
  )

  // Tooltip handler
  const handleMouseMove = useCallback(
    (
      event: React.MouseEvent<SVGRectElement>,
      driver: string,
      sectorName: string,
      sectorIndex: number
    ) => {
      const point = localPoint(event) || { x: 0, y: 0 }
      const time = getSectorValue(driver, sectorIndex)
      const best = sectorStats.best[sectorName as keyof typeof sectorStats.best]
      const delta = time - best
      const isBest = Math.abs(delta) < 0.001

      showTooltip({
        tooltipData: { driver, sector: sectorName, time, delta, isBest },
        tooltipLeft: point.x,
        tooltipTop: point.y - 10,
      })
    },
    [getSectorValue, sectorStats.best, showTooltip]
  )

  return (
    <div className="relative">
      <svg width={width} height={height}>
        <Group left={margin.left} top={margin.top}>
          {/* Heatmap cells */}
          {drivers.map((driver) =>
            sectors.map((sector, sectorIndex) => {
              const value = getSectorValue(driver, sectorIndex)
              if (value <= 0) return null

              const x = xScale(sector) || 0
              const y = yScale(driver) || 0
              const cellWidth = xScale.bandwidth()
              const cellHeight = yScale.bandwidth()
              const color = getColorForSector(sector, value)
              const best =
                sectorStats.best[sector as keyof typeof sectorStats.best]
              const delta = value - best
              const isBest = Math.abs(delta) < 0.001

              return (
                <g key={`${driver}-${sector}`}>
                  <rect
                    x={x}
                    y={y}
                    width={cellWidth}
                    height={cellHeight}
                    fill={color}
                    stroke={isBest ? '#E10600' : '#333'}
                    strokeWidth={isBest ? 3 : 1}
                    rx={4}
                    onMouseMove={(e) =>
                      handleMouseMove(e, driver, sector, sectorIndex)
                    }
                    onMouseLeave={hideTooltip}
                    style={{ cursor: 'pointer' }}
                  />
                  {/* Cell text */}
                  <text
                    x={x + cellWidth / 2}
                    y={y + cellHeight / 2}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill={isBest ? '#fff' : '#000'}
                    fontSize={12}
                    fontWeight={isBest ? 'bold' : 'normal'}
                    pointerEvents="none"
                  >
                    {showDelta
                      ? isBest
                        ? formatTime(value)
                        : formatDelta(delta)
                      : formatTime(value)}
                  </text>
                </g>
              )
            })
          )}

          {/* Axes */}
          <AxisBottom
            top={innerHeight}
            scale={xScale}
            stroke="#666"
            tickStroke="#666"
            tickLabelProps={() => ({
              fill: '#fff',
              fontSize: 12,
              textAnchor: 'middle',
              fontWeight: 'bold',
            })}
          />

          <AxisLeft
            scale={yScale}
            stroke="#666"
            tickStroke="#666"
            tickLabelProps={() => ({
              fill: '#fff',
              fontSize: 12,
              textAnchor: 'end',
              dy: '0.33em',
            })}
          />
        </Group>
      </svg>

      {/* Color scale legend */}
      <div
        style={{
          position: 'absolute',
          top: margin.top,
          right: 10,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '4px',
        }}
      >
        <span className="text-xs text-f1-gray">Fast</span>
        <div
          style={{
            width: '20px',
            height: '100px',
            background:
              'linear-gradient(to bottom, #1a9850, #91cf60, #d9ef8b, #fee08b, #fc8d59, #d73027)',
            borderRadius: '4px',
            border: '1px solid #333',
          }}
        />
        <span className="text-xs text-f1-gray">Slow</span>
      </div>

      {/* Tooltip */}
      {tooltipOpen && tooltipData && (
        <TooltipWithBounds
          top={tooltipTop}
          left={tooltipLeft}
          style={tooltipStyles}
        >
          <div className="space-y-1">
            <div className="font-semibold text-white">
              {tooltipData.driver} - {tooltipData.sector}
            </div>
            <div>Time: {formatTime(tooltipData.time)}</div>
            <div
              className={
                tooltipData.isBest
                  ? 'text-purple-400 font-bold'
                  : tooltipData.delta < 0.1
                    ? 'text-green-400'
                    : tooltipData.delta < 0.3
                      ? 'text-yellow-400'
                      : 'text-red-400'
              }
            >
              {tooltipData.isBest
                ? 'FASTEST'
                : `${formatDelta(tooltipData.delta)} from best`}
            </div>
          </div>
        </TooltipWithBounds>
      )}
    </div>
  )
}

// Responsive wrapper
export function SectorHeatmap({
  data,
  title,
  showDelta = false,
}: SectorHeatmapProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 bg-bg-secondary rounded-xl">
        <p className="text-f1-gray">No sector data available</p>
      </div>
    )
  }

  return (
    <div className="w-full">
      {title && <h4 className="text-white font-medium mb-4">{title}</h4>}
      <ParentSize>
        {({ width }) => (
          <SectorHeatmapChart
            data={data}
            width={width}
            height={Math.max(300, data.length * 45 + 80)}
            showDelta={showDelta}
          />
        )}
      </ParentSize>
    </div>
  )
}
