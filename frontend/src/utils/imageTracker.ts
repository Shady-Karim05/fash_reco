/**
 * Global broken image URL tracker to avoid repeated failed network requests (Phase 8).
 */

const brokenImageUrls = new Set<string>();

export function isImageKnownBroken(url: string | null | undefined): boolean {
  if (!url) return true;
  return brokenImageUrls.has(url);
}

export function markImageAsBroken(url: string | null | undefined): void {
  if (url) {
    brokenImageUrls.add(url);
  }
}
