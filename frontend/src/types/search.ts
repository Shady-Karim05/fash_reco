import { SearchResultItem } from './product';

export interface SearchFiltersMeta {
  occasion?: string | null;
  season?: string | null;
  gender?: string | null;
  age_group?: string | null;
  max_price?: number | null;
  min_price?: number | null;
  brand?: string | null;
  colors?: string[];
  slots?: string[];
  language?: string;
  [key: string]: unknown;
}

export interface SearchMeta {
  parsed_filters: SearchFiltersMeta;
  used_fallback: boolean;
  latency_ms: number;
  index_version: number;
  excluded_by_filters: number;
  duplicates_collapsed?: number;
  low_confidence?: boolean;
  warnings?: string[];
}

export interface SearchRequest {
  query: string;
  top_k?: number;
  mode?: 'products' | 'product' | 'outfit';
}

export interface SearchResponse {
  results: SearchResultItem[];
  meta: SearchMeta;
  message?: string | null;
  suggested_queries?: string[] | null;
}
