import React, { useState, ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import clsx from 'clsx';

interface CollapsibleSectionProps {
  title: string;
  summary?: string;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  headerClassName?: string;
  contentClassName?: string;
  icon?: React.FC<{ className?: string }>;
  badge?: ReactNode;
}

export const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({
  title,
  summary,
  children,
  defaultOpen = false,
  className,
  headerClassName,
  contentClassName,
  icon: Icon,
  badge,
}) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <motion.div
      layout
      className={clsx('card-ios overflow-hidden', className)}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={clsx(
          'w-full px-5 py-4 flex items-center justify-between',
          'hover:bg-gray-50 dark:hover:bg-gray-800/50',
          'transition-colors duration-200 touch-feedback focus-ring',
          'group',
          headerClassName
        )}
        aria-expanded={isOpen}
        aria-controls={`section-${title.toLowerCase().replace(/\s+/g, '-')}`}
      >
        <div className="flex items-center gap-3 text-left">
          {Icon && (
            <div className="flex-shrink-0">
              <Icon className="w-5 h-5 text-gold" />
            </div>
          )}
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-headline text-gray-900 dark:text-gray-50">
                {title}
              </h2>
              {badge}
            </div>
            {summary && (
              <p className="text-caption text-gray-500 dark:text-gray-400 mt-0.5">
                {summary}
              </p>
            )}
          </div>
        </div>

        <motion.div
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.2, ease: 'easeInOut' }}
          className="flex-shrink-0 ml-2"
        >
          <ChevronDown className={clsx(
            'w-5 h-5 transition-colors duration-200',
            'text-gray-400 group-hover:text-gray-600',
            'dark:text-gray-500 dark:group-hover:text-gray-300'
          )} />
        </motion.div>
      </button>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            id={`section-${title.toLowerCase().replace(/\s+/g, '-')}`}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{
              height: { duration: 0.3, ease: 'easeInOut' },
              opacity: { duration: 0.2 }
            }}
            className="overflow-hidden"
          >
            <div className={clsx(
              'px-5 pb-4 pt-1 border-t border-gray-200/50 dark:border-gray-800/50',
              contentClassName
            )}>
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};