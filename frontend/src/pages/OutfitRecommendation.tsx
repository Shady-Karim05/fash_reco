import React, { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Layers, Sparkles, DollarSign, Clock } from 'lucide-react';
import { useOutfitRecommendation } from '../hooks/useOutfitRecommendation';
import { SearchBar } from '../components/common/SearchBar';
import { OutfitDisplay } from '../components/outfit/OutfitDisplay';
import { OutfitSkeleton } from '../components/common/Skeleton';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';

const EXAMPLE_OUTFIT_QUERIES = [
  'cocktail party outfit for women under $100',
  'summer casual resort outfit for men under $80',
  'formal wedding guest look with shoes and jewelry',
  'streetwear gym outfit for men under $60',
  'minimalist business casual ensemble for women',
];

export const OutfitRecommendation: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryParam = searchParams.get('q') || '';

  const { recommend, data, status, error, isLoading } = useOutfitRecommendation();

  // Execute recommendation if URL param exists
  useEffect(() => {
    if (queryParam) {
      recommend(queryParam);
    }
  }, [queryParam, recommend]);

  const handleOutfitSubmit = (newQuery: string) => {
    setSearchParams({ q: newQuery });
    recommend(newQuery);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-12">
      {/* Header & Stylist Input */}
      <div className="max-w-3xl mx-auto text-center space-y-4">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent-50 text-accent-800 border border-accent-200 text-xs font-semibold uppercase tracking-wider">
          <Layers className="w-3.5 h-3.5" />
          <span>Generative Outfit Recommender</span>
        </div>

        <h1 className="font-serif text-3xl sm:text-5xl font-light text-brand-900 leading-tight">
          Curated Multi-Piece Looks
        </h1>

        <p className="text-sand-600 text-sm sm:text-base max-w-xl mx-auto">
          Input an occasion, aesthetic, or budget limit. The microservice automatically coordinates
          compatible tops, bottoms, footwear, and accessories.
        </p>

        <div className="pt-2">
          <SearchBar
            initialValue={queryParam}
            placeholder="e.g. 'cocktail party outfit for women under $100'..."
            onSearch={handleOutfitSubmit}
            isLoading={isLoading}
            size="lg"
            showPills={true}
            examplePills={EXAMPLE_OUTFIT_QUERIES}
          />
        </div>
      </div>

      {/* Main Content Area */}
      {status === 'idle' ? (
        <div className="max-w-3xl mx-auto bg-white rounded-3xl border border-sand-200 p-8 sm:p-12 text-center shadow-subtle space-y-6">
          <div className="w-16 h-16 rounded-full bg-sand-100 flex items-center justify-center text-accent-700 mx-auto">
            <Sparkles className="w-8 h-8" />
          </div>

          <div className="space-y-2">
            <h3 className="font-serif text-2xl font-light text-brand-900">
              Coordinated Fashion Intelligence
            </h3>
            <p className="text-sm text-sand-600 max-w-lg mx-auto">
              Our backend combines cross-slot compatibility filters, color harmony heuristics, and
              budget optimization to generate unified head-to-toe recommendations.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4 text-left border-t border-sand-100">
            <div className="p-4 rounded-2xl bg-sand-50/70 border border-sand-200">
              <span className="font-semibold text-xs uppercase tracking-wider text-brand-900 block mb-1">
                1. Context
              </span>
              <p className="text-xs text-sand-500">
                Identifies occasion, season, and formality from natural speech.
              </p>
            </div>
            <div className="p-4 rounded-2xl bg-sand-50/70 border border-sand-200">
              <span className="font-semibold text-xs uppercase tracking-wider text-brand-900 block mb-1 flex items-center gap-1">
                <DollarSign className="w-3 h-3 text-accent-600" />
                2. Budget
              </span>
              <p className="text-xs text-sand-500">
                Optimizes cumulative slot prices to stay strictly within budget bounds.
              </p>
            </div>
            <div className="p-4 rounded-2xl bg-sand-50/70 border border-sand-200">
              <span className="font-semibold text-xs uppercase tracking-wider text-brand-900 block mb-1 flex items-center gap-1">
                <Clock className="w-3 h-3 text-accent-600" />
                3. Fast Co-Ranking
              </span>
              <p className="text-xs text-sand-500">
                Pre-filtered candidate recall with sub-second composite ranking.
              </p>
            </div>
          </div>
        </div>
      ) : status === 'loading' ? (
        <OutfitSkeleton />
      ) : status === 'error' ? (
        <ErrorState
          error={error}
          onRetry={() => queryParam && recommend(queryParam)}
        />
      ) : status === 'empty' || !data?.outfit ? (
        <EmptyState
          title="No ensemble matched this prompt"
          description={
            data?.message === 'no_outfit_within_budget'
              ? 'The system was unable to find all required outfit pieces within the requested price ceiling. Try increasing the budget limit.'
              : data?.message ||
                'No coordinated ensemble could be generated for this exact search criteria. Try a broader search.'
          }
          suggestions={EXAMPLE_OUTFIT_QUERIES.slice(0, 3)}
          onSelectSuggestion={handleOutfitSubmit}
          actionText="Try Standard Cocktail Look"
          onAction={() =>
            handleOutfitSubmit('cocktail party outfit for women under $100')
          }
        />
      ) : (
        <OutfitDisplay outfit={data.outfit} meta={data.meta} />
      )}
    </div>
  );
};
