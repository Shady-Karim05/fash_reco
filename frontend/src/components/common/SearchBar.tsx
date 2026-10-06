import React, { useState } from 'react';
import { Search, X, Sparkles } from 'lucide-react';
import { Button } from './Button';

export interface SearchBarProps {
  initialValue?: string;
  placeholder?: string;
  onSearch: (query: string) => void;
  isLoading?: boolean;
  size?: 'md' | 'lg';
  showPills?: boolean;
  examplePills?: string[];
  className?: string;
}

const DEFAULT_EXAMPLE_PILLS = [
  'red cocktail dress',
  'oversized linen blazer for summer',
  'black waterproof running shoes',
  'vintage leather crossbody bag',
  'cocktail party dress for women under $100',
];

export const SearchBar: React.FC<SearchBarProps> = ({
  initialValue = '',
  placeholder = 'Search by style, occasion, color, cut, or vibe (e.g. "red cocktail dress")...',
  onSearch,
  isLoading = false,
  size = 'md',
  showPills = false,
  examplePills = DEFAULT_EXAMPLE_PILLS,
  className = '',
}) => {
  const [query, setQuery] = useState(initialValue);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      onSearch(query.trim());
    }
  };

  const handleClear = () => {
    setQuery('');
  };

  const handleSelectPill = (pill: string) => {
    setQuery(pill);
    onSearch(pill);
  };

  const isLg = size === 'lg';

  return (
    <div className={`w-full ${className}`}>
      <form onSubmit={handleSubmit} className="relative w-full">
        <div
          className={`flex items-center bg-white rounded-full border border-sand-300 shadow-subtle hover:border-sand-400 focus-within:border-brand-900 focus-within:ring-2 focus-within:ring-brand-900/10 transition-all ${
            isLg ? 'p-2 pl-6' : 'p-1.5 pl-4'
          }`}
        >
          <Search className={`text-sand-400 shrink-0 mr-3 ${isLg ? 'w-5 h-5' : 'w-4 h-4'}`} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={placeholder}
            className={`w-full bg-transparent text-brand-900 placeholder-sand-400 focus:outline-none ${
              isLg ? 'text-base' : 'text-sm'
            }`}
          />
          {query && (
            <button
              type="button"
              onClick={handleClear}
              className="text-sand-400 hover:text-brand-900 p-1 mr-1 transition-colors"
              aria-label="Clear search input"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <Button
            type="submit"
            variant="primary"
            size={isLg ? 'md' : 'sm'}
            isLoading={isLoading}
            disabled={!query.trim()}
          >
            Search
          </Button>
        </div>
      </form>

      {showPills && (
        <div className="mt-4 flex items-center flex-wrap gap-2 justify-center">
          <span className="text-xs text-sand-500 uppercase tracking-wider font-medium flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-accent-600" />
            Try searching:
          </span>
          {examplePills.map((pill, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleSelectPill(pill)}
              className="text-xs bg-sand-100 hover:bg-sand-200 text-sand-700 px-3 py-1 rounded-full transition-colors font-sans"
            >
              {pill}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
