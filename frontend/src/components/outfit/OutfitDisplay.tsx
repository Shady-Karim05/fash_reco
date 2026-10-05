import React from 'react';
import { OutfitPayload } from '../../types/outfit';
import { SearchMeta } from '../../types/search';
import { BudgetSummary } from './BudgetSummary';
import { OutfitSlotCard } from './OutfitSlotCard';
import { SearchResultItem } from '../../types/product';

export interface OutfitDisplayProps {
  outfit: OutfitPayload;
  meta: SearchMeta;
}

export const OutfitDisplay: React.FC<OutfitDisplayProps> = ({ outfit, meta }) => {
  const items = outfit.items || [];

  // Map backend items by slot
  const topItem = items.find((i) => i.slot === 'top');
  const bottomItem = items.find((i) => i.slot === 'bottom');
  const fullBodyItem = items.find((i) => i.slot === 'full_body');
  const footwearItem = items.find((i) => i.slot === 'footwear');
  const accessoryItem = items.find((i) => i.slot === 'accessory');

  // Any additional items returned by the backend (e.g. secondary accessories, innerwear)
  const otherItems = items.filter(
    (i) =>
      i !== topItem &&
      i !== bottomItem &&
      i !== fullBodyItem &&
      i !== footwearItem &&
      i !== accessoryItem
  );

  const missingSlots = outfit.missing_slots || [];

  // If a full-body piece (e.g. dress / jumpsuit) is present, display Full Body instead of separate top/bottom
  const isFullBody = Boolean(fullBodyItem);

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Top Banner with Total Price & Budget */}
      <BudgetSummary outfit={outfit} meta={meta} />

      {/* Main 4-Slot Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {isFullBody ? (
          <OutfitSlotCard
            slotName="Full Body"
            item={fullBodyItem}
            isMissing={missingSlots.includes('full_body')}
          />
        ) : (
          <>
            <OutfitSlotCard
              slotName="Top"
              item={topItem}
              isMissing={missingSlots.includes('top')}
            />
            <OutfitSlotCard
              slotName="Bottom"
              item={bottomItem}
              isMissing={missingSlots.includes('bottom')}
            />
          </>
        )}

        {/* If isFullBody is true and only 3 slots, top/bottom is 1 slot, so we can show footwear and accessory */}
        <OutfitSlotCard
          slotName="Footwear"
          item={footwearItem}
          isMissing={missingSlots.includes('footwear')}
        />

        <OutfitSlotCard
          slotName="Accessory"
          item={accessoryItem}
          isMissing={missingSlots.includes('accessory')}
        />

        {/* If isFullBody is true, there is an extra column space in a 4-col grid: fill it with secondary accessory or top pick */}
        {isFullBody && otherItems.length > 0 && (
          <OutfitSlotCard
            slotName="Accent Piece"
            item={otherItems[0]}
            isMissing={false}
          />
        )}
      </div>

      {/* Additional coordinated pieces if returned */}
      {otherItems.length > (isFullBody ? 1 : 0) && (
        <div className="pt-6 border-t border-sand-200">
          <h4 className="text-xs uppercase tracking-wider font-semibold text-sand-600 mb-4">
            Additional Recommended Accents
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {otherItems.slice(isFullBody ? 1 : 0).map((item: SearchResultItem) => (
              <OutfitSlotCard
                key={item.product_id}
                slotName={item.accessory_type || item.slot}
                item={item}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
