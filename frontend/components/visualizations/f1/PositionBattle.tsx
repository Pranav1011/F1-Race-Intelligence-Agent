'use client'

import { useMemo, useCallback } from 'react'
import { Group } from '@visx/group'
import { LinePath, Circle } from '@visx/shape'
import { curveMonotoneX } from '@visx/curve'
import { scaleLinear, scaleOrdinal } from '@visx/scale'
import { AxisBottom, AxisLeft } from '@visx/axis'
import { GridRows, GridColumns } from '@visx/grid'
import { useTooltip, TooltipWithBounds, defaultStyles } from '@visx/tooltip'
import { localPoint } from '@visx/event'
import { ParentSize } from '@visx/responsive'
import { LegendOrdinal } from '@visx/legend'
import { bisector } from 'd3-array'

// Types
interface PositionDataPoint {
  lap: number
  [driver: string]: number
}

interface PositionBattleProps {
  data: PositionDataPoint[]
  drivers: string[]
  title?: string
  colors?: Record<string, string>
  highlightOvertakes?: boolean
}

// Default F1 driver colors
const DEFAULT_DRIVER_COLORS: Record<string, string> = {
  VER: '#3671C6',
  PER: '#3671C6',
  HAM: '#6CD3BF',
  RUS: '#6CD3BF',
  LEC: '#F91536',
  SAI: '#F91536',
  NOR: '#F58020',
  PIA: '#F58020',
  ALO: '#229971',
  STR: '#229971',
  GAS: '#0093CC',
  OCO: '#0093CC',
  ALB: '#64C4FF',
  SAR: '#64C4FF',
  BOT: '#C92D4B',
  ZHO: '#C92D4B',
  MAG: '#B6BABD',
  HUL: '#B6BABD',
  TSU: '#6692FF',
  RIC: '#6692FF',
  LAW: '#6692FF',
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

// Bisector for finding closest data point
const bisectLap = bisector<PositionDataPoint, number>((d) => d.lap).left

// Detect overtakes
interface Overtake {
  lap: number
  overtaker: string
  overtaken: string
  newPosition: number
}

function detectOvertakes(
  data: PositionDataPoint[],
  drivers: string[]
): Overtake[] {
  const overtakes: Overtake[] = []

  for (let i = 1; i < data.length; i++) {
    const prevLap = data[i - 1]
    const currLap = data[i]

    for (const driver of drivers) {
      const prevPos = prevLap[driver] as number
      const currPos = currLap[driver] as number

      if (prevPos && currPos && currPos < prevPos) {
        // Driver gained position(s)
        for (const otherDriver of drivers) {
          if (otherDriver === driver) continue
          const otherPrevPos = prevLap[otherDriver] as number
          const otherCurrPos = currLap[otherDriver] as number

          // Check if positions swapped
          if (
            otherPrevPos < prevPos &&
            otherCurrPos > currPos &&
            currPos === otherPrevPos
          ) {
            overtakes.push({
              lap: currLap.lap,
              overtaker: driver,
              overtaken: otherDriver,
              newPosition: currPos,
            })
          }
        }
      }
    }
  }

  return overtakes
}

function PositionBattleChart({
  data,
  drivers,
  width,
  height,
  colors,
  highlightOvertakes = true,
}: PositionBattleProps & { width: number; height: number }) {
  const {
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
    tooltipData,
    hideTooltip,
    showTooltip,
  } = useTooltip<{
    lap: number
    positions: Record<string, number>
    overtake?: Overtake
  }>()

  // Margins
  const margin = { top: 20, right: 120, bottom: 50, left: 60 }
  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  // Driver colors
  const driverColors = useMemo(() => {
    return { ...DEFAULT_DRIVER_COLORS, ...(colors || {}) }
  }, [colors])

  // Detect overtakes
  const overtakes = useMemo(
    () => (highlightOvertakes ? detectOvertakes(data, drivers) : []),
    [data, drivers, highlightOvertakes]
  )

  // Scales
  const xScale = useMemo(
    () =>
      scaleLinear({
        domain: [
          Math.min(...data.map((d) => d.lap)),
          Math.max(...data.map((d) => d.lap)),
        ],
        range: [0, innerWidth],
      }),
    [data, innerWidth]
  )

  const yScale = useMemo(() => {
    const allPositions = data.flatMap((d) =>
      drivers.map((driver) => d[driver] as number).filter((v) => v !== undefined)
    )
    const maxPos = Math.max(...allPositions, 20)

    return scaleLinear({
      domain: [1, maxPos],
      range: [0, innerHeight],
    })
  }, [data, drivers, innerHeight])

  const colorScale = scaleOrdinal({
    domain: drivers,
    range: drivers.map((d) => driverColors[d] || '#888888'),
  })

  // Tooltip handler
  const handleTooltip = useCallback(
    (event: React.MouseEvent<SVGRectElement>) => {
      const point = localPoint(event) || { x: 0, y: 0 }
      const x = point.x - margin.left
      const lap = Math.round(xScale.invert(x))

      const index = bisectLap(data, lap, 1)
      const d0 = data[index - 1]
      const d1 = data[index]
      const d = d1 && lap - d0?.lap > d1.lap - lap ? d1 : d0

      if (d) {
        const positions: Record<string, number> = {}
        drivers.forEach((driver) => {
          if (d[driver] !== undefined) {
            positions[driver] = d[driver] as number
          }
        })

        // Check for overtake on this lap
        const overtake = overtakes.find((o) => o.lap === d.lap)

        showTooltip({
          tooltipData: { lap: d.lap, positions, overtake },
          tooltipLeft: xScale(d.lap) + margin.left,
          tooltipTop: point.y,
        })
      }
    },
    [xScale, data, drivers, overtakes, margin.left, showTooltip]
  )

  return (
    <div className="relative">
      <svg width={width} height={height}>
        <Group left={margin.left} top={margin.top}>
          {/* Grid */}
          <GridRows
            scale={yScale}
            width={innerWidth}
            stroke="#333"
            strokeOpacity={0.3}
            strokeDasharray="2,2"
          />
          <GridColumns
            scale={xScale}
            height={innerHeight}
            stroke="#333"
            strokeOpacity={0.3}
            strokeDasharray="2,2"
          />

          {/* Position lines for each driver */}
          {drivers.map((driver) => (
            <LinePath
              key={driver}
              data={data.filter((d) => d[driver] !== undefined)}
              x={(d) => xScale(d.lap)}
              y={(d) => yScale(d[driver] as number)}
              stroke={driverColors[driver] || '#888888'}
              strokeWidth={2.5}
              curve={curveMonotoneX}
            />
          ))}

          {/* Overtake markers */}
          {highlightOvertakes &&
            overtakes.map((overtake, i) => (
              <Circle
                key={`overtake-${i}`}
                cx={xScale(overtake.lap)}
                cy={yScale(overtake.newPosition)}
                r={6}
                fill="#E10600"
                stroke="#fff"
                strokeWidth={2}
                opacity={0.9}
              />
            ))}

          {/* Start position markers */}
          {drivers.map((driver) => {
            const firstData = data.find((d) => d[driver] !== undefined)
            if (!firstData) return null
            return (
              <Circle
                key={`start-${driver}`}
                cx={xScale(firstData.lap)}
                cy={yScale(firstData[driver] as number)}
                r={4}
                fill={driverColors[driver] || '#888888'}
                stroke="#000"
                strokeWidth={1}
              />
            )
          })}

          {/* End position markers */}
          {drivers.map((driver) => {
            const lastData = [...data]
              .reverse()
              .find((d) => d[driver] !== undefined)
            if (!lastData) return null
            return (
              <Circle
                key={`end-${driver}`}
                cx={xScale(lastData.lap)}
                cy={yScale(lastData[driver] as number)}
                r={4}
                fill={driverColors[driver] || '#888888'}
                stroke="#fff"
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
            tickValues={[1, 3, 5, 10, 15, 20]}
            tickLabelProps={() => ({
              fill: '#999',
              fontSize: 11,
              textAnchor: 'end',
              dy: '0.33em',
            })}
            label="Position"
            labelProps={{
              fill: '#999',
              fontSize: 12,
              textAnchor: 'middle',
              transform: 'rotate(-90)',
            }}
            labelOffset={40}
          />

          {/* Invisible rect for tooltip */}
          <rect
            x={0}
            y={0}
            width={innerWidth}
            height={innerHeight}
            fill="transparent"
            onMouseMove={handleTooltip}
            onMouseLeave={hideTooltip}
          />

          {/* Tooltip vertical line */}
          {tooltipOpen && tooltipData && (
            <line
              x1={xScale(tooltipData.lap)}
              x2={xScale(tooltipData.lap)}
              y1={0}
              y2={innerHeight}
              stroke="#E10600"
              strokeWidth={1}
              strokeDasharray="4,4"
              pointerEvents="none"
            />
          )}
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
          style={{
            fontSize: '11px',
            color: '#999',
          }}
        />
        {highlightOvertakes && overtakes.length > 0 && (
          <div className="flex items-center gap-2 mt-2 text-xs text-f1-gray">
            <span className="w-3 h-3 rounded-full bg-f1-red" />
            <span>Overtake</span>
          </div>
        )}
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
              Lap {tooltipData.lap}
            </div>
            {tooltipData.overtake && (
              <div className="text-f1-red text-xs mb-2 pb-2 border-b border-white/10">
                {tooltipData.overtake.overtaker} overtook{' '}
                {tooltipData.overtake.overtaken} for P
                {tooltipData.overtake.newPosition}
              </div>
            )}
            {Object.entries(tooltipData.positions)
              .sort((a, b) => a[1] - b[1])
              .map(([driver, position]) => (
                <div
                  key={driver}
                  className="flex items-center justify-between gap-4"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{
                        backgroundColor: driverColors[driver] || '#888',
                      }}
                    />
                    <span>{driver}</span>
                  </div>
                  <span className="text-white font-medium">P{position}</span>
                </div>
              ))}
          </div>
        </TooltipWithBounds>
      )}
    </div>
  )
}

// Responsive wrapper
export function PositionBattle({
  data,
  drivers,
  title,
  colors,
  highlightOvertakes = true,
}: PositionBattleProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 bg-bg-secondary rounded-xl">
        <p className="text-f1-gray">No position data available</p>
      </div>
    )
  }

  return (
    <div className="w-full">
      {title && <h4 className="text-white font-medium mb-4">{title}</h4>}
      <ParentSize>
        {({ width }) => (
          <PositionBattleChart
            data={data}
            drivers={drivers}
            width={width}
            height={400}
            colors={colors}
            highlightOvertakes={highlightOvertakes}
          />
        )}
      </ParentSize>
    </div>
  )
}
