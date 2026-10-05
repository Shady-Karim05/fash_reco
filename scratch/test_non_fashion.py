"""Refined non-fashion filter with wearable guardrails."""

import sqlite3
import re

# Strong fashion accessory / garment indicators that override false positives
FASHION_OVERRIDE_PATTERN = re.compile(
    r"\b(?:"
    r"watch\s+band|watch\s+strap|iwatch\s+band|apple\s+watch\s+band|"
    r"enamel\s+pin|lapel\s+pin|brooch|charm|pendant|necklace|bracelet|earrings?|"
    r"beanie|knitted\s+cap|costume|cosplay"
    r")\b",
    re.IGNORECASE
)

STRONG_NON_FASHION = re.compile(
    r"\b(?:"
    # Electronics & computer parts (not watch bands)
    r"usb\s+cable|phone\s+case|screen\s+protector|charger|earbuds|headphones|bluetooth\s+speaker|"
    r"camera\s+mount|stylus\s+pen|battery\s+pack|audio\s+cable|"
    # Automotive & mechanical
    r"license\s+plate|car\s+seat\s+cover|steering\s+wheel\s+cover|floor\s+mat|bumper\s+sticker|"
    r"tire\s+pressure|valve\s+stem|spark\s+plug|oil\s+filter|"
    # Home improvement, plumbing, hardware (not charm)
    r"pipe\s+connector|brass\s+valve|pipe\s+fitting|pvc\s+fitting|shower\s+head|light\s+bulb|"
    r"screwdriver|wrench|drill\s+bit|door\s+knob|cabinet\s+pull|curtain\s+rod|switch\s+plate|"
    # Musical instruments accessories
    r"guitar\s+strap|guitar\s+pick|guitar\s+cable|drum\s+stick|violin\s+bow|bell\s+incredibell|action\s+bell|"
    # Office, paper, books
    r"paperweight|pen\s+holder|desk\s+organizer|bookmark|"
    # Raw crystals, uncut rocks, specimens (not cut gemstones set in jewelry)
    r"uncut\s+raw\s+rough|healing\s+crystal\s+aquamarine|mineral\s+specimen|geode\s+crystal|"
    # Kitchen & cookware
    r"cutting\s+board|coffee\s+mug|water\s+bottle|wine\s+glass|spatula|cutlery\s+set|"
    # Pet accessories (non-human)
    r"dog\s+collar|cat\s+harness|dog\s+leash|pet\s+carrier|dog\s+harness|"
    # Medical & chemicals
    r"disposable\s+blue\s+-\s*50\s+tablets|sanitizer"
    r")\b",
    re.IGNORECASE
)

def is_non_fashion(title: str, category: str = "", description: str = "") -> tuple[bool, str]:
    full_text = f"{title} {category} {description}".lower()
    
    # Check overrides first
    if FASHION_OVERRIDE_PATTERN.search(title):
        # Even if "pipe wrench" appears in "Rembrandt Pipe Wrench Charm", "charm" overrides!
        # Even if "coffee mug" appears in "Coffee Mug Enamel Pin", "enamel pin" overrides!
        return False, ""
    
    m = STRONG_NON_FASHION.search(full_text)
    if m:
        return True, f"non_fashion: {m.group(0)}"
    
    return False, ""

conn = sqlite3.connect('data/catalog.db')
cursor = conn.cursor()
cursor.execute('SELECT parent_asin, title, price, slot, store, description FROM products')
rows = cursor.fetchall()

non_fashion_list = []
for r in rows:
    asin, title, price, slot, store, desc = r
    flagged, reason = is_non_fashion(title, description=desc or "")
    if flagged:
        non_fashion_list.append((asin, title, slot, reason))

print(f"Total non-fashion flagged: {len(non_fashion_list)}")
print("\nSample verified non-fashion:")
for item in non_fashion_list[:15]:
    print(f"  [{item[2]}] {item[0]}: {item[1][:75]} ({item[3]})")
