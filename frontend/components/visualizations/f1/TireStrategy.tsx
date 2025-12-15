'use client'

import { useMemo, useState, useCallback } from 'react'
import { Group } from '@visx/group'
import { Bar } from '@visx/shape'
import { scaleLinear, scaleBand, scaleOrdinal } from '@visx/scale'
import { AxisBottom, AxisLeft } from '@visx/axis'
import { useTooltip, TooltipWithBounds, defaultStyles } from '@visx/tooltip'
import { localPoint } from '@visx/event'
import { ParentSize } from '@visx/responsive'
import { LegendOrdinal } from '@visx/legend'

// Types for tire strategy data
interface StintData {
  driver: string
  stint: number
  compound: string
  startLap: number
  endLap: number
  totalLaps: number
  avgPace?: number
  color: string
}

interface TireStrategyProps {
  data: StintData[]
  title?: string
  maxLaps?: number
}

// F1 tire compound colors
const COMPOUND_COLORS: Record<string, string> = {
  SOFT: '#FF3333',
  MEDIUM: '#FFD700',
  HARD: '#EEEEEE',
  INTERMEDIATE: '#43B02A',
  WET: '#0067AD',
  UNKNOWN: '#888888',
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

// Inner chart component
function TireStrategyChart({
  data,
  width,
  height,
  maxLaps,
}: TireStrategyProps & { width: number; height: number }) {
  const {
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
    tooltipData,
    hideTooltip,
    showTooltip,
  } = useTooltip<StintData>()

  // Margins
  const margin = { top: 20, right: 120, bottom: 40, left: 80 }
  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  // Get unique drivers and compounds
  const drivers = useMemo(
    () => Array.from(new Set(data.map((d) => d.driver))),
    [data]
  )

  const compounds = useMemo(
    () => Array.from(new Set(data.map((d) => d.compound.toUpperCase()))),
    [data]
  )

  // Calculate max laps from data if not provided
  const totalLaps = useMemo(() => {
    if (maxLaps) return maxLaps
    return Math.max(...data.map((d) => d.endLap))
  }, [data, maxLaps])

  // Scales
  const xScale = scaleLinear({
    domain: [0, totalLaps],
    range: [0, innerWidth],
  })

  const yScale = scaleBand({
    domain: drivers,
    range: [0, innerHeight],
    padding: 0.3,
  })

  const colorScale = scaleOrdinal({
    domain: compounds,
    range: compounds.map((c) => COMPOUND_COLORS[c] || COMPOUND_COLORS.UNKNOWN),
  })

  // Tooltip handler
  const handleMouseMove = useCallback(
    (
      event: React.MouseEvent<SVGRectElement>,
      stint: StintData
    ) => {
      const point = localPoint(event) || { x: 0, y: 0 }
      showTooltip({
        tooltipData: stint,
        tooltipLeft: point.x,
        tooltipTop: point.y - 10,
      })
    },
    [showTooltip]
  )

  return (
    <div className="relative">
      <svg width={width} height={height}>
        <Group left={margin.left} top={margin.top}>
          {/* Background grid lines */}
          {xScale.ticks(10).map((tick) => (
            <line
              key={`grid-${tick}`}
              x1={xScale(tick)}
              x2={xScale(tick)}
              y1={0}
              y2={innerHeight}
              stroke="#333"
              strokeDasharray="2,2"
            />
          ))}

          {/* Stint bars */}
          {data.map((stint, i) => {
            const barWidth = xScale(stint.endLap) - xScale(stint.startLap)
            const barHeight = yScale.bandwidth()
            const x = xScale(stint.startLap)
            const y = yScale(stint.driver) || 0
            const compound = stint.compound.toUpperCase()

            return (
              <Bar
                key={`stint-${stint.driver}-${stint.stint}-${i}`}
                x={x}
                y={y}
                width={Math.max(barWidth, 2)}
                height={barHeight}
                fill={COMPOUND_COLORS[compound] || COMPOUND_COLORS.UNKNOWN}
                stroke="#000"
                strokeWidth={1}
                rx={4}
                opacity={0.9}
                onMouseMove={(e) => handleMouseMove(e, stint)}
                onMouseLeave={hideTooltip}
                style={{ cursor: 'pointer' }}
              />
            )
          })}

          {/* Pit stop indicators */}
          {data.map((stint, i) => {
            if (stint.stint === 1) return null
            const x = xScale(stint.startLap)
            const y = yScale(stint.driver) || 0
            const barHeight = yScale.bandwidth()

            return (
              <line
                key={`pit-${stint.driver}-${stint.stint}-${i}`}
                x1={x}
                x2={x}
                y1={y - 2}
                y2={y + barHeight + 2}
                stroke="#E10600"
                strokeWidth={2}
              />
            )
          })}

          {/* Axes */}
          <AxisBottom
            top={innerHeight}
            scale={xScale}
            stroke="#666"
            tickStroke="#666"
            tickLabelProps={() => ({
              fill: '#999',
              fontSize: 11,
              textAnchor: 'middle',
            })}
            label="Lap"
            labelProps={{
              fill: '#999',
              fontSize: 12,
              textAnchor: 'middle',
            }}
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

      {/* Legend */}
      <div
        style={{
          position: 'absolute',
          top: margin.top,
          right: 10,
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}
      >
        <LegendOrdinal
          scale={colorScale}
          direction="column"
          labelMargin="0 0 0 8px"
          shapeStyle={() => ({
            borderRadius: '4px',
          })}
          style={{
            fontSize: '11px',
            color: '#999',
          }}
        />
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
              {tooltipData.driver} - Stint {tooltipData.stint}
            </div>
            <div className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded"
                style={{
                  backgroundColor:
                    COMPOUND_COLORS[tooltipData.compound.toUpperCase()] ||
                    COMPOUND_COLORS.UNKNOWN,
                }}
              />
              <span>{tooltipData.compound}</span>
            </div>
            <div className="text-f1-gray">
              Laps {tooltipData.startLap} - {tooltipData.endLap} (
              {tooltipData.totalLaps} laps)
            </div>
            {tooltipData.avgPace && (
              <div className="text-f1-gray">
                Avg pace: {tooltipData.avgPace.toFixed(3)}s
              </div>
            )}
          </div>
        </TooltipWithBounds>
      )}
    </div>
  )
}

// Responsive wrapper
export function TireStrategy({ data, title, maxLaps }: TireStrategyProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 bg-bg-secondary rounded-xl">
        <p className="text-f1-gray">No tire strategy data available</p>
      </div>
    )
  }

  return (
    <div className="w-full">
      {title && <h4 className="text-white font-medium mb-4">{title}</h4>}
      <ParentSize>
        {({ width }) => (
          <TireStrategyChart
            data={data}
            width={width}
            height={Math.max(200, data.length * 40 + 100)}
            maxLaps={maxLaps}
          />
        )}
      </ParentSize>
    </div>
  )
}
