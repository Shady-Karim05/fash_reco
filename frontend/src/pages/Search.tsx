import React, { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { SlidersHorizontal, Sparkles, AlertCircle } from 'lucide-react';
import { useSearch } from '../hooks/useSearch';
import { SearchBar } from '../components/common/SearchBar';
import { ProductGrid } from '../components/search/ProductGrid';
import { ProductGridSkeleton } from '../components/common/Skeleton';
import { FilterSidebar, FilterOptions } from '../components/search/FilterSidebar';
import { FilterDrawer } from '../components/search/FilterDrawer';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';

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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Search Header */}
      <div className="max-w-3xl mx-auto text-center space-y-4">
        <h1 className="font-serif text-3xl sm:text-4xl text-brand-900 font-light">
          Catalog Semantic Search
        </h1>
        <SearchBar
          initialValue={queryParam}
          placeholder="Describe items by style, fabric, cut, color, or vibe..."
          onSearch={handleSearchSubmit}
          isLoading={isLoading}
          size="md"
        />
      </div>

      {/* Main Content Layout */}
      {status === 'idle' ? (
        <div className="text-center py-20 bg-white rounded-3xl border border-sand-200 p-8 max-w-2xl mx-auto shadow-subtle space-y-6">
          <div className="w-16 h-16 rounded-full bg-sand-100 flex items-center justify-center text-accent-700 mx-auto">
            <Sparkles className="w-8 h-8" />
          </div>
          <div>
            <h2 className="font-serif text-2xl text-brand-900">Discover Fashion Semantically</h2>
            <p className="text-sm text-sand-600 mt-2 max-w-md mx-auto">
              Type naturally. You can describe an event, an aesthetic, a color scheme, or a specific
              apparel item.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 justify-center pt-2">
            {[
              'red cocktail dress',
              'black running sneakers',
              'oversized beige blazer',
              'pleated silk maxi skirt',
              'vintage leather jacket',
            ].map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => handleSearchSubmit(q)}
                className="text-xs bg-sand-100 hover:bg-sand-200 text-sand-800 px-3.5 py-1.5 rounded-full transition-colors font-medium"
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
          {/* Status bar & mobile filter trigger */}
          <div className="flex items-center justify-between border-b border-sand-200 pb-4">
            <div>
              {status === 'loading' ? (
                <div className="h-5 w-48 bg-sand-200 animate-pulse rounded" />
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-brand-900">
                    {filteredAndSortedProducts.length}{' '}
                    {filteredAndSortedProducts.length === 1 ? 'result' : 'results'}
                  </span>
                  <span className="text-xs text-sand-400">for &ldquo;{queryParam}&rdquo;</span>
                  {data?.meta?.low_confidence && (
                    <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                      <AlertCircle className="w-3 h-3 text-amber-600" />
                      Low confidence query
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Mobile filter toggle button */}
            <button
              type="button"
              onClick={() => setMobileFilterOpen(true)}
              className="lg:hidden inline-flex items-center gap-1.5 text-xs uppercase tracking-wider font-semibold px-3 py-2 rounded-full border border-sand-300 bg-white text-sand-700 shadow-xs"
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>Filters</span>
            </button>
          </div>

          {/* Desktop Layout: Sidebar on Left, Results on Right */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-8 items-start">
            {/* Desktop Left Sidebar */}
            <div className="hidden lg:block lg:col-span-1 sticky top-24">
              <FilterSidebar
                meta={data?.meta}
                filterOptions={filterOptions}
                availableSlots={availableSlots}
                onChangeSlot={(slot) => setFilterOptions((prev) => ({ ...prev, selectedSlot: slot }))}
                onChangeSort={(sort) => setFilterOptions((prev) => ({ ...prev, sortBy: sort }))}
                onReset={handleResetFilters}
              />
            </div>

            {/* Results Grid / Loading / Empty */}
            <div className="lg:col-span-3">
              {status === 'loading' ? (
                <ProductGridSkeleton count={8} />
              ) : filteredAndSortedProducts.length === 0 ? (
                <EmptyState
                  title="No items found"
                  description={`No products matched "${queryParam}". Try relaxing filters or testing one of our suggested searches below.`}
                  suggestions={data?.suggested_queries || [
                    'red cocktail dress',
                    'casual summer dress',
                    'black running shoes',
                  ]}
                  onSelectSuggestion={handleSearchSubmit}
                  actionText="Clear All Filters"
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
            onChangeSlot={(slot) => setFilterOptions((prev) => ({ ...prev, selectedSlot: slot }))}
            onChangeSort={(sort) => setFilterOptions((prev) => ({ ...prev, sortBy: sort }))}
            onReset={handleResetFilters}
          />
        </div>
      )}
    </div>
  );
};
