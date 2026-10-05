/**
 * General text and badge formatting utilities.
 */

export function capitalize(str: string | null | undefined): string {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

export function formatSlot(slot: string | null | undefined): string {
  if (!slot || slot === 'unknown') return 'Apparel';
  const mapping: Record<string, string> = {
    top: 'Top & Shirts',
    bottom: 'Bottoms & Pants',
    footwear: 'Footwear',
    accessory: 'Accessories',
    full_body: 'Dresses & One-Piece',
    innerwear: 'Innerwear',
  };
  return mapping[slot.toLowerCase()] || capitalize(slot.replace(/_/g, ' '));
}

export function formatSimilarity(similarity: number | null | undefined): string {
  if (similarity === null || similarity === undefined || isNaN(similarity)) return '0%';
  const clamped = Math.max(0, Math.min(1, similarity));
  return `${Math.round(clamped * 100)}% match`;
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined || isNaN(score)) return '0.00';
  return score.toFixed(2);
}
