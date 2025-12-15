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
} from './f1'

interface ChartRendererProps {
  visualization: Visualization
}

// F1 team colors for charts
const CHART_COLORS = [
  '#E10600', // F1 Red
  '#3671C6', // Red Bull
  '#F91536', // Ferrari
  '#6CD3BF', // Mercedes
  '#F58020', // McLaren
  '#229971', // Aston Martin
  '#0093CC', // Alpine
  '#64C4FF', // Williams
]

export function ChartRenderer({ visualization }: ChartRendererProps) {
  const { type, data, config, title, drivers } = visualization

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 bg-bg-secondary rounded-xl">
        <p className="text-f1-gray">No data available</p>
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
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey={xKey} stroke="#949498" fontSize={12} />
            <YAxis stroke="#949498" fontSize={12} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1A1A1A',
                border: '1px solid #333',
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
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey={xKey} stroke="#949498" fontSize={12} />
            <YAxis stroke="#949498" fontSize={12} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1A1A1A',
                border: '1px solid #333',
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
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey={xKey} stroke="#949498" fontSize={12} />
            <YAxis stroke="#949498" fontSize={12} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1A1A1A',
                border: '1px solid #333',
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
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey={xKey} stroke="#949498" fontSize={12} name={xKey} />
            <YAxis dataKey={yKeys[0]} stroke="#949498" fontSize={12} name={yKeys[0]} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1A1A1A',
                border: '1px solid #333',
                borderRadius: '8px',
              }}
            />
            <Scatter data={data} fill={CHART_COLORS[0]} />
          </ScatterChart>
        )

      case 'table':
        return (
          <div className="overflow-auto max-h-[500px]">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-secondary">
                <tr>
                  {Object.keys(data[0]).map((key) => (
                    <th
                      key={key}
                      className="px-4 py-2 text-left text-f1-gray font-medium border-b border-white/10"
                    >
                      {key}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((row, i) => (
                  <tr key={i} className="hover:bg-bg-tertiary">
                    {Object.values(row).map((val, j) => (
                      <td
                        key={j}
                        className="px-4 py-2 text-white border-b border-white/5"
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

      default:
        return (
          <div className="flex items-center justify-center h-64 bg-bg-secondary rounded-xl">
            <p className="text-f1-gray">Unsupported chart type: {type}</p>
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
  ].includes(type)

  return (
    <div className="w-full">
      {!isF1Chart && title && (
        <h4 className="text-white font-medium mb-4">{title}</h4>
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
