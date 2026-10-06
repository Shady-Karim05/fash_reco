import React, { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { SlidersHorizontal, Sparkles, AlertCircle, Zap, X } from 'lucide-react';
import { useSearch } from '../hooks/useSearch';
import { SearchBar } from '../components/common/SearchBar';
import { ProductGrid } from '../components/search/ProductGrid';
import { ProductGridSkeleton } from '../components/common/Skeleton';
import { FilterSidebar, FilterOptions } from '../components/search/FilterSidebar';
import { FilterDrawer } from '../components/search/FilterDrawer';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { formatSlot } from '../utils/formatters';

const QUICK_CATEGORIES = [
  { label: 'All Items', slot: null },
  { label: 'Dresses', slot: 'full_body' },
  { label: 'Tops', slot: 'top' },
  { label: 'Bottoms', slot: 'bottom' },
  { label: 'Footwear', slot: 'footwear' },
  { label: 'Accessories', slot: 'accessory' },
];

export const Search: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryParam = searchParams.get('q') || '';

  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    selectedSlot: null,
    sortBy: 'relevance',
  });

  const { data, status, error, refetch, isLoading } = useSearch(queryParam, 32);

  const handleSearchSubmit = (newQuery: string) => {
    setSearchParams({ q: newQuery });
    // Reset filters on new search
    setFilterOptions({ selectedSlot: null, sortBy: 'relevance' });
  };

  // Derive available categories/slots present in returned results
  const availableSlots = useMemo(() => {
    if (!data?.results) return [];
    const set = new Set<string>();
    data.results.forEach((r) => {
      if (r.slot && r.slot !== 'unknown') {
        set.add(r.slot);
      }
    });
    return Array.from(set);
  }, [data?.results]);

  // Client-side filtering & sorting of backend-returned products
  const filteredAndSortedProducts = useMemo(() => {
    if (!data?.results) return [];

    let list = [...data.results];

    // Filter by slot if selected
    if (filterOptions.selectedSlot) {
      list = list.filter((item) => item.slot === filterOptions.selectedSlot);
    }

    // Sort
    if (filterOptions.sortBy === 'price_asc') {
      list.sort((a, b) => (a.price ?? 999999) - (b.price ?? 999999));
    } else if (filterOptions.sortBy === 'price_desc') {
      list.sort((a, b) => (b.price ?? -1) - (a.price ?? -1));
    } else {
      // Default to relevance score
      list.sort((a, b) => b.score - a.score);
    }

    return list;
  }, [data?.results, filterOptions]);

  const handleResetFilters = () => {
    setFilterOptions({ selectedSlot: null, sortBy: 'relevance' });
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      {/* Search Header with Editorial Aesthetics */}
      <div className="max-w-3xl mx-auto text-center space-y-5">
        <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-sand-100/90 border border-sand-200 text-[11px] font-semibold uppercase tracking-[0.2em] text-accent-700">
          <Sparkles className="w-3.5 h-3.5 text-accent-600" />
          <span>Semantic Discovery</span>
        </div>

        <h1 className="font-serif text-3xl sm:text-5xl text-brand-900 font-light tracking-tight">
          Haute Catalog Search
        </h1>

        <div className="p-1 rounded-full bg-white/95 shadow-premium border border-sand-200/90 hover:border-sand-300 transition-all duration-300">
          <SearchBar
            initialValue={queryParam}
            placeholder="Describe apparel by aesthetic, cut, vibe, occasion, or palette..."
            onSearch={handleSearchSubmit}
            isLoading={isLoading}
            size="lg"
          />
        </div>

        {/* Quick Category Filtering Pills */}
        <div className="flex items-center justify-center flex-wrap gap-2 pt-2">
          {QUICK_CATEGORIES.map((cat) => {
            const isActive = filterOptions.selectedSlot === cat.slot;
            return (
              <button
                key={cat.label}
                type="button"
                onClick={() =>
                  setFilterOptions((prev) => ({
                    ...prev,
                    selectedSlot: cat.slot,
                  }))
                }
                className={`text-xs px-3.5 py-1.5 rounded-full font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-brand-900 text-white shadow-xs'
                    : 'bg-white/80 text-sand-700 border border-sand-200 hover:bg-sand-100'
                }`}
              >
                {cat.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Content Layout */}
      {status === 'idle' ? (
        <div className="text-center py-20 bg-white/90 backdrop-blur-md rounded-3xl border border-sand-200/90 p-8 max-w-2xl mx-auto shadow-premium space-y-6">
          <div className="w-16 h-16 rounded-full bg-sand-100/80 border border-sand-200 flex items-center justify-center text-accent-700 mx-auto">
            <Sparkles className="w-8 h-8" />
          </div>
          <div className="space-y-2">
            <h2 className="font-serif text-2xl sm:text-3xl text-brand-900 font-light">
              Discover Fashion Through Meaning
            </h2>
            <p className="text-sm text-sand-600 max-w-md mx-auto leading-relaxed">
              Describe your occasion, silhouette, material, or desired atmosphere. Our AI index
              comprehends nuanced semantics across 24,000 apparel records.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 justify-center pt-2">
            {[
              'red cocktail dress',
              'black running sneakers',
              'oversized beige blazer',
              'pleated silk maxi skirt',
              'vintage leather jacket',
              'women formal outfit under $100',
            ].map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => handleSearchSubmit(q)}
                className="text-xs bg-sand-100/80 hover:bg-brand-900 hover:text-white text-sand-800 px-3.5 py-1.5 rounded-full transition-all duration-200 font-medium border border-sand-200"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : status === 'error' ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : (
        <div className="space-y-6">
          {/* Status Bar & Active Filter Summary */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-sand-200/80 pb-4">
            <div className="flex items-center flex-wrap gap-2.5">
              {status === 'loading' ? (
                <div className="h-5 w-48 bg-sand-200 animate-pulse rounded-full" />
              ) : (
                <>
                  <span className="text-sm font-semibold text-brand-950 font-serif">
                    {filteredAndSortedProducts.length}{' '}
                    {filteredAndSortedProducts.length === 1 ? 'Piece' : 'Pieces'} Found
                  </span>
                  <span className="text-xs text-sand-500 font-light">
                    for &ldquo;<span className="text-brand-900 font-medium">{queryParam}</span>&rdquo;
                  </span>

                  {data?.meta?.latency_ms && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-sand-100 text-sand-600 border border-sand-200">
                      <Zap className="w-2.5 h-2.5 text-accent-600" />
                      {data.meta.latency_ms.toFixed(0)} ms
                    </span>
                  )}

                  {data?.meta?.low_confidence && (
                    <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                      <AlertCircle className="w-3 h-3 text-amber-600" />
                      Broad intent
                    </span>
                  )}

                  {filterOptions.selectedSlot && (
                    <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-0.5 rounded-full bg-brand-900 text-white shadow-2xs">
                      <span>Slot: {formatSlot(filterOptions.selectedSlot)}</span>
                      <button
                        type="button"
                        onClick={() =>
                          setFilterOptions((prev) => ({ ...prev, selectedSlot: null }))
                        }
                        className="hover:text-accent-300 ml-0.5"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  )}
                </>
              )}
            </div>

            {/* Mobile Filter Toggle */}
            <button
              type="button"
              onClick={() => setMobileFilterOpen(true)}
              className="lg:hidden inline-flex items-center gap-2 text-xs uppercase tracking-wider font-semibold px-4 py-2 rounded-full border border-sand-300 bg-white text-sand-800 shadow-xs"
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>Refine Filters</span>
            </button>
          </div>

          {/* Desktop Layout: Sidebar on Left, Results on Right */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-8 items-start">
            {/* Desktop Left Sidebar */}
            <div className="hidden lg:block lg:col-span-1 sticky top-24">
              <div className="bg-white/90 backdrop-blur-md rounded-2xl border border-sand-200/90 p-5 shadow-subtle">
                <FilterSidebar
                  meta={data?.meta}
                  filterOptions={filterOptions}
                  availableSlots={availableSlots}
                  onChangeSlot={(slot) =>
                    setFilterOptions((prev) => ({ ...prev, selectedSlot: slot }))
                  }
                  onChangeSort={(sort) =>
                    setFilterOptions((prev) => ({ ...prev, sortBy: sort }))
                  }
                  onReset={handleResetFilters}
                />
              </div>
            </div>

            {/* Results Grid / Loading / Empty */}
            <div className="lg:col-span-3">
              {status === 'loading' ? (
                <ProductGridSkeleton count={8} />
              ) : filteredAndSortedProducts.length === 0 ? (
                <EmptyState
                  title="No matching apparel found"
                  description={`No items in the catalog matched "${queryParam}". Try relaxing slot filters or exploring our suggested searches.`}
                  suggestions={
                    data?.suggested_queries || [
                      'red cocktail dress',
                      'summer linen blazer',
                      'black running shoes',
                      'pleated silk skirt',
                    ]
                  }
                  onSelectSuggestion={handleSearchSubmit}
                  actionText="Clear Active Filters"
                  onAction={handleResetFilters}
                />
              ) : (
                <ProductGrid products={filteredAndSortedProducts} columns={3} />
              )}
            </div>
          </div>

          {/* Mobile Filter Drawer */}
          <FilterDrawer
            isOpen={mobileFilterOpen}
            onClose={() => setMobileFilterOpen(false)}
            meta={data?.meta}
            filterOptions={filterOptions}
            availableSlots={availableSlots}
            onChangeSlot={(slot) =>
              setFilterOptions((prev) => ({ ...prev, selectedSlot: slot }))
            }
            onChangeSort={(sort) =>
              setFilterOptions((prev) => ({ ...prev, sortBy: sort }))
            }
            onReset={handleResetFilters}
          />
        </div>
      )}
    </div>
  );
};
