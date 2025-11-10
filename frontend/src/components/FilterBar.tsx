import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import clsx from 'clsx';

interface FilterOption {
  value: string;
  label: string;
  count?: number;
}

interface FilterBarProps {
  filters: {
    [key: string]: {
      label: string;
      options: FilterOption[];
      multiple?: boolean;
    };
  };
  activeFilters: {
    [key: string]: string | string[];
  };
  onFilterChange: (filterKey: string, value: string | string[]) => void;
  onClearAll?: () => void;
  className?: string;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  filters,
  activeFilters,
  onFilterChange,
  onClearAll,
  className,
}) => {
  const hasActiveFilters = Object.keys(activeFilters).some(
    (key) => {
      const value = activeFilters[key];
      return Array.isArray(value) ? value.length > 0 : !!value;
    }
  );

  const handleFilterClick = (filterKey: string, optionValue: string) => {
    const filter = filters[filterKey];
    const currentValue = activeFilters[filterKey];

    if (filter.multiple) {
      const currentArray = Array.isArray(currentValue) ? currentValue : [];
      const newValue = currentArray.includes(optionValue)
        ? currentArray.filter((v) => v !== optionValue)
        : [...currentArray, optionValue];
      onFilterChange(filterKey, newValue);
    } else {
      onFilterChange(filterKey, currentValue === optionValue ? '' : optionValue);
    }
  };

  const isOptionActive = (filterKey: string, optionValue: string) => {
    const currentValue = activeFilters[filterKey];
    if (Array.isArray(currentValue)) {
      return currentValue.includes(optionValue);
    }
    return currentValue === optionValue;
  };

  return (
    <div className={clsx('space-y-3', className)}>
      {/* Filter groups */}
      {Object.entries(filters).map(([filterKey, filter]) => (
        <div key={filterKey}>
          <p className="text-caption text-gray-500 dark:text-gray-400 mb-2">
            {filter.label}
          </p>
          <div className="flex flex-wrap gap-2 md:gap-3">
            {filter.options.map((option) => {
              const isActive = isOptionActive(filterKey, option.value);

              return (
                <motion.button
                  key={option.value}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => handleFilterClick(filterKey, option.value)}
                  className={clsx(
                    'px-4 py-2 rounded-full text-body font-medium',
                    'transition-all duration-200 touch-feedback focus-ring',
                    'flex items-center gap-2',
                    isActive
                      ? 'bg-gold text-white shadow-sm'
                      : 'glass hover:glass-strong text-gray-700 dark:text-gray-300'
                  )}
                >
                  <span>{option.label}</span>
                  {option.count !== undefined && (
                    <span className={clsx(
                      'text-caption px-1.5 py-0.5 rounded-full',
                      isActive
                        ? 'bg-white/20 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                    )}>
                      {option.count}
                    </span>
                  )}
                </motion.button>
              );
            })}
          </div>
        </div>
      ))}

      {/* Clear all button */}
      <AnimatePresence>
        {hasActiveFilters && onClearAll && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <button
              onClick={onClearAll}
              className="btn-ios-ghost text-danger hover:bg-danger/10 mt-2"
            >
              <X className="w-4 h-4" />
              Clear All Filters
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};