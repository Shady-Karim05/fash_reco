import { useQuery } from '@tanstack/react-query';
import { searchProducts } from '../services/searchApi';
import { formatApiError, ApiErrorMessage } from '../services/api';
import { SearchResponse } from '../types/search';

export type UiStatus = 'idle' | 'loading' | 'success' | 'empty' | 'error';

export interface UseSearchResult {
  data: SearchResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  error: ApiErrorMessage | null;
  status: UiStatus;
  refetch: () => void;
}

export function useSearch(query: string, topK: number = 24): UseSearchResult {
  const cleanQuery = query.trim();

  const queryInfo = useQuery<SearchResponse, unknown>({
    queryKey: ['search', cleanQuery, topK],
    queryFn: ({ signal }) => searchProducts({ query: cleanQuery, top_k: topK }, signal),
    enabled: cleanQuery.length > 0,
    staleTime: 1000 * 60 * 5, // 5 mins
    gcTime: 1000 * 60 * 15, // 15 mins
    retry: 1,
  });

  let status: UiStatus = 'idle';
  if (!cleanQuery) {
    status = 'idle';
  } else if (queryInfo.isLoading) {
    status = 'loading';
  } else if (queryInfo.isError) {
    status = 'error';
  } else if (queryInfo.isSuccess) {
    if (!queryInfo.data?.results || queryInfo.data.results.length === 0) {
      status = 'empty';
    } else {
      status = 'success';
    }
  }

  const error: ApiErrorMessage | null = queryInfo.error ? formatApiError(queryInfo.error) : null;

  return {
    data: queryInfo.data,
    isLoading: queryInfo.isLoading,
    isError: queryInfo.isError,
    error,
    status,
    refetch: queryInfo.refetch,
  };
}
