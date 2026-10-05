import { useMutation } from '@tanstack/react-query';
import { recommendOutfit } from '../services/outfitApi';
import { formatApiError, ApiErrorMessage } from '../services/api';
import { OutfitResponse } from '../types/outfit';
import { UiStatus } from './useSearch';

export interface UseOutfitRecommendationResult {
  recommend: (query: string) => void;
  data: OutfitResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  error: ApiErrorMessage | null;
  status: UiStatus;
  reset: () => void;
}

export function useOutfitRecommendation(): UseOutfitRecommendationResult {
  const mutation = useMutation<OutfitResponse, unknown, string>({
    mutationFn: (query: string) => recommendOutfit({ query }),
  });

  let status: UiStatus = 'idle';
  if (mutation.isPending) {
    status = 'loading';
  } else if (mutation.isError) {
    status = 'error';
  } else if (mutation.isSuccess) {
    if (!mutation.data?.outfit || mutation.data.outfit.items.length === 0) {
      status = 'empty';
    } else {
      status = 'success';
    }
  }

  const error: ApiErrorMessage | null = mutation.error ? formatApiError(mutation.error) : null;

  return {
    recommend: (query: string) => mutation.mutate(query),
    data: mutation.data,
    isLoading: mutation.isPending,
    isError: mutation.isError,
    error,
    status,
    reset: mutation.reset,
  };
}
