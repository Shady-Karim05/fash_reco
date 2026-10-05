/**
 * Formats a numeric price into a localized currency string.
 * Gracefully handles null, undefined, or invalid price values.
 */
export function formatPrice(price: number | null | undefined, currency: string = 'USD'): string {
  if (price === null || price === undefined || isNaN(price)) {
    return 'Price on request';
  }

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
}
