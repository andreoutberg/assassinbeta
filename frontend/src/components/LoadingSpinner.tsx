import React from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  color?: 'gold' | 'white' | 'gray';
  text?: string;
  className?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = 'md',
  color = 'gold',
  text,
  className,
}) => {
  const sizes = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
    xl: 'w-16 h-16',
  };

  const borderSizes = {
    sm: 'border-2',
    md: 'border-3',
    lg: 'border-4',
    xl: 'border-4',
  };

  const colors = {
    gold: 'border-gold',
    white: 'border-white',
    gray: 'border-gray-600 dark:border-gray-400',
  };

  const spinnerVariants = {
    animate: {
      rotate: 360,
      transition: {
        duration: 1,
        repeat: Infinity,
        ease: 'linear',
      },
    },
  };

  return (
    <div className={clsx('flex flex-col items-center justify-center gap-3', className)}>
      <motion.div
        variants={spinnerVariants}
        animate="animate"
        className={clsx(
          sizes[size],
          borderSizes[size],
          colors[color],
          'border-t-transparent rounded-full',
          'shadow-sm'
        )}
      />

      {text && (
        <motion.p
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="text-body text-gray-600 dark:text-gray-400 text-center"
        >
          {text}
        </motion.p>
      )}
    </div>
  );
};