import React from 'react';
import { X } from 'lucide-react';
import { FilterSidebar, FilterSidebarProps } from './FilterSidebar';

export interface FilterDrawerProps extends FilterSidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export const FilterDrawer: React.FC<FilterDrawerProps> = ({
  isOpen,
  onClose,
  ...sidebarProps
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex lg:hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer content */}
      <div className="relative ml-auto w-full max-w-xs bg-white h-full shadow-2xl p-6 overflow-y-auto flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between pb-4 border-b border-sand-200 mb-6">
            <span className="font-serif text-lg text-brand-900">Filter & Refine</span>
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded-full text-sand-500 hover:text-brand-900 focus:outline-none"
              aria-label="Close filters"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <FilterSidebar {...sidebarProps} />
        </div>

        <div className="pt-6 border-t border-sand-200 mt-6">
          <button
            type="button"
            onClick={onClose}
            className="w-full py-3 bg-brand-900 hover:bg-black text-white text-xs uppercase tracking-wider font-semibold rounded-full shadow-sm"
          >
            Apply Filters
          </button>
        </div>
      </div>
    </div>
  );
};
