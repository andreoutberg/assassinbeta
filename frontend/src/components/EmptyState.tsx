import React from 'react';
import { motion } from 'framer-motion';
import { LucideIcon } from 'lucide-react';
import clsx from 'clsx';

interface EmptyStateProps {
  icon?: LucideIcon;
  message: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon,
  message,
  description,
  action,
  className,
}) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={clsx(
        'card-ios p-8 md:p-12 text-center',
        className
      )}
    >
      {Icon && (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: 0.1, type: 'spring', stiffness: 200 }}
          className="mx-auto mb-6 p-4 rounded-ios-lg bg-gray-100 dark:bg-gray-800 inline-block"
        >
          <Icon className="w-8 h-8 md:w-10 md:h-10 text-gray-400 dark:text-gray-600" />
        </motion.div>
      )}

      <motion.h3
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="text-title2 font-semibold text-gray-900 dark:text-gray-50 mb-2"
      >
        {message}
      </motion.h3>

      {description && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="text-body text-gray-500 dark:text-gray-400 max-w-sm mx-auto"
        >
          {description}
        </motion.p>
      )}

      {action && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="mt-6"
        >
          <button
            onClick={action.onClick}
            className="btn-ios-primary"
          >
            {action.label}
          </button>
        </motion.div>
      )}
    </motion.div>
  );
};