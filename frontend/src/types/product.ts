/**
 * Product domain contracts matching FastAPI backend schemas.
 */

export type GenderType = 'men' | 'women' | 'unisex' | 'unknown';
export type AgeGroupType = 'adult' | 'kids';
export type SlotType = 'top' | 'bottom' | 'full_body' | 'footwear' | 'accessory' | 'innerwear' | 'unknown';

export interface SearchResultItem {
  product_id: string;
  title: string;
  price: number | null;
  brand: string | null;
  image_url: string | null;
  slot: SlotType | string;
  accessory_type?: string | null;
  gender: GenderType | string;
  age_group: AgeGroupType | string;
  score: number;
  similarity: number;
  reason?: string | null;
}

export interface ProductDetailsModel extends SearchResultItem {
  store?: string | null;
  average_rating?: number | null;
  rating_number?: number | null;
  quality_score?: number;
  colors?: string[];
  seasons?: string[];
  occasions?: string[];
  features?: string[];
  description?: string | null;
}
