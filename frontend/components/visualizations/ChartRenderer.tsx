'use client'

import { useMemo } from 'react'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  ScatterChart,
  Scatter,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { Visualization } from '@/types'
import {
  TireStrategy,
  GapEvolution,
  PositionBattle,
  SectorHeatmap,
  RaceProgressChart,
  LapTimeComparison,
} from './f1'

interface ChartRendererProps {
  visualization: Visualization
}

// F1 team colors for charts
const CHART_COLORS = [
  '#E31937', // F1 Red
  '#3671C6', // Red Bull
  '#F91536', // Ferrari
  '#6CD3BF', // Mercedes
  '#F58020', // McLaren
  '#229971', // Aston Martin
  '#0093CC', // Alpine
  '#64C4FF', // Williams
]

// Chart theme colors
const CHART_THEME = {
  background: '#16161E',
  gridColor: '#2A2A35',
  textColor: '#A1A1AA',
  tooltipBg: '#12121A',
  tooltipBorder: '#2A2A35',
}

export function ChartRenderer({ visualization }: ChartRendererProps) {
  const { type, data, config, title, drivers } = visualization

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 bg-surface rounded-xl border border-white/5">
        <p className="text-text-muted">No data available</p>
      </div>
    )
  }

  const xKey = config?.xAxis || Object.keys(data[0])[0]
  const yKeys = config?.yAxis
    ? Array.isArray(config.yAxis)
      ? config.yAxis
      : [config.yAxis]
    : Object.keys(data[0]).filter((k) => k !== xKey)

  const renderChart = () => {
    switch (type) {
      case 'line':
        return (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.gridColor} />
            <XAxis dataKey={xKey} stroke={CHART_THEME.textColor} fontSize={12} />
            <YAxis stroke={CHART_THEME.textColor} fontSize={12} />
            <Tooltip
              contentStyle={{
                backgroundColor: CHART_THEME.tooltipBg,
                border: `1px solid ${CHART_THEME.tooltipBorder}`,
                borderRadius: '8px',
              }}
            />
            {config?.legend !== false && <Legend />}
            {yKeys.map((key, i) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={CHART_COLORS[i % CHART_COLORS.length]}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        )

      case 'bar':
        return (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.gridColor} />
            <XAxis dataKey={xKey} stroke={CHART_THEME.textColor} fontSize={12} />
            <YAxis stroke={CHART_THEME.textColor} fontSize={12} />
            <Tooltip
              contentStyle={{
                backgroundColor: CHART_THEME.tooltipBg,
                border: `1px solid ${CHART_THEME.tooltipBorder}`,
                borderRadius: '8px',
              }}
            />
            {config?.legend !== false && <Legend />}
            {yKeys.map((key, i) => (
              <Bar
                key={key}
                dataKey={key}
                fill={CHART_COLORS[i % CHART_COLORS.length]}
              />
            ))}
          </BarChart>
        )

      case 'area':
        return (
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.gridColor} />
            <XAxis dataKey={xKey} stroke={CHART_THEME.textColor} fontSize={12} />
            <YAxis stroke={CHART_THEME.textColor} fontSize={12} />
            <Tooltip
              contentStyle={{
                backgroundColor: CHART_THEME.tooltipBg,
                border: `1px solid ${CHART_THEME.tooltipBorder}`,
                borderRadius: '8px',
              }}
            />
            {config?.legend !== false && <Legend />}
            {yKeys.map((key, i) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stroke={CHART_COLORS[i % CHART_COLORS.length]}
                fill={CHART_COLORS[i % CHART_COLORS.length]}
                fillOpacity={0.3}
              />
            ))}
          </AreaChart>
        )

      case 'scatter':
        return (
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.gridColor} />
            <XAxis dataKey={xKey} stroke={CHART_THEME.textColor} fontSize={12} name={xKey} />
            <YAxis dataKey={yKeys[0]} stroke={CHART_THEME.textColor} fontSize={12} name={yKeys[0]} />
            <Tooltip
              contentStyle={{
                backgroundColor: CHART_THEME.tooltipBg,
                border: `1px solid ${CHART_THEME.tooltipBorder}`,
                borderRadius: '8px',
              }}
            />
            <Scatter data={data} fill={CHART_COLORS[0]} />
          </ScatterChart>
        )

      case 'table':
        return (
          <div className="overflow-auto max-h-[500px] rounded-lg border border-white/5">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface">
                <tr>
                  {Object.keys(data[0]).map((key) => (
                    <th
                      key={key}
                      className="px-4 py-3 text-left text-text-secondary font-medium border-b border-white/10"
                    >
                      {key}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((row, i) => (
                  <tr key={i} className="hover:bg-surface-hover transition-colors">
                    {Object.values(row).map((val, j) => (
                      <td
                        key={j}
                        className="px-4 py-3 text-text-primary border-b border-white/5"
                      >
                        {String(val)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )

      // F1-specific chart types using Visx
      case 'tire_strategy':
        return (
          <TireStrategy
            data={data as any}
            title={title}
            maxLaps={config?.maxLaps}
          />
        )

      case 'gap_evolution':
        return (
          <GapEvolution
            data={data as any}
            drivers={drivers || []}
            title={title}
            colors={config?.colors as Record<string, string>}
          />
        )

      case 'position_battle':
        return (
          <PositionBattle
            data={data as any}
            drivers={drivers || []}
            title={title}
            colors={config?.colors as Record<string, string>}
            highlightOvertakes={config?.highlightOvertakes ?? true}
          />
        )

      case 'sector_heatmap':
        return (
          <SectorHeatmap
            data={data as any}
            title={title}
            showDelta={config?.showDelta}
          />
        )

      case 'race_progress':
        return (
          <RaceProgressChart
            data={data as any}
            drivers={drivers || []}
            totalLaps={config?.totalLaps || 50}
            title={title}
          />
        )

      case 'lap_comparison':
      case 'lap_time_comparison':
        return (
          <LapTimeComparison
            data={data as any}
            drivers={drivers || []}
            title={title}
            showDelta={config?.showDelta}
          />
        )

      case 'delta_line':
        // Delta/gap evolution line chart
        return (
          <div className="w-full p-4">
            <h4 className="text-text-primary font-semibold mb-4 text-center">{title || 'Gap Evolution'}</h4>
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.gridColor} />
                  <XAxis
                    dataKey="lap"
                    tick={{ fill: CHART_THEME.textColor, fontSize: 12 }}
                    axisLine={{ stroke: CHART_THEME.gridColor }}
                    label={{ value: 'Lap', position: 'bottom', fill: CHART_THEME.textColor }}
                  />
                  <YAxis
                    tick={{ fill: CHART_THEME.textColor, fontSize: 12 }}
                    axisLine={{ stroke: CHART_THEME.gridColor }}
                    tickFormatter={(value) => `${value > 0 ? '+' : ''}${value.toFixed(1)}s`}
                    label={{ value: 'Delta (s)', angle: -90, position: 'insideLeft', fill: CHART_THEME.textColor }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: CHART_THEME.tooltipBg,
                      border: `1px solid ${CHART_THEME.tooltipBorder}`,
                      borderRadius: '8px',
                      color: CHART_THEME.textColor,
                    }}
                    formatter={(value: number, name: string) => {
                      const label = name === 'cumulative_delta' ? 'Total Gap' : 'Lap Delta'
                      return [`${value > 0 ? '+' : ''}${value.toFixed(3)}s`, label]
                    }}
                  />
                  <Legend />
                  {/* Reference line at 0 */}
                  <Area
                    type="monotone"
                    dataKey="cumulative_delta"
                    stroke="#E31937"
                    fill="#E31937"
                    fillOpacity={0.2}
                    strokeWidth={2}
                    name="Cumulative Gap"
                  />
                  <Line
                    type="monotone"
                    dataKey="lap_delta"
                    stroke="#3671C6"
                    strokeWidth={1.5}
                    dot={false}
                    name="Per-Lap Delta"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-2 text-center text-xs text-text-muted">
              Positive = {config?.referenceDriver || drivers?.[0]} faster
            </div>
          </div>
        )

      case 'box_plot':
        // Box plot for lap time distribution
        return (
          <div className="w-full p-4">
            <h4 className="text-text-primary font-semibold mb-4 text-center">{title || 'Lap Time Distribution'}</h4>
            <div className="flex justify-center gap-8 flex-wrap">
              {data.map((d: any) => (
                <div key={d.driver} className="flex flex-col items-center">
                  <div className="text-sm font-medium text-text-primary mb-2">{d.driver}</div>
                  <svg width="80" height="200" className="overflow-visible">
                    {/* Box plot visualization */}
                    {d.min && d.max && d.q1 && d.q3 && d.median && (() => {
                      const scale = (val: number) => 180 - ((val - d.min) / (d.max - d.min)) * 160
                      return (
                        <>
                          {/* Whisker line */}
                          <line x1="40" y1={scale(d.min)} x2="40" y2={scale(d.max)} stroke={d.color || '#888'} strokeWidth="1" />
                          {/* Min whisker */}
                          <line x1="30" y1={scale(d.min)} x2="50" y2={scale(d.min)} stroke={d.color || '#888'} strokeWidth="2" />
                          {/* Max whisker */}
                          <line x1="30" y1={scale(d.max)} x2="50" y2={scale(d.max)} stroke={d.color || '#888'} strokeWidth="2" />
                          {/* Box */}
                          <rect
                            x="20"
                            y={scale(d.q3)}
                            width="40"
                            height={scale(d.q1) - scale(d.q3)}
                            fill={d.color || '#888'}
                            fillOpacity="0.3"
                            stroke={d.color || '#888'}
                            strokeWidth="2"
                            rx="4"
                          />
                          {/* Median line */}
                          <line x1="20" y1={scale(d.median)} x2="60" y2={scale(d.median)} stroke={d.color || '#888'} strokeWidth="3" />
                          {/* Mean dot */}
                          <circle cx="40" cy={scale(d.mean)} r="4" fill="white" stroke={d.color || '#888'} strokeWidth="2" />
                        </>
                      )
                    })()}
                  </svg>
                  <div className="text-xs text-text-muted mt-1 space-y-0.5 text-center">
                    <div>Min: {d.min?.toFixed(2)}s</div>
                    <div>Med: {d.median?.toFixed(2)}s</div>
                    <div>Max: {d.max?.toFixed(2)}s</div>
                    <div className="text-text-secondary">{d.count} laps</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

      case 'histogram':
        // Histogram for lap time frequency
        return (
          <div className="w-full p-4">
            <h4 className="text-text-primary font-semibold mb-4 text-center">{title || 'Lap Time Distribution'}</h4>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} margin={{ top: 10, right: 30, left: 10, bottom: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.gridColor} />
                  <XAxis
                    dataKey="bin"
                    tick={{ fill: CHART_THEME.textColor, fontSize: 10 }}
                    axisLine={{ stroke: CHART_THEME.gridColor }}
                    angle={-45}
                    textAnchor="end"
                    height={60}
                  />
                  <YAxis
                    tick={{ fill: CHART_THEME.textColor, fontSize: 12 }}
                    axisLine={{ stroke: CHART_THEME.gridColor }}
                    label={{ value: 'Frequency', angle: -90, position: 'insideLeft', fill: CHART_THEME.textColor }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: CHART_THEME.tooltipBg,
                      border: `1px solid ${CHART_THEME.tooltipBorder}`,
                      borderRadius: '8px',
                      color: CHART_THEME.textColor,
                    }}
                  />
                  <Legend />
                  {(drivers || []).map((driver, idx) => (
                    <Bar
                      key={driver}
                      dataKey={driver}
                      fill={(config?.colors as Record<string, string>)?.[driver] || CHART_COLORS[idx % CHART_COLORS.length]}
                      fillOpacity={0.8}
                      name={driver}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )

      case 'violin_plot':
        // Simplified violin plot (using distribution points)
        return (
          <div className="w-full p-4">
            <h4 className="text-text-primary font-semibold mb-4 text-center">{title || 'Pace Distribution'}</h4>
            <div className="flex justify-center gap-8 flex-wrap">
              {data.map((d: any) => {
                const values = d.values || []
                if (values.length === 0) return null
                const min = d.min
                const max = d.max
                const range = max - min || 1

                // Create density histogram for violin shape
                const bins = 20
                const binWidth = range / bins
                const histogram: number[] = Array(bins).fill(0)
                values.forEach((v: number) => {
                  const binIdx = Math.min(Math.floor((v - min) / binWidth), bins - 1)
                  histogram[binIdx]++
                })
                const maxCount = Math.max(...histogram)

                return (
                  <div key={d.driver} className="flex flex-col items-center">
                    <div className="text-sm font-medium text-text-primary mb-2">{d.driver}</div>
                    <svg width="100" height="200" className="overflow-visible">
                      {/* Violin shape */}
                      <path
                        d={histogram.map((count, i) => {
                          const y = 180 - (i / bins) * 160
                          const width = (count / maxCount) * 35
                          return `${i === 0 ? 'M' : 'L'} ${50 - width} ${y}`
                        }).join(' ') + histogram.map((count, i) => {
                          const y = 180 - ((bins - 1 - i) / bins) * 160
                          const width = (histogram[bins - 1 - i] / maxCount) * 35
                          return `L ${50 + width} ${y}`
                        }).join(' ') + ' Z'}
                        fill={d.color || '#888'}
                        fillOpacity="0.3"
                        stroke={d.color || '#888'}
                        strokeWidth="2"
                      />
                      {/* Median line */}
                      <line
                        x1="30"
                        y1={180 - ((d.median - min) / range) * 160}
                        x2="70"
                        y2={180 - ((d.median - min) / range) * 160}
                        stroke={d.color || '#888'}
                        strokeWidth="3"
                      />
                      {/* Mean dot */}
                      <circle
                        cx="50"
                        cy={180 - ((d.mean - min) / range) * 160}
                        r="4"
                        fill="white"
                        stroke={d.color || '#888'}
                        strokeWidth="2"
                      />
                    </svg>
                    <div className="text-xs text-text-muted mt-1 space-y-0.5 text-center">
                      <div>Min: {d.min?.toFixed(2)}s</div>
                      <div>Med: {d.median?.toFixed(2)}s</div>
                      <div>Max: {d.max?.toFixed(2)}s</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )

      case 'bar_chart':
      case 'bar':
        // Driver comparison bar chart
        const barColors = config?.colors as Record<string, string> || {}
        const barDrivers = drivers || []
        return (
          <div className="w-full p-4">
            <h4 className="text-text-primary font-semibold mb-4 text-center">{title || 'Driver Comparison'}</h4>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={data}
                  layout="vertical"
                  margin={{ top: 10, right: 30, left: 80, bottom: 10 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.gridColor} horizontal={true} vertical={false} />
                  <XAxis
                    type="number"
                    tick={{ fill: CHART_THEME.textColor, fontSize: 12 }}
                    axisLine={{ stroke: CHART_THEME.gridColor }}
                    tickLine={{ stroke: CHART_THEME.gridColor }}
                    domain={['dataMin - 1', 'dataMax + 1']}
                    tickFormatter={(value) => `${value.toFixed(1)}s`}
                  />
                  <YAxis
                    type="category"
                    dataKey="metric"
                    tick={{ fill: CHART_THEME.textColor, fontSize: 12 }}
                    axisLine={{ stroke: CHART_THEME.gridColor }}
                    tickLine={{ stroke: CHART_THEME.gridColor }}
                    width={75}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: CHART_THEME.tooltipBg,
                      border: `1px solid ${CHART_THEME.tooltipBorder}`,
                      borderRadius: '8px',
                      color: CHART_THEME.textColor,
                    }}
                    formatter={(value: number, name: string) => [`${value.toFixed(3)}s`, name]}
                  />
                  <Legend
                    wrapperStyle={{ color: CHART_THEME.textColor }}
                  />
                  {barDrivers.map((driver, index) => (
                    <Bar
                      key={driver}
                      dataKey={driver}
                      fill={barColors[driver] || CHART_COLORS[index % CHART_COLORS.length]}
                      radius={[0, 4, 4, 0]}
                      name={driver}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
            {/* Driver stats summary */}
            {config?.driverStats && (
              <div className="mt-4 grid grid-cols-2 gap-4">
                {barDrivers.map((driver) => {
                  const stats = (config.driverStats as Record<string, any>)?.[driver]
                  if (!stats) return null
                  return (
                    <div
                      key={driver}
                      className="p-3 rounded-lg bg-surface border border-white/5"
                      style={{ borderLeftColor: barColors[driver] || CHART_COLORS[0], borderLeftWidth: '3px' }}
                    >
                      <div className="text-sm font-semibold text-text-primary mb-2">{driver}</div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        {stats.total_laps && (
                          <div>
                            <span className="text-text-muted">Laps: </span>
                            <span className="text-text-secondary">{stats.total_laps}</span>
                          </div>
                        )}
                        {stats.average_pace && (
                          <div>
                            <span className="text-text-muted">Avg: </span>
                            <span className="text-text-secondary">{stats.average_pace.toFixed(3)}s</span>
                          </div>
                        )}
                        {stats.fastest_lap && (
                          <div>
                            <span className="text-text-muted">Best: </span>
                            <span className="text-text-secondary">{stats.fastest_lap.toFixed(3)}s</span>
                          </div>
                        )}
                        {stats.consistency !== undefined && (
                          <div>
                            <span className="text-text-muted">σ: </span>
                            <span className="text-text-secondary">{stats.consistency.toFixed(3)}s</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )

      default:
        return (
          <div className="flex items-center justify-center h-64 bg-surface rounded-xl border border-white/5">
            <p className="text-text-muted">Unsupported chart type: {type}</p>
          </div>
        )
    }
  }

  // F1 charts handle their own responsive sizing
  const isF1Chart = [
    'tire_strategy',
    'gap_evolution',
    'position_battle',
    'sector_heatmap',
    'race_progress',
    'lap_comparison',
    'lap_time_comparison',
  ].includes(type)

  return (
    <div className="w-full">
      {!isF1Chart && title && (
        <h4 className="text-text-primary font-medium mb-4">{title}</h4>
      )}
      {type === 'table' || isF1Chart ? (
        renderChart()
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          {renderChart()}
        </ResponsiveContainer>
      )}
    </div>
  )
}
