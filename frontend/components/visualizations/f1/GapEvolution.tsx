'use client'

import { useMemo, useCallback, useState } from 'react'
import { Group } from '@visx/group'
import { LinePath, AreaClosed } from '@visx/shape'
import { curveMonotoneX } from '@visx/curve'
import { scaleLinear, scaleOrdinal } from '@visx/scale'
import { AxisBottom, AxisLeft } from '@visx/axis'
import { GridRows, GridColumns } from '@visx/grid'
import { useTooltip, TooltipWithBounds, defaultStyles } from '@visx/tooltip'
import { localPoint } from '@visx/event'
import { ParentSize } from '@visx/responsive'
import { LegendOrdinal } from '@visx/legend'
import { Brush } from '@visx/brush'
import { PatternLines } from '@visx/pattern'
import { bisector } from 'd3-array'

// Types
interface GapDataPoint {
  lap: number
  [driver: string]: number
}

interface GapEvolutionProps {
  data: GapDataPoint[]
  drivers: string[]
  title?: string
  colors?: Record<string, string>
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
const bisectLap = bisector<GapDataPoint, number>((d) => d.lap).left

function GapEvolutionChart({
  data,
  drivers,
  width,
  height,
  colors,
}: GapEvolutionProps & { width: number; height: number }) {
  const [brushDomain, setBrushDomain] = useState<[number, number] | null>(null)

  const {
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
    tooltipData,
    hideTooltip,
    showTooltip,
  } = useTooltip<{ lap: number; gaps: Record<string, number> }>()

  // Margins
  const margin = { top: 20, right: 120, bottom: 60, left: 60 }
  const brushHeight = 40
  const innerWidth = width - margin.left - margin.right
  const chartHeight = height - margin.top - margin.bottom - brushHeight - 20
  const brushTop = height - margin.bottom - brushHeight

  // Driver colors
  const driverColors = useMemo(() => {
    return { ...DEFAULT_DRIVER_COLORS, ...(colors || {}) }
  }, [colors])

  // Filter data based on brush selection
  const filteredData = useMemo(() => {
    if (!brushDomain) return data
    return data.filter(
      (d) => d.lap >= brushDomain[0] && d.lap <= brushDomain[1]
    )
  }, [data, brushDomain])

  // Scales for main chart
  const xScale = useMemo(
    () =>
      scaleLinear({
        domain: [
          Math.min(...filteredData.map((d) => d.lap)),
          Math.max(...filteredData.map((d) => d.lap)),
        ],
        range: [0, innerWidth],
      }),
    [filteredData, innerWidth]
  )

  const yScale = useMemo(() => {
    const allGaps = filteredData.flatMap((d) =>
      drivers.map((driver) => d[driver] as number).filter((v) => v !== undefined)
    )
    const minGap = Math.min(...allGaps, 0)
    const maxGap = Math.max(...allGaps, 0)
    const padding = (maxGap - minGap) * 0.1

    return scaleLinear({
      domain: [minGap - padding, maxGap + padding],
      range: [chartHeight, 0],
      nice: true,
    })
  }, [filteredData, drivers, chartHeight])

  // Scales for brush
  const brushXScale = scaleLinear({
    domain: [
      Math.min(...data.map((d) => d.lap)),
      Math.max(...data.map((d) => d.lap)),
    ],
    range: [0, innerWidth],
  })

  const brushYScale = useMemo(() => {
    const allGaps = data.flatMap((d) =>
      drivers.map((driver) => d[driver] as number).filter((v) => v !== undefined)
    )
    return scaleLinear({
      domain: [Math.min(...allGaps, 0), Math.max(...allGaps, 0)],
      range: [brushHeight, 0],
    })
  }, [data, drivers])

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

      const index = bisectLap(filteredData, lap, 1)
      const d0 = filteredData[index - 1]
      const d1 = filteredData[index]
      const d = d1 && lap - d0?.lap > d1.lap - lap ? d1 : d0

      if (d) {
        const gaps: Record<string, number> = {}
        drivers.forEach((driver) => {
          if (d[driver] !== undefined) {
            gaps[driver] = d[driver] as number
          }
        })

        showTooltip({
          tooltipData: { lap: d.lap, gaps },
          tooltipLeft: xScale(d.lap) + margin.left,
          tooltipTop: point.y,
        })
      }
    },
    [xScale, filteredData, drivers, margin.left, showTooltip]
  )

  // Brush handlers
  const onBrushChange = useCallback(
    (domain: { x0: number; x1: number } | null) => {
      if (!domain) {
        setBrushDomain(null)
        return
      }
      setBrushDomain([
        Math.round(brushXScale.invert(domain.x0)),
        Math.round(brushXScale.invert(domain.x1)),
      ])
    },
    [brushXScale]
  )

  return (
    <div className="relative">
      <svg width={width} height={height}>
        {/* Pattern for brush selection */}
        <PatternLines
          id="brush-pattern"
          height={8}
          width={8}
          stroke="#333"
          strokeWidth={1}
          orientation={['diagonal']}
        />

        {/* Main chart */}
        <Group left={margin.left} top={margin.top}>
          {/* Grid */}
          <GridRows
            scale={yScale}
            width={innerWidth}
            stroke="#333"
            strokeOpacity={0.5}
            strokeDasharray="2,2"
          />
          <GridColumns
            scale={xScale}
            height={chartHeight}
            stroke="#333"
            strokeOpacity={0.5}
            strokeDasharray="2,2"
          />

          {/* Zero line */}
          <line
            x1={0}
            x2={innerWidth}
            y1={yScale(0)}
            y2={yScale(0)}
            stroke="#666"
            strokeWidth={1}
          />

          {/* Gap lines for each driver */}
          {drivers.map((driver) => (
            <LinePath
              key={driver}
              data={filteredData.filter((d) => d[driver] !== undefined)}
              x={(d) => xScale(d.lap)}
              y={(d) => yScale(d[driver] as number)}
              stroke={driverColors[driver] || '#888888'}
              strokeWidth={2}
              curve={curveMonotoneX}
            />
          ))}

          {/* Axes */}
          <AxisBottom
            top={chartHeight}
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
              fill: '#999',
              fontSize: 11,
              textAnchor: 'end',
              dy: '0.33em',
            })}
            label="Gap to Leader (s)"
            labelProps={{
              fill: '#999',
              fontSize: 12,
              textAnchor: 'middle',
              transform: 'rotate(-90)',
            }}
            labelOffset={45}
          />

          {/* Invisible rect for tooltip */}
          <rect
            x={0}
            y={0}
            width={innerWidth}
            height={chartHeight}
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
              y2={chartHeight}
              stroke="#E10600"
              strokeWidth={1}
              strokeDasharray="4,4"
              pointerEvents="none"
            />
          )}
        </Group>

        {/* Brush area */}
        <Group left={margin.left} top={brushTop}>
          {/* Mini chart preview */}
          {drivers.map((driver) => (
            <LinePath
              key={`brush-${driver}`}
              data={data.filter((d) => d[driver] !== undefined)}
              x={(d) => brushXScale(d.lap)}
              y={(d) => brushYScale(d[driver] as number)}
              stroke={driverColors[driver] || '#888888'}
              strokeWidth={1}
              strokeOpacity={0.5}
              curve={curveMonotoneX}
            />
          ))}

          <Brush
            xScale={brushXScale}
            yScale={brushYScale}
            width={innerWidth}
            height={brushHeight}
            margin={{ top: 0, bottom: 0, left: 0, right: 0 }}
            handleSize={8}
            resizeTriggerAreas={['left', 'right']}
            brushDirection="horizontal"
            onChange={onBrushChange}
            selectedBoxStyle={{
              fill: 'url(#brush-pattern)',
              stroke: '#E10600',
            }}
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
            <div className="font-semibold text-white">Lap {tooltipData.lap}</div>
            {Object.entries(tooltipData.gaps)
              .sort((a, b) => a[1] - b[1])
              .map(([driver, gap]) => (
                <div key={driver} className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: driverColors[driver] || '#888' }}
                    />
                    <span>{driver}</span>
                  </div>
                  <span className={gap > 0 ? 'text-f1-gray' : 'text-green-400'}>
                    {gap > 0 ? '+' : ''}
                    {gap.toFixed(3)}s
                  </span>
                </div>
              ))}
          </div>
        </TooltipWithBounds>
      )}
    </div>
  )
}

// Responsive wrapper
export function GapEvolution({ data, drivers, title, colors }: GapEvolutionProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 bg-bg-secondary rounded-xl">
        <p className="text-f1-gray">No gap data available</p>
      </div>
    )
  }

  return (
    <div className="w-full">
      {title && <h4 className="text-white font-medium mb-4">{title}</h4>}
      <ParentSize>
        {({ width }) => (
          <GapEvolutionChart
            data={data}
            drivers={drivers}
            width={width}
            height={400}
            colors={colors}
          />
        )}
      </ParentSize>
      <p className="text-xs text-f1-gray mt-2 text-center">
        Drag on the bottom area to zoom into specific laps
      </p>
    </div>
  )
}
