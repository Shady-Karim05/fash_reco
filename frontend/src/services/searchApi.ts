import { apiClient } from './api';
import { SearchRequest, SearchResponse } from '../types/search';

/**
 * Executes semantic / keyword fashion search via POST /search.
 */
export async function searchProducts(
  params: SearchRequest,
  signal?: AbortSignal
): Promise<SearchResponse> {
  const payload: SearchRequest = {
    query: params.query.trim(),
    top_k: params.top_k ?? 20,
    mode: params.mode ?? 'product',
  };

  const response = await apiClient.post<SearchResponse>('/search', payload, { signal });
  return response.data;
}

/**
 * Checks backend microservice health status via GET /health.
 */
export async function getHealthStatus(): Promise<{
  status: string;
  index_loaded: boolean;
  catalog_size: number;
  llm_status: string;
}> {
  const response = await apiClient.get('/health');
  return response.data;
}
