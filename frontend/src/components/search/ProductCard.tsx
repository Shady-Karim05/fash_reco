import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, ArrowUpRight, Shirt } from 'lucide-react';
import { SearchResultItem } from '../../types/product';
import { formatPrice } from '../../utils/formatPrice';
import { formatSlot, formatSimilarity } from '../../utils/formatters';
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
      className="group relative bg-white rounded-2xl border border-sand-200/80 overflow-hidden shadow-subtle hover:shadow-premium hover:-translate-y-1.5 transition-all duration-350 flex flex-col cursor-pointer"
    >
      {/* Luxury Product Visual Presentation */}
      <div className="relative aspect-[3/4] w-full bg-sand-100/70 overflow-hidden">
        {hasImage ? (
          <img
            src={product.image_url!}
            alt={product.title}
            onError={handleImageError}
            loading="lazy"
            decoding="async"
            className="w-full h-full object-cover object-center group-hover:scale-106 transition-transform duration-700 ease-out"
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center text-sand-400 p-6 bg-gradient-to-b from-sand-50 to-sand-100/70">
            <div className="w-16 h-16 rounded-full bg-white/80 border border-sand-200 flex items-center justify-center mb-3 shadow-2xs group-hover:scale-105 transition-transform">
              <Shirt className="w-8 h-8 stroke-[1.2] text-sand-400" />
            </div>
            <span className="text-[11px] uppercase tracking-[0.18em] text-sand-500 font-medium">
              {formatSlot(product.slot)}
            </span>
          </div>
        )}

        {/* Ambient Top Badges */}
        <div className="absolute top-3 left-3 right-3 flex items-center justify-between pointer-events-none">
          {product.slot && (
            <span className="text-[10px] uppercase tracking-wider font-semibold px-2.5 py-1 rounded-full bg-white/92 backdrop-blur-md text-brand-900 border border-sand-200/80 shadow-2xs">
              {formatSlot(product.slot)}
            </span>
          )}

          {product.similarity > 0 && (
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2.5 py-1 rounded-full bg-brand-950/88 backdrop-blur-md text-white shadow-2xs border border-white/10">
              <Sparkles className="w-2.5 h-2.5 text-accent-400" />
              <span>{formatSimilarity(product.similarity)}</span>
            </span>
          )}
        </div>

        {/* Subtle Bottom Image Gradient on Hover */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/20 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
      </div>

      {/* Product Details Section */}
      <div className="p-4.5 flex-grow flex flex-col justify-between space-y-3 bg-white">
        <div className="space-y-1">
          {product.brand ? (
            <p className="text-[11px] uppercase tracking-[0.15em] font-semibold text-accent-700 line-clamp-1">
              {product.brand}
            </p>
          ) : (
            <p className="text-[11px] uppercase tracking-[0.15em] font-medium text-sand-400 line-clamp-1">
              {formatSlot(product.slot)}
            </p>
          )}

          <h3
            className="text-sm font-medium text-brand-900 line-clamp-2 leading-snug group-hover:text-black transition-colors"
            title={product.title}
          >
            {product.title}
          </h3>
        </div>

        <div className="pt-2.5 border-t border-sand-100/90 flex items-center justify-between">
          <div className="font-serif text-lg font-normal text-brand-950">
            {formatPrice(product.price)}
          </div>

          <span className="inline-flex items-center gap-1 text-xs text-sand-600 font-medium group-hover:text-brand-900 transition-colors">
            <span>Details</span>
            <ArrowUpRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </span>
        </div>
      </div>
    </article>
  );
};
