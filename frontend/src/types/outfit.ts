import { SearchResultItem } from './product';
import { SearchMeta } from './search';

export interface OutfitPayload {
  items: SearchResultItem[];
  total_price: number;
  complete: boolean;
  missing_slots: string[];
  template: string;
}

export interface OutfitRequest {
  query: string;
}

export interface OutfitResponse {
  outfit: OutfitPayload | null;
  meta: SearchMeta;
  message?: string | null;
  suggested_queries?: string[] | null;
}
