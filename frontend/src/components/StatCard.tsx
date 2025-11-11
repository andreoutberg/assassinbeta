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

const StatCard: React.FC<StatCardProps> = ({
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
      whileHover={{ scale: 1.01 }}
      whileTap={onClick ? { scale: 0.99 } : undefined}
      className={clsx(
        'card-dark p-4',
        'flex flex-col',
        'group cursor-default',
        onClick && 'cursor-pointer',
        className
      )}
      onClick={onClick}
    >
      {/* Icon */}
      <div className="flex items-center gap-2 mb-3">
        {Icon && (
          <Icon className={clsx('w-5 h-5', colorClasses[color])} />
        )}
        {trend && trendValue && (
          <div className={clsx(
            'flex items-center gap-1 ml-auto',
            trend === 'up' && 'text-ios-green',
            trend === 'down' && 'text-ios-red',
            trend === 'neutral' && 'text-gray-500'
          )}>
            {TrendIcon && <TrendIcon className="w-3.5 h-3.5" />}
            <span className="text-[11px] font-medium">{trendValue}</span>
          </div>
        )}
      </div>

      {/* Value */}
      <motion.div
        initial={{ opacity: 0, y: 5 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="text-[28px] font-bold text-white leading-tight mb-1"
      >
        {value}
      </motion.div>

      {/* Label */}
      <div className="text-[13px] text-gray-400">
        {label}
      </div>
    </motion.div>
  );
};

export default React.memo(StatCard);