import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts';
import { format } from 'date-fns';
import clsx from 'clsx';

interface DataPoint {
  timestamp: string | Date;
  value: number;
  cumulative?: number;
}

interface PerformanceLineChartProps {
  data: DataPoint[];
  height?: number;
  showGrid?: boolean;
  color?: 'gold' | 'success' | 'danger' | 'gradient';
  className?: string;
}

export const PerformanceLineChart: React.FC<PerformanceLineChartProps> = ({
  data,
  height = 300,
  showGrid = true,
  color = 'gradient',
  className,
}) => {
  const strokeColor = {
    gold: '#D4AF37',
    success: '#00b67a',
    danger: '#d32f2f',
    gradient: 'url(#colorGradient)',
  }[color];

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload[0]) {
      return (
        <div className="glass-strong rounded-ios p-3 shadow-ios">
          <p className="text-caption text-gray-600 dark:text-gray-400">
            {format(new Date(label), 'MMM dd, HH:mm')}
          </p>
          <p className={clsx(
            'text-body font-semibold mt-1',
            payload[0].value >= 0 ? 'text-success' : 'text-danger'
          )}>
            {payload[0].value >= 0 ? '+' : ''}{payload[0].value.toFixed(2)}%
          </p>
        </div>
      );
    }
    return null;
  };

  const formatTick = (value: string) => {
    return format(new Date(value), 'MMM dd');
  };

  return (
    <div className={clsx('card-ios p-5', className)}>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
          <defs>
            <linearGradient id="colorGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#00b67a" stopOpacity={0.8} />
              <stop offset="50%" stopColor="#D4AF37" stopOpacity={0.5} />
              <stop offset="100%" stopColor="#d32f2f" stopOpacity={0.3} />
            </linearGradient>
            <linearGradient id="fillGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#D4AF37" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#D4AF37" stopOpacity={0} />
            </linearGradient>
          </defs>

          {showGrid && (
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#E5E5EA"
              className="dark:stroke-gray-800"
              opacity={0.5}
            />
          )}

          <XAxis
            dataKey="timestamp"
            tickFormatter={formatTick}
            stroke="#8E8E93"
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
          />

          <YAxis
            stroke="#8E8E93"
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => `${value}%`}
          />

          <Tooltip content={<CustomTooltip />} />

          <Area
            type="monotone"
            dataKey="value"
            stroke={strokeColor}
            strokeWidth={2}
            fill="url(#fillGradient)"
            fillOpacity={1}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};