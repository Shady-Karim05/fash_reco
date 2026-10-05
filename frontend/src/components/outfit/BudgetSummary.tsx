import React from 'react';
import { CheckCircle, AlertTriangle, Sparkles, Layers } from 'lucide-react';
import { OutfitPayload } from '../../types/outfit';
import { SearchMeta } from '../../types/search';
import { formatPrice } from '../../utils/formatPrice';

export interface BudgetSummaryProps {
  outfit: OutfitPayload;
  meta: SearchMeta;
}

export const BudgetSummary: React.FC<BudgetSummaryProps> = ({ outfit, meta }) => {
  const maxPrice = meta.parsed_filters?.max_price as number | undefined;
  const isWithinBudget = maxPrice ? outfit.total_price <= maxPrice : true;

  const templateLabel = outfit.template
    ? outfit.template.replace(/_/g, ' • ').toUpperCase()
    : 'STANDARD ENSEMBLE';

  return (
    <div className="bg-white rounded-3xl p-6 md:p-8 border border-sand-200 shadow-subtle flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-wider font-semibold px-2.5 py-1 rounded-full bg-accent-50 text-accent-800 border border-accent-200 inline-flex items-center gap-1.5">
            <Layers className="w-3 h-3" />
            Template: {templateLabel}
          </span>
          {outfit.complete ? (
            <span className="text-[11px] uppercase tracking-wider font-semibold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 inline-flex items-center gap-1">
              <CheckCircle className="w-3 h-3 text-emerald-600" />
              Complete Outfit
            </span>
          ) : (
            <span className="text-[11px] uppercase tracking-wider font-semibold px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200 inline-flex items-center gap-1">
              <AlertTriangle className="w-3 h-3 text-amber-600" />
              Partial Match
            </span>
          )}
        </div>

        <h3 className="font-serif text-2xl font-light text-brand-900">
          Coordinated Fashion Ensemble
        </h3>
        <p className="text-sand-600 text-xs">
          Harmonized across {outfit.items.length} complementary components using semantic similarity
          and cross-slot compatibility constraints.
        </p>
      </div>

      {/* Pricing and budget block */}
      <div className="flex items-center gap-6 self-stretch md:self-auto justify-between md:justify-end pt-4 md:pt-0 border-t md:border-t-0 border-sand-100">
        <div className="text-left md:text-right">
          <span className="text-xs uppercase tracking-wider text-sand-500 font-medium block">
            Total Ensemble Price
          </span>
          <span className="font-serif text-3xl font-semibold text-brand-900">
            {formatPrice(outfit.total_price)}
          </span>
        </div>

        {maxPrice && (
          <div
            className={`px-3 py-2 rounded-2xl border text-xs text-left ${
              isWithinBudget
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : 'bg-amber-50 border-amber-200 text-amber-800'
            }`}
          >
            <div className="font-semibold flex items-center gap-1">
              <Sparkles className="w-3 h-3" />
              {isWithinBudget ? 'Within Budget' : 'Exceeds Target'}
            </div>
            <div className="text-[11px] opacity-90">
              Budget target: ${maxPrice.toFixed(0)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
