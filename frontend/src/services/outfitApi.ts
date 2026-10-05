import { apiClient } from './api';
import { OutfitRequest, OutfitResponse } from '../types/outfit';

/**
 * Generates an end-to-end coordinated outfit recommendation via POST /outfit.
 */
export async function recommendOutfit(
  params: OutfitRequest,
  signal?: AbortSignal
): Promise<OutfitResponse> {
  const payload = {
    query: params.query.trim(),
  };

  const response = await apiClient.post<OutfitResponse>('/outfit', payload, { signal });
  return response.data;
}
