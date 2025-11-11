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
      className={clsx('card-dark overflow-hidden', className)}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={clsx(
          'w-full px-5 py-4 flex items-center justify-between',
          'hover:bg-gray-800/30',
          'transition-colors duration-200',
          'group',
          headerClassName
        )}
        aria-expanded={isOpen}
        aria-controls={`section-${title.toLowerCase().replace(/\s+/g, '-')}`}
      >
        <div className="flex items-center gap-3 text-left">
          {Icon && (
            <div className="flex-shrink-0">
              <Icon className="w-5 h-5 text-white" />
            </div>
          )}
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-[15px] font-medium text-white">
                {title}
              </h2>
              {badge}
            </div>
            {summary && (
              <p className="text-[13px] text-gray-400 mt-0.5">
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
          <ChevronDown className="w-5 h-5 text-gray-500 group-hover:text-gray-400 transition-colors duration-200" />
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
              'px-5 pb-4 pt-3 border-t border-gray-800/50',
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