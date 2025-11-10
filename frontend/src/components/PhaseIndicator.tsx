import React from 'react';
import { TrendingUp, TrendingDown, Minus, AlertCircle, Clock, CheckCircle } from 'lucide-react';
import { motion } from 'framer-motion';
import clsx from 'clsx';

export type PhaseType = 'accumulation' | 'markup' | 'distribution' | 'markdown' | 'neutral' | 'analyzing';

interface PhaseIndicatorProps {
  phase: PhaseType;
  confidence?: number;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const phaseConfig = {
  accumulation: {
    label: 'Accumulation',
    icon: Clock,
    color: 'text-ios-blue',
    bgColor: 'bg-ios-blue/10',
    borderColor: 'border-ios-blue/20',
    description: 'Smart money accumulating',
  },
  markup: {
    label: 'Markup',
    icon: TrendingUp,
    color: 'text-ios-green',
    bgColor: 'bg-ios-green/10',
    borderColor: 'border-ios-green/20',
    description: 'Uptrend in progress',
  },
  distribution: {
    label: 'Distribution',
    icon: AlertCircle,
    color: 'text-ios-orange',
    bgColor: 'bg-ios-orange/10',
    borderColor: 'border-ios-orange/20',
    description: 'Smart money distributing',
  },
  markdown: {
    label: 'Markdown',
    icon: TrendingDown,
    color: 'text-ios-red',
    bgColor: 'bg-ios-red/10',
    borderColor: 'border-ios-red/20',
    description: 'Downtrend in progress',
  },
  neutral: {
    label: 'Neutral',
    icon: Minus,
    color: 'text-gray-500',
    bgColor: 'bg-gray-500/10',
    borderColor: 'border-gray-500/20',
    description: 'No clear direction',
  },
  analyzing: {
    label: 'Analyzing',
    icon: CheckCircle,
    color: 'text-ios-teal',
    bgColor: 'bg-ios-teal/10',
    borderColor: 'border-ios-teal/20',
    description: 'Processing market data',
  },
};

const sizeConfig = {
  sm: {
    container: 'px-2 py-1',
    icon: 'w-3.5 h-3.5',
    text: 'text-caption',
    gap: 'gap-1.5',
  },
  md: {
    container: 'px-3 py-1.5',
    icon: 'w-4 h-4',
    text: 'text-sm',
    gap: 'gap-2',
  },
  lg: {
    container: 'px-4 py-2',
    icon: 'w-5 h-5',
    text: 'text-body',
    gap: 'gap-2.5',
  },
};

const PhaseIndicator: React.FC<PhaseIndicatorProps> = ({
  phase,
  confidence,
  showLabel = true,
  size = 'md',
  className,
}) => {
  const config = phaseConfig[phase];
  const sizes = sizeConfig[size];
  const Icon = config.icon;

  return (
    <motion.div
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      className={clsx(
        'inline-flex items-center rounded-full border',
        sizes.container,
        sizes.gap,
        config.bgColor,
        config.borderColor,
        className
      )}
    >
      <Icon className={clsx(sizes.icon, config.color)} />

      {showLabel && (
        <div className="flex flex-col">
          <span className={clsx(sizes.text, 'font-medium', config.color)}>
            {config.label}
          </span>
          {confidence !== undefined && (
            <span className={clsx('text-[10px] opacity-70', config.color)}>
              {(confidence * 100).toFixed(0)}% confidence
            </span>
          )}
        </div>
      )}

      {/* Pulse animation for active phases */}
      {(phase === 'markup' || phase === 'markdown' || phase === 'analyzing') && (
        <motion.div
          className={clsx(
            'absolute inset-0 rounded-full',
            config.bgColor,
            'opacity-30'
          )}
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.3, 0, 0.3],
          }}
          transition={{
            duration: 2,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />
      )}
    </motion.div>
  );
};

export default PhaseIndicator;