import React from 'react';
import { SearchX, Sparkles } from 'lucide-react';
import { Button } from './Button';

export interface EmptyStateProps {
  title?: string;
  description?: string;
  actionText?: string;
  onAction?: () => void;
  suggestions?: string[];
  onSelectSuggestion?: (query: string) => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'No products found',
  description = 'We could not find items matching your semantic search. Try adjusting terms, keywords, or filters.',
  actionText,
  onAction,
  suggestions,
  onSelectSuggestion,
}) => {
  return (
    <div className="text-center py-16 px-4 max-w-lg mx-auto flex flex-col items-center">
      <div className="w-16 h-16 rounded-full bg-sand-100 flex items-center justify-center text-sand-500 mb-6">
        <SearchX className="w-8 h-8" />
      </div>

      <h3 className="font-serif text-2xl font-normal text-brand-900 mb-3">{title}</h3>
      <p className="text-sand-600 text-sm leading-relaxed mb-6">{description}</p>

      {suggestions && suggestions.length > 0 && (
        <div className="mb-6 w-full">
          <p className="text-xs uppercase tracking-wider text-sand-500 font-semibold mb-3 flex items-center justify-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-accent-600" />
            Suggested Searches
          </p>
          <div className="flex flex-wrap gap-2 justify-center">
            {suggestions.map((s, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => onSelectSuggestion?.(s)}
                className="text-xs bg-white border border-sand-200 hover:border-brand-900 text-sand-800 px-3 py-1.5 rounded-full transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {actionText && onAction && (
        <Button variant="outline" size="sm" onClick={onAction}>
          {actionText}
        </Button>
      )}
    </div>
  );
};
