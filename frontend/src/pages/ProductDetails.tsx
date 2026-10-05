import React, { useState, useEffect } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Sparkles,
  Shirt,
  Shield,
  Layers,
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

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-16 text-center">
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
      <div className="max-w-xl mx-auto px-4 py-20 text-center space-y-6">
        <h2 className="font-serif text-2xl text-brand-900">Product Information Unavailable</h2>
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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Breadcrumb / Back button */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1.5 text-xs uppercase tracking-wider font-semibold text-sand-600 hover:text-brand-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>

        <span className="text-xs font-mono text-sand-400">ID: {product.product_id}</span>
      </div>

      {/* Main Product Layout */}
      <div className="bg-white rounded-3xl border border-sand-200 p-6 sm:p-10 shadow-subtle grid grid-cols-1 md:grid-cols-2 gap-10 items-start">
        {/* Left: Product Image */}
        <div className="relative aspect-[3/4] w-full bg-sand-100 rounded-2xl overflow-hidden flex items-center justify-center">
          {hasImage ? (
            <img
              src={product.image_url!}
              alt={product.title}
              onError={() => setImageError(true)}
              className="w-full h-full object-cover object-center"
            />
          ) : (
            <div className="text-center p-8 text-sand-400">
              <Shirt className="w-16 h-16 stroke-[1] text-sand-300 mx-auto mb-3" />
              <p className="text-xs uppercase tracking-wider font-medium text-sand-500">
                {formatSlot(product.slot)}
              </p>
            </div>
          )}

          {product.similarity > 0 && (
            <div className="absolute top-4 left-4">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1 rounded-full bg-brand-900/90 text-white backdrop-blur-sm shadow-xs">
                <Sparkles className="w-3.5 h-3.5 text-accent-300" />
                {formatSimilarity(product.similarity)}
              </span>
            </div>
          )}
        </div>

        {/* Right: Product Metadata */}
        <div className="space-y-6">
          <div>
            {product.brand && (
              <p className="text-xs uppercase tracking-widest font-semibold text-sand-500 mb-2">
                {product.brand}
              </p>
            )}
            <h1 className="font-serif text-2xl sm:text-3xl font-normal text-brand-900 leading-snug">
              {product.title}
            </h1>
          </div>

          <div className="flex items-baseline gap-4 pb-4 border-b border-sand-100">
            <span className="font-serif text-3xl font-semibold text-brand-900">
              {formatPrice(product.price)}
            </span>
          </div>

          {/* Core Verified Attributes from Backend */}
          <div className="space-y-3">
            <h3 className="text-xs uppercase tracking-wider font-semibold text-sand-700">
              Catalog Attributes
            </h3>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 bg-sand-50 rounded-xl border border-sand-100">
                <span className="text-sand-500 block text-[11px] mb-0.5">Category Slot</span>
                <span className="font-medium text-brand-900">{formatSlot(product.slot)}</span>
              </div>

              {product.accessory_type && (
                <div className="p-3 bg-sand-50 rounded-xl border border-sand-100">
                  <span className="text-sand-500 block text-[11px] mb-0.5">Accessory Type</span>
                  <span className="font-medium text-brand-900 capitalize">
                    {product.accessory_type.replace(/_/g, ' ')}
                  </span>
                </div>
              )}

              {product.gender && product.gender !== 'unknown' && (
                <div className="p-3 bg-sand-50 rounded-xl border border-sand-100">
                  <span className="text-sand-500 block text-[11px] mb-0.5">Target Audience</span>
                  <span className="font-medium text-brand-900 capitalize">
                    {product.gender}
                  </span>
                </div>
              )}

              {product.age_group && (
                <div className="p-3 bg-sand-50 rounded-xl border border-sand-100">
                  <span className="text-sand-500 block text-[11px] mb-0.5">Age Group</span>
                  <span className="font-medium text-brand-900 capitalize">
                    {product.age_group}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Engine Scoring Insights */}
          <div className="p-4 bg-sand-50/70 rounded-2xl border border-sand-200/80 space-y-2 text-xs">
            <span className="font-semibold text-brand-900 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-accent-600" />
              Retrieval Intelligence
            </span>
            <div className="grid grid-cols-2 gap-2 text-sand-600">
              <div>
                <span className="text-sand-500">Calibrated Rank Score:</span>{' '}
                <span className="font-mono font-medium text-brand-900">
                  {product.score.toFixed(4)}
                </span>
              </div>
              <div>
                <span className="text-sand-500">Dense Cosine Similarity:</span>{' '}
                <span className="font-mono font-medium text-brand-900">
                  {product.similarity.toFixed(4)}
                </span>
              </div>
            </div>
            {product.reason && (
              <p className="text-sand-600 text-[11px] italic pt-1 border-t border-sand-200">
                &ldquo;{product.reason}&rdquo;
              </p>
            )}
          </div>

          {/* Action CTAs */}
          <div className="pt-4 flex flex-col sm:flex-row gap-3">
            <Button
              variant="primary"
              size="md"
              onClick={() =>
                navigate(`/outfit?q=${encodeURIComponent(`outfit with ${product.title}`)}`)
              }
              icon={<Layers className="w-4 h-4" />}
            >
              Style in an Outfit
            </Button>
            <Button
              variant="outline"
              size="md"
              onClick={() =>
                navigate(`/search?q=${encodeURIComponent(product.brand || product.slot)}`)
              }
            >
              Similar {product.brand || formatSlot(product.slot)}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
