import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shirt, Footprints, Watch, ArrowUpRight, CheckCircle2 } from 'lucide-react';
import { SearchResultItem } from '../../types/product';
import { formatPrice } from '../../utils/formatPrice';
import { formatSlot } from '../../utils/formatters';
import { isImageKnownBroken, markImageAsBroken } from '../../utils/imageTracker';

export interface OutfitSlotCardProps {
  slotName: 'Top' | 'Bottom' | 'Footwear' | 'Accessory' | 'Full Body' | string;
  item?: SearchResultItem | null;
  isMissing?: boolean;
}

const slotIcons: Record<string, React.ReactNode> = {
  Top: <Shirt className="w-4 h-4 text-accent-600" />,
  Bottom: <Shirt className="w-4 h-4 text-accent-600" />,
  Footwear: <Footprints className="w-4 h-4 text-accent-600" />,
  Accessory: <Watch className="w-4 h-4 text-accent-600" />,
  'Full Body': <Shirt className="w-4 h-4 text-accent-600" />,
};

export const OutfitSlotCard: React.FC<OutfitSlotCardProps> = ({
  slotName,
  item,
  isMissing = false,
}) => {
  const navigate = useNavigate();
  const [imageError, setImageError] = useState(() => isImageKnownBroken(item?.image_url));

  const handleClick = () => {
    if (item) {
      navigate(`/product/${item.product_id}`, { state: { product: item } });
    }
  };

  const handleImageError = () => {
    setImageError(true);
    markImageAsBroken(item?.image_url);
  };

  const hasImage = Boolean(item?.image_url) && !imageError && !isImageKnownBroken(item?.image_url);

  return (
    <div
      onClick={item ? handleClick : undefined}
      className={`group relative bg-white rounded-3xl border border-sand-200 overflow-hidden shadow-subtle transition-all duration-300 flex flex-col justify-between ${
        item ? 'hover:shadow-card hover:-translate-y-1 cursor-pointer' : 'opacity-75'
      }`}
    >
      {/* Top Header Tag */}
      <div className="px-5 pt-4 pb-2 flex items-center justify-between border-b border-sand-100">
        <div className="flex items-center gap-2">
          {slotIcons[slotName] || <Shirt className="w-4 h-4 text-accent-600" />}
          <span className="font-serif text-sm font-medium tracking-wide text-brand-900">
            {slotName}
          </span>
        </div>
        {item ? (
          <span className="flex items-center gap-1 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-medium">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            Selected
          </span>
        ) : (
          <span className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
            {isMissing ? 'Slot Omitted' : 'Optional'}
          </span>
        )}
      </div>

      {/* Image Area */}
      <div className="relative aspect-[4/5] w-full bg-sand-100 overflow-hidden flex items-center justify-center">
        {hasImage ? (
          <img
            src={item!.image_url!}
            alt={item!.title}
            onError={handleImageError}
            className="w-full h-full object-cover object-center group-hover:scale-105 transition-transform duration-500"
          />
        ) : (
          <div className="p-6 text-center text-sand-400">
            <Shirt className="w-12 h-12 stroke-[1] text-sand-300 mx-auto mb-2" />
            <p className="text-xs text-sand-500 uppercase tracking-wider font-medium">
              {item ? formatSlot(item.slot) : `No ${slotName} matched`}
            </p>
          </div>
        )}
      </div>

      {/* Content Area */}
      <div className="p-5 flex-grow flex flex-col justify-between space-y-3">
        {item ? (
          <>
            <div>
              {item.brand && (
                <p className="text-[11px] uppercase tracking-wider font-semibold text-sand-500 mb-1 line-clamp-1">
                  {item.brand}
                </p>
              )}
              <h4
                className="text-sm font-medium text-brand-900 line-clamp-2 leading-snug group-hover:text-black transition-colors"
                title={item.title}
              >
                {item.title}
              </h4>
            </div>

            <div className="pt-2 border-t border-sand-100 flex items-center justify-between">
              <span className="font-serif text-base font-semibold text-brand-900">
                {formatPrice(item.price)}
              </span>

              <span className="inline-flex items-center gap-0.5 text-xs text-sand-600 font-medium group-hover:text-brand-900">
                Details <ArrowUpRight className="w-3.5 h-3.5" />
              </span>
            </div>
          </>
        ) : (
          <div className="py-4 text-center">
            <p className="text-xs text-sand-500">
              No matching item was returned by the recommendation engine for this slot.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
