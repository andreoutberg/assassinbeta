import React from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import clsx from 'clsx';

interface StatCardProps {
  value: string | number;
  label: string;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  icon?: React.FC<{ className?: string }>;
  color?: 'gold' | 'success' | 'danger' | 'warning' | 'blue';
  className?: string;
  onClick?: () => void;
}

export const StatCard: React.FC<StatCardProps> = ({
  value,
  label,
  trend,
  trendValue,
  icon: Icon,
  color = 'gold',
  className,
  onClick,
}) => {
  const colorClasses = {
    gold: 'text-gold',
    success: 'text-success',
    danger: 'text-danger',
    warning: 'text-warning',
    blue: 'text-ios-blue',
  };

  const trendIcon = {
    up: TrendingUp,
    down: TrendingDown,
    neutral: Minus,
  };

  const TrendIcon = trend ? trendIcon[trend] : null;

  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      whileTap={onClick ? { scale: 0.98 } : undefined}
      className={clsx(
        'card-ios p-5 md:p-6',
        'flex flex-col items-start',
        'group cursor-default',
        onClick && 'cursor-pointer',
        className
      )}
      onClick={onClick}
    >
      {/* Icon and trend */}
      <div className="w-full flex items-start justify-between mb-3">
        {Icon && (
          <div className={clsx(
            'p-2 rounded-ios',
            'bg-gray-100 dark:bg-gray-800',
            'group-hover:bg-gray-200 dark:group-hover:bg-gray-700',
            'transition-colors duration-200'
          )}>
            <Icon className={clsx('w-5 h-5', colorClasses[color])} />
          </div>
        )}

        {trend && (
          <div className={clsx(
            'flex items-center gap-1',
            trend === 'up' && 'text-success',
            trend === 'down' && 'text-danger',
            trend === 'neutral' && 'text-gray-500'
          )}>
            {TrendIcon && <TrendIcon className="w-4 h-4" />}
            {trendValue && (
              <span className="text-caption font-medium">
                {trendValue}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Value */}
      <div className="space-y-1">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
          className={clsx(
            'text-largeTitle font-bold text-sf',
            'text-gray-900 dark:text-gray-50'
          )}
        >
          {value}
        </motion.div>

        {/* Label */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3, delay: 0.2 }}
          className="text-caption text-gray-500 dark:text-gray-400"
        >
          {label}
        </motion.div>
      </div>

      {/* Hover indicator */}
      {onClick && (
        <motion.div
          initial={{ width: 0 }}
          whileHover={{ width: '100%' }}
          className="absolute bottom-0 left-0 h-0.5 bg-gold"
          transition={{ duration: 0.2 }}
        />
      )}
    </motion.div>
  );
};