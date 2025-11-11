import React from 'react';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from 'recharts';
import clsx from 'clsx';

interface DataPoint {
  name: string;
  risk_reward: number;
  win_rate: number;
  phase: 'I' | 'II' | 'III';
  trades: number;
}

interface ParetoScatterChartProps {
  data: DataPoint[];
  height?: number;
  targetWinRate?: number;
  targetRR?: number;
  className?: string;
}

export const ParetoScatterChart: React.FC<ParetoScatterChartProps> = ({
  data,
  height = 400,
  targetWinRate = 65,
  targetRR = 2.0,
  className,
}) => {
  // Group data by phase
  const phaseData = {
    I: data.filter((d) => d.phase === 'I'),
    II: data.filter((d) => d.phase === 'II'),
    III: data.filter((d) => d.phase === 'III'),
  };

  const phaseColors = {
    I: '#007AFF',
    II: '#D4AF37',
    III: '#34C759',
  };

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload[0]) {
      const data = payload[0].payload;
      return (
        <div className="glass-strong rounded-ios p-3 shadow-ios">
          <p className="text-headline text-gray-900 dark:text-gray-50 mb-1">
            {data.name}
          </p>
          <div className="space-y-1">
            <p className="text-caption">
              <span className="text-gray-500 dark:text-gray-400">Phase:</span>{' '}
              <span className={clsx(
                'font-semibold',
                data.phase === 'I' && 'text-ios-blue',
                data.phase === 'II' && 'text-gold',
                data.phase === 'III' && 'text-ios-green'
              )}>
                {data.phase}
              </span>
            </p>
            <p className="text-caption">
              <span className="text-gray-500 dark:text-gray-400">Win Rate:</span>{' '}
              <span className="font-semibold">{data.win_rate}%</span>
            </p>
            <p className="text-caption">
              <span className="text-gray-500 dark:text-gray-400">R/R:</span>{' '}
              <span className="font-semibold">{data.risk_reward.toFixed(2)}</span>
            </p>
            <p className="text-caption">
              <span className="text-gray-500 dark:text-gray-400">Trades:</span>{' '}
              <span className="font-semibold">{data.trades}</span>
            </p>
          </div>
        </div>
      );
    }
    return null;
  };

  const CustomLegend = () => {
    return (
      <div className="flex items-center justify-center gap-4 mt-4">
        {Object.entries(phaseColors).map(([phase, color]) => (
          <div key={phase} className="flex items-center gap-1.5">
            <div
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="text-caption text-gray-600 dark:text-gray-300">
              Phase {phase}
            </span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className={clsx('card-ios p-5', className)}>
      <div className="mb-4">
        <h3 className="text-headline text-gray-900 dark:text-gray-50 mb-1">
          Strategy Performance Distribution
        </h3>
        <p className="text-caption text-gray-500 dark:text-gray-400">
          Higher and further right = Better performance
        </p>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 20, right: 20, bottom: 60, left: 20 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="#E5E5EA"
            className="dark:stroke-gray-800"
            opacity={0.5}
          />

          <XAxis
            type="number"
            dataKey="risk_reward"
            name="Risk/Reward"
            domain={[0, 'dataMax + 0.5']}
            label={{
              value: 'Risk/Reward Ratio',
              position: 'insideBottom',
              offset: -10,
              style: { fontSize: 12, fill: '#8E8E93' },
            }}
            stroke="#8E8E93"
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
          />

          <YAxis
            type="number"
            dataKey="win_rate"
            name="Win Rate"
            domain={[0, 100]}
            label={{
              value: 'Win Rate (%)',
              angle: -90,
              position: 'insideLeft',
              style: { fontSize: 12, fill: '#8E8E93', textAnchor: 'middle' },
            }}
            stroke="#8E8E93"
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
          />

          <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: '3 3' }} />

          {/* Target lines */}
          <ReferenceLine
            y={targetWinRate}
            stroke="#00b67a"
            strokeDasharray="5 5"
            strokeOpacity={0.5}
            label={{
              value: `Target WR: ${targetWinRate}%`,
              position: 'right',
              style: { fontSize: 10, fill: '#00b67a' },
            }}
          />

          <ReferenceLine
            x={targetRR}
            stroke="#00b67a"
            strokeDasharray="5 5"
            strokeOpacity={0.5}
            label={{
              value: `Target R/R: ${targetRR}`,
              position: 'top',
              style: { fontSize: 10, fill: '#00b67a' },
            }}
          />

          {/* Render scatter points for each phase */}
          {Object.entries(phaseData).map(([phase, points]) => (
            <Scatter
              key={phase}
              name={`Phase ${phase}`}
              data={points}
              fill={phaseColors[phase as keyof typeof phaseColors]}
              fillOpacity={0.8}
            />
          ))}

          <Legend content={<CustomLegend />} />
        </ScatterChart>
      </ResponsiveContainer>

      {/* Quadrant labels */}
      <div className="grid grid-cols-2 gap-2 mt-4">
        <div className="glass rounded-ios p-2 text-center">
          <p className="text-caption text-gray-500 dark:text-gray-400">
            Low R/R, Low WR
          </p>
          <p className="text-caption font-medium text-danger">Poor</p>
        </div>
        <div className="glass rounded-ios p-2 text-center">
          <p className="text-caption text-gray-500 dark:text-gray-400">
            High R/R, Low WR
          </p>
          <p className="text-caption font-medium text-warning">Risky</p>
        </div>
        <div className="glass rounded-ios p-2 text-center">
          <p className="text-caption text-gray-500 dark:text-gray-400">
            Low R/R, High WR
          </p>
          <p className="text-caption font-medium text-warning">Conservative</p>
        </div>
        <div className="glass rounded-ios p-2 text-center">
          <p className="text-caption text-gray-500 dark:text-gray-400">
            High R/R, High WR
          </p>
          <p className="text-caption font-medium text-success">Optimal</p>
        </div>
      </div>
    </div>
  );
};