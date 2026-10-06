import React, { useState, useEffect } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Sparkles,
  Shirt,
  Shield,
  Search,
  Check,
  Tag,
  Compass,
} from 'lucide-react';
import { SearchResultItem } from '../types/product';
import { formatPrice } from '../utils/formatPrice';
import { formatSlot, formatSimilarity } from '../utils/formatters';
import { Button } from '../components/common/Button';
import { searchProducts } from '../services/searchApi';

export const ProductDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  // Try retrieving product from router navigation state
  const stateProduct = (location.state as { product?: SearchResultItem })?.product;

  const [product, setProduct] = useState<SearchResultItem | null>(stateProduct || null);
  const [loading, setLoading] = useState<boolean>(!stateProduct);
  const [imageError, setImageError] = useState(false);
  const [copiedId, setCopiedId] = useState(false);

  useEffect(() => {
    if (!stateProduct && id) {
      setLoading(true);
      // Query backend for this product id
      searchProducts({ query: id, top_k: 1 })
        .then((res) => {
          const match = res.results.find((r) => r.product_id === id) || res.results[0];
          if (match) {
            setProduct(match);
          }
        })
        .catch(() => {
          // Graceful handling
        })
        .finally(() => setLoading(false));
    }
  }, [id, stateProduct]);

  const handleCopyId = () => {
    if (product) {
      navigator.clipboard.writeText(product.product_id);
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 2000);
    }
  };

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-20 text-center">
        <div className="animate-pulse space-y-6 max-w-xl mx-auto">
          <div className="aspect-[3/4] bg-sand-200 rounded-3xl" />
          <div className="h-6 bg-sand-200 rounded w-3/4 mx-auto" />
          <div className="h-4 bg-sand-200 rounded w-1/2 mx-auto" />
        </div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="max-w-xl mx-auto px-4 py-24 text-center space-y-6">
        <h2 className="font-serif text-3xl text-brand-900 font-light">Product Unavailable</h2>
        <p className="text-sand-600 text-sm">
          No detailed records were returned for item ID &ldquo;{id}&rdquo;.
        </p>
        <Button variant="primary" onClick={() => navigate('/search')}>
          Back to Search Catalog
        </Button>
      </div>
    );
  }

  const hasImage = Boolean(product.image_url) && !imageError;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      {/* Editorial Breadcrumbs & Top Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-sand-200/80 pb-4">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] font-semibold text-sand-600 hover:text-brand-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Results</span>
        </button>

        <div className="flex items-center gap-3">
          <span className="text-[11px] font-mono text-sand-400">
            SKU: {product.product_id}
          </span>
          <button
            type="button"
            onClick={handleCopyId}
            className="text-[11px] px-2.5 py-1 rounded-full bg-sand-100 hover:bg-sand-200 text-sand-700 transition-colors inline-flex items-center gap-1 font-sans"
            title="Copy SKU identifier"
          >
            {copiedId ? (
              <>
                <Check className="w-3 h-3 text-emerald-600" />
                <span className="text-emerald-700 font-medium">Copied</span>
              </>
            ) : (
              <span>Copy SKU</span>
            )}
          </button>
        </div>
      </div>

      {/* Main Product Showcase Layout */}
      <div className="bg-white rounded-3xl border border-sand-200/90 p-6 sm:p-10 lg:p-12 shadow-premium grid grid-cols-1 lg:grid-cols-12 gap-12 items-start">
        {/* Left: Product Visual Presentation (5 cols) */}
        <div className="lg:col-span-5 relative aspect-[3/4] w-full bg-sand-100/70 rounded-2xl overflow-hidden flex items-center justify-center border border-sand-200/60 shadow-xs">
          {hasImage ? (
            <img
              src={product.image_url!}
              alt={product.title}
              onError={() => setImageError(true)}
              className="w-full h-full object-cover object-center"
            />
          ) : (
            <div className="text-center p-8 text-sand-400 flex flex-col items-center">
              <div className="w-20 h-20 rounded-full bg-white border border-sand-200 flex items-center justify-center mb-4 shadow-xs">
                <Shirt className="w-10 h-10 stroke-[1.2] text-sand-400" />
              </div>
              <p className="text-xs uppercase tracking-[0.2em] font-medium text-sand-500">
                {formatSlot(product.slot)}
              </p>
            </div>
          )}

          {product.similarity > 0 && (
            <div className="absolute top-4 left-4">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-3.5 py-1.5 rounded-full bg-brand-950/90 text-white backdrop-blur-md shadow-sm border border-white/10">
                <Sparkles className="w-3.5 h-3.5 text-accent-400" />
                <span>{formatSimilarity(product.similarity)}</span>
              </span>
            </div>
          )}
        </div>

        {/* Right: Product Editorial Details (7 cols) */}
        <div className="lg:col-span-7 space-y-7">
          <div className="space-y-2">
            {product.brand ? (
              <span className="inline-block text-xs uppercase tracking-[0.2em] font-semibold text-accent-700">
                {product.brand}
              </span>
            ) : (
              <span className="inline-block text-xs uppercase tracking-[0.2em] font-medium text-sand-400">
                Atelier Catalog
              </span>
            )}
            <h1 className="font-serif text-3xl sm:text-4xl font-normal text-brand-900 leading-tight">
              {product.title}
            </h1>
          </div>

          <div className="flex items-baseline gap-4 pb-6 border-b border-sand-100">
            <span className="font-serif text-3xl sm:text-4xl font-medium text-brand-950">
              {formatPrice(product.price)}
            </span>
            <span className="text-xs text-sand-500 font-medium px-2.5 py-1 rounded-md bg-sand-100/70 border border-sand-200/60">
              Verified Catalog Item
            </span>
          </div>

          {/* Core Catalog Attributes */}
          <div className="space-y-3">
            <h3 className="text-xs uppercase tracking-[0.18em] font-semibold text-sand-700 flex items-center gap-1.5">
              <Tag className="w-3.5 h-3.5 text-accent-600" />
              <span>Garment Metadata</span>
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
              <div className="p-3.5 bg-sand-50/70 rounded-2xl border border-sand-100">
                <span className="text-sand-400 block text-[10px] uppercase tracking-wider mb-1">
                  Category Slot
                </span>
                <span className="font-medium text-brand-900">{formatSlot(product.slot)}</span>
              </div>

              {product.accessory_type && (
                <div className="p-3.5 bg-sand-50/70 rounded-2xl border border-sand-100">
                  <span className="text-sand-400 block text-[10px] uppercase tracking-wider mb-1">
                    Accessory Type
                  </span>
                  <span className="font-medium text-brand-900 capitalize">
                    {product.accessory_type.replace(/_/g, ' ')}
                  </span>
                </div>
              )}

              {product.gender && product.gender !== 'unknown' && (
                <div className="p-3.5 bg-sand-50/70 rounded-2xl border border-sand-100">
                  <span className="text-sand-400 block text-[10px] uppercase tracking-wider mb-1">
                    Audience
                  </span>
                  <span className="font-medium text-brand-900 capitalize">
                    {product.gender}
                  </span>
                </div>
              )}

              {product.age_group && (
                <div className="p-3.5 bg-sand-50/70 rounded-2xl border border-sand-100">
                  <span className="text-sand-400 block text-[10px] uppercase tracking-wider mb-1">
                    Demographic
                  </span>
                  <span className="font-medium text-brand-900 capitalize">
                    {product.age_group}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* AI Neural Retrieval Insights */}
          <div className="p-5 bg-sand-50/80 rounded-2xl border border-sand-200/90 space-y-3 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-brand-900 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-accent-600" />
                <span>Neural Retrieval Scoring</span>
              </span>
              <span className="text-[10px] font-mono text-sand-500">
                Hybrid RRF + FAISS
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sand-600">
              <div className="p-2.5 bg-white rounded-xl border border-sand-200/60">
                <span className="text-sand-400 block text-[10px] uppercase tracking-wider">
                  Calibrated Rank Score
                </span>
                <span className="font-mono text-sm font-semibold text-brand-900">
                  {product.score.toFixed(4)}
                </span>
              </div>
              <div className="p-2.5 bg-white rounded-xl border border-sand-200/60">
                <span className="text-sand-400 block text-[10px] uppercase tracking-wider">
                  Cosine Similarity
                </span>
                <span className="font-mono text-sm font-semibold text-brand-900">
                  {product.similarity.toFixed(4)}
                </span>
              </div>
            </div>

            {product.reason && (
              <p className="text-sand-700 text-xs italic pt-2 border-t border-sand-200/70">
                &ldquo;{product.reason}&rdquo;
              </p>
            )}
          </div>

          {/* Action CTAs: Removed outfit button, focused on search discovery */}
          <div className="pt-2 flex flex-col sm:flex-row gap-3.5">
            <Button
              variant="primary"
              size="lg"
              onClick={() =>
                navigate(`/search?q=${encodeURIComponent(product.brand || product.slot)}`)
              }
              icon={<Search className="w-4 h-4 text-accent-300" />}
              className="flex-1 shadow-sm hover:shadow-md"
            >
              Explore Similar Looks
            </Button>
            <Button
              variant="outline"
              size="lg"
              onClick={() =>
                navigate(`/search?q=${encodeURIComponent(formatSlot(product.slot))}`)
              }
              icon={<Compass className="w-4 h-4 text-sand-500" />}
              className="flex-1"
            >
              Browse {formatSlot(product.slot)}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
