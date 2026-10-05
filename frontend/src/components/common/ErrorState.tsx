import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from './Button';
import { ApiErrorMessage } from '../../services/api';

export interface ErrorStateProps {
  error: ApiErrorMessage | null;
  onRetry?: () => void;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ error, onRetry, className = '' }) => {
  const title = error?.title || 'Unable to Load Recommendations';
  const detail =
    error?.detail ||
    'Unable to connect to the recommendation service. Please verify that the backend is running and try again.';

  return (
    <div
      className={`rounded-2xl border border-red-100 bg-red-50/50 p-8 max-w-lg mx-auto text-center ${className}`}
      role="alert"
    >
      <div className="w-12 h-12 rounded-full bg-red-100 text-red-600 flex items-center justify-center mx-auto mb-4">
        <AlertCircle className="w-6 h-6" />
      </div>

      <h3 className="font-serif text-xl font-normal text-brand-900 mb-2">{title}</h3>
      <p className="text-sand-600 text-sm mb-6 leading-relaxed">{detail}</p>

      {onRetry && (
        <Button
          variant="outline"
          size="sm"
          onClick={onRetry}
          icon={<RefreshCw className="w-4 h-4" />}
        >
          Try Again
        </Button>
      )}
    </div>
  );
};
