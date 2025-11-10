import React from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';

interface WinRateGaugeProps {
  value: number;
  label?: string;
  size?: 'sm' | 'md' | 'lg';
  showThresholds?: boolean;
  className?: string;
}

export const WinRateGauge: React.FC<WinRateGaugeProps> = ({
  value,
  label = 'Win Rate',
  size = 'md',
  showThresholds = true,
  className,
}) => {
  // Clamp value between 0 and 100
  const clampedValue = Math.min(100, Math.max(0, value));

  // Calculate rotation angle (180 degrees = 100%)
  const rotation = (clampedValue / 100) * 180;

  // Determine color based on value
  const getColor = () => {
    if (clampedValue >= 65) return '#34C759'; // success
    if (clampedValue >= 50) return '#f59e0b'; // warning
    return '#d32f2f'; // danger
  };

  const sizes = {
    sm: { width: 120, height: 60, strokeWidth: 8, fontSize: 20 },
    md: { width: 200, height: 100, strokeWidth: 12, fontSize: 34 },
    lg: { width: 280, height: 140, strokeWidth: 16, fontSize: 48 },
  };

  const currentSize = sizes[size];
  const radius = (currentSize.width - currentSize.strokeWidth) / 2;
  const circumference = Math.PI * radius;

  return (
    <div className={clsx('flex flex-col items-center', className)}>
      <div className="relative" style={{ width: currentSize.width, height: currentSize.height }}>
        {/* Background arc */}
        <svg
          width={currentSize.width}
          height={currentSize.height}
          className="absolute inset-0"
        >
          <path
            d={`M ${currentSize.strokeWidth / 2} ${currentSize.height} A ${radius} ${radius} 0 0 1 ${currentSize.width - currentSize.strokeWidth / 2} ${currentSize.height}`}
            fill="none"
            stroke="currentColor"
            strokeWidth={currentSize.strokeWidth}
            strokeLinecap="round"
            className="text-gray-200 dark:text-gray-800"
          />
        </svg>

        {/* Color segments */}
        <svg
          width={currentSize.width}
          height={currentSize.height}
          className="absolute inset-0"
        >
          {/* Danger zone (0-50%) */}
          <path
            d={`M ${currentSize.strokeWidth / 2} ${currentSize.height} A ${radius} ${radius} 0 0 1 ${currentSize.width / 2} ${currentSize.strokeWidth / 2}`}
            fill="none"
            stroke="#d32f2f"
            strokeWidth={currentSize.strokeWidth}
            strokeLinecap="round"
            opacity={0.2}
          />

          {/* Warning zone (50-65%) */}
          <path
            d={`M ${currentSize.width / 2} ${currentSize.strokeWidth / 2} A ${radius} ${radius} 0 0 1 ${currentSize.width * 0.683} ${currentSize.height * 0.183}`}
            fill="none"
            stroke="#f59e0b"
            strokeWidth={currentSize.strokeWidth}
            strokeLinecap="round"
            opacity={0.2}
          />

          {/* Success zone (65-100%) */}
          <path
            d={`M ${currentSize.width * 0.683} ${currentSize.height * 0.183} A ${radius} ${radius} 0 0 1 ${currentSize.width - currentSize.strokeWidth / 2} ${currentSize.height}`}
            fill="none"
            stroke="#34C759"
            strokeWidth={currentSize.strokeWidth}
            strokeLinecap="round"
            opacity={0.2}
          />
        </svg>

        {/* Animated progress arc */}
        <svg
          width={currentSize.width}
          height={currentSize.height}
          className="absolute inset-0"
        >
          <motion.path
            d={`M ${currentSize.strokeWidth / 2} ${currentSize.height} A ${radius} ${radius} 0 ${rotation > 90 ? 1 : 0} 1 ${
              currentSize.width / 2 + radius * Math.cos((Math.PI * (180 - rotation)) / 180)
            } ${
              currentSize.height - radius * Math.sin((Math.PI * (180 - rotation)) / 180)
            }`}
            fill="none"
            stroke={getColor()}
            strokeWidth={currentSize.strokeWidth}
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 1.5, ease: 'easeOut' }}
          />
        </svg>

        {/* Value display */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center mt-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5, delay: 0.5 }}
              className="text-sf font-bold text-gray-900 dark:text-gray-50"
              style={{ fontSize: currentSize.fontSize }}
            >
              {clampedValue.toFixed(0)}%
            </motion.div>
          </div>
        </div>

        {/* Threshold markers */}
        {showThresholds && (
          <>
            {/* 50% marker */}
            <div
              className="absolute text-caption text-gray-500 dark:text-gray-400"
              style={{
                left: currentSize.width / 2 - 10,
                top: -5,
              }}
            >
              50%
            </div>

            {/* 65% marker */}
            <div
              className="absolute text-caption text-gray-500 dark:text-gray-400"
              style={{
                left: currentSize.width * 0.683 - 10,
                top: currentSize.height * 0.183 - 15,
              }}
            >
              65%
            </div>
          </>
        )}
      </div>

      {/* Label */}
      <div className="mt-3">
        <p className="text-body font-medium text-gray-600 dark:text-gray-300">
          {label}
        </p>
      </div>

      {/* Legend */}
      {showThresholds && (
        <div className="flex items-center gap-3 mt-3">
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-danger" />
            <span className="text-caption text-gray-500">Poor</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-warning" />
            <span className="text-caption text-gray-500">Fair</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-success" />
            <span className="text-caption text-gray-500">Good</span>
          </div>
        </div>
      )}
    </div>
  );
};