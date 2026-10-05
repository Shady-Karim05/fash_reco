import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, ArrowUpRight, Shirt } from 'lucide-react';
import { SearchResultItem } from '../../types/product';
import { formatPrice } from '../../utils/formatPrice';
import { formatSlot, formatSimilarity } from '../../utils/formatters';
import { Badge } from '../common/Badge';

import { isImageKnownBroken, markImageAsBroken } from '../../utils/imageTracker';

export interface ProductCardProps {
  product: SearchResultItem;
}

export const ProductCard: React.FC<ProductCardProps> = ({ product }) => {
  const navigate = useNavigate();
  const [imageError, setImageError] = useState(() => isImageKnownBroken(product.image_url));

  const handleCardClick = () => {
    navigate(`/product/${product.product_id}`, {
      state: { product },
    });
  };

  const handleImageError = () => {
    setImageError(true);
    markImageAsBroken(product.image_url);
  };

  const hasImage = Boolean(product.image_url) && !imageError && !isImageKnownBroken(product.image_url);

  return (
    <article
      onClick={handleCardClick}
      className="group relative bg-white rounded-2xl border border-sand-200 overflow-hidden shadow-subtle hover:shadow-card transition-all duration-300 flex flex-col cursor-pointer"
    >
      {/* Image container */}
      <div className="relative aspect-[3/4] w-full bg-sand-100 overflow-hidden">
        {hasImage ? (
          <img
            src={product.image_url!}
            alt={product.title}
            onError={handleImageError}
            loading="lazy"
            decoding="async"
            className="w-full h-full object-cover object-center group-hover:scale-105 transition-transform duration-500 ease-out"
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center text-sand-400 p-4">
            <Shirt className="w-12 h-12 stroke-[1.25] text-sand-300 mb-2" />
            <span className="text-[11px] uppercase tracking-wider text-sand-500 font-medium">
              {formatSlot(product.slot)}
            </span>
          </div>
        )}

        {/* Top Badges */}
        <div className="absolute top-3 left-3 right-3 flex items-center justify-between pointer-events-none">
          {product.slot && (
            <Badge variant="neutral" size="sm" className="bg-white/90 backdrop-blur-sm shadow-xs">
              {formatSlot(product.slot)}
            </Badge>
          )}

          {product.similarity > 0 && (
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand-900/85 backdrop-blur-sm text-white shadow-xs">
              <Sparkles className="w-2.5 h-2.5 text-accent-300" />
              {formatSimilarity(product.similarity)}
            </span>
          )}
        </div>
      </div>

      {/* Product Details */}
      <div className="p-4 flex-grow flex flex-col justify-between space-y-3">
        <div>
          {product.brand && (
            <p className="text-[11px] uppercase tracking-wider font-semibold text-sand-500 mb-1 line-clamp-1">
              {product.brand}
            </p>
          )}
          <h3
            className="text-sm font-medium text-brand-900 line-clamp-2 leading-snug group-hover:text-black transition-colors"
            title={product.title}
          >
            {product.title}
          </h3>
        </div>

        <div className="pt-2 border-t border-sand-100 flex items-center justify-between">
          <div className="font-serif text-base font-semibold text-brand-900">
            {formatPrice(product.price)}
          </div>

          <button
            type="button"
            className="inline-flex items-center gap-0.5 text-xs text-sand-600 font-medium group-hover:text-brand-900 transition-colors"
            aria-label={`View details for ${product.title}`}
          >
            <span>View</span>
            <ArrowUpRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </button>
        </div>
      </div>
    </article>
  );
};
