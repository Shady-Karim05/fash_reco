import React from 'react';
import { SlidersHorizontal, Check, Zap, DollarSign, Tag, Clock } from 'lucide-react';
import { SearchMeta } from '../../types/search';
import { formatSlot } from '../../utils/formatters';

export interface FilterOptions {
  selectedSlot: string | null;
  sortBy: 'relevance' | 'price_asc' | 'price_desc';
}

export interface FilterSidebarProps {
  meta?: SearchMeta;
  filterOptions: FilterOptions;
  availableSlots: string[];
  onChangeSlot: (slot: string | null) => void;
  onChangeSort: (sort: 'relevance' | 'price_asc' | 'price_desc') => void;
  onReset: () => void;
}

export const FilterSidebar: React.FC<FilterSidebarProps> = ({
  meta,
  filterOptions,
  availableSlots,
  onChangeSlot,
  onChangeSort,
  onReset,
}) => {
  const parsed = meta?.parsed_filters || {};

  return (
    <aside className="w-full space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-sand-200">
        <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-brand-900">
          <SlidersHorizontal className="w-4 h-4 text-sand-600" />
          <span>Filters & Sort</span>
        </div>
        {(filterOptions.selectedSlot || filterOptions.sortBy !== 'relevance') && (
          <button
            type="button"
            onClick={onReset}
            className="text-xs text-accent-700 hover:text-accent-800 font-medium"
          >
            Reset
          </button>
        )}
      </div>

      {/* Backend Extracted Intent / Parsed Filters */}
      {meta && (
        <div className="bg-sand-50 rounded-2xl p-4 border border-sand-200 space-y-3">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-sand-700">
            <span className="flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-accent-600" />
              Detected Query Intent
            </span>
            {meta.used_fallback && (
              <span className="text-[10px] bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full font-medium">
                Rule Fallback
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 gap-2 text-xs">
            {parsed.occasion && (
              <div className="flex items-center justify-between text-sand-600">
                <span className="text-sand-500">Occasion:</span>
                <span className="font-medium text-brand-900 capitalize">{parsed.occasion}</span>
              </div>
            )}
            {parsed.season && (
              <div className="flex items-center justify-between text-sand-600">
                <span className="text-sand-500">Season:</span>
                <span className="font-medium text-brand-900 capitalize">{parsed.season}</span>
              </div>
            )}
            {parsed.gender && parsed.gender !== 'unknown' && (
              <div className="flex items-center justify-between text-sand-600">
                <span className="text-sand-500">Audience:</span>
                <span className="font-medium text-brand-900 capitalize">{parsed.gender}</span>
              </div>
            )}
            {parsed.max_price && (
              <div className="flex items-center justify-between text-sand-600">
                <span className="text-sand-500 flex items-center gap-1">
                  <DollarSign className="w-3 h-3" /> Max Budget:
                </span>
                <span className="font-medium text-brand-900">${parsed.max_price}</span>
              </div>
            )}
            {parsed.brand && (
              <div className="flex items-center justify-between text-sand-600">
                <span className="text-sand-500 flex items-center gap-1">
                  <Tag className="w-3 h-3" /> Brand:
                </span>
                <span className="font-medium text-brand-900 capitalize">{parsed.brand}</span>
              </div>
            )}
          </div>

          <div className="pt-2 border-t border-sand-200/80 flex items-center justify-between text-[11px] text-sand-500">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {meta.latency_ms.toFixed(1)} ms
            </span>
            <span>Index v{meta.index_version}</span>
          </div>
        </div>
      )}

      {/* Sort Section */}
      <div className="space-y-3">
        <label className="block text-xs font-semibold uppercase tracking-wider text-sand-700">
          Sort Results By
        </label>
        <div className="space-y-1.5">
          {[
            { value: 'relevance', label: 'Highest Semantic Match' },
            { value: 'price_asc', label: 'Price: Low to High' },
            { value: 'price_desc', label: 'Price: High to Low' },
          ].map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => onChangeSort(opt.value as FilterOptions['sortBy'])}
              className={`w-full flex items-center justify-between px-3 py-2 text-xs rounded-xl transition-colors text-left ${
                filterOptions.sortBy === opt.value
                  ? 'bg-brand-900 text-white font-medium'
                  : 'bg-white hover:bg-sand-100 text-sand-700 border border-sand-200'
              }`}
            >
              <span>{opt.label}</span>
              {filterOptions.sortBy === opt.value && <Check className="w-3.5 h-3.5" />}
            </button>
          ))}
        </div>
      </div>

      {/* Apparel Category / Slot Filter */}
      {availableSlots.length > 0 && (
        <div className="space-y-3">
          <label className="block text-xs font-semibold uppercase tracking-wider text-sand-700">
            Apparel Category
          </label>
          <div className="space-y-1.5">
            <button
              type="button"
              onClick={() => onChangeSlot(null)}
              className={`w-full flex items-center justify-between px-3 py-2 text-xs rounded-xl transition-colors text-left ${
                filterOptions.selectedSlot === null
                  ? 'bg-brand-900 text-white font-medium'
                  : 'bg-white hover:bg-sand-100 text-sand-700 border border-sand-200'
              }`}
            >
              <span>All Categories</span>
              {filterOptions.selectedSlot === null && <Check className="w-3.5 h-3.5" />}
            </button>
            {availableSlots.map((slot) => (
              <button
                key={slot}
                type="button"
                onClick={() => onChangeSlot(slot)}
                className={`w-full flex items-center justify-between px-3 py-2 text-xs rounded-xl transition-colors text-left ${
                  filterOptions.selectedSlot === slot
                    ? 'bg-brand-900 text-white font-medium'
                    : 'bg-white hover:bg-sand-100 text-sand-700 border border-sand-200'
                }`}
              >
                <span>{formatSlot(slot)}</span>
                {filterOptions.selectedSlot === slot && <Check className="w-3.5 h-3.5" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
};
