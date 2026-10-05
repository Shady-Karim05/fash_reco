"""Test slot classification improvements on unknown slot products."""

import sqlite3
import re
from app.attributes import derive_slot

conn = sqlite3.connect('data/catalog.db')
cursor = conn.cursor()
cursor.execute('SELECT parent_asin, title, slot FROM products WHERE slot = "unknown"')
unknowns = cursor.fetchall()
print(f"Total unknown products: {len(unknowns)}")

# Additional slot rules for common patterns in fashion catalog
BAG_SATCHEL_PATTERN = re.compile(
    r"\b(?:satchel|crossbody|clutch|tote|backpack|handbag|shoulder\s+bag|wristlet|wallet|coin\s+purse|card\s+holder|duffel|messenger\s+bag)\b",
    re.IGNORECASE
)
FOOTWEAR_PATTERN = re.compile(
    r"\b(?:shoes?|sneakers?|boots?|sandals?|footwear|loafers?|heels?|slippers?|pumps?|flats?|mules?|clogs?|slides?|oxfords?|espadrilles?)\b",
    re.IGNORECASE
)
SOCKS_TIGHTS_PATTERN = re.compile(
    r"\b(?:socks?|no[- ]shows?|booties?|stockings?|tights?|leg\s+warmers?|crew\s+socks?|ankle\s+socks?)\b",
    re.IGNORECASE
)
GI_UNIFORM_PATTERN = re.compile(
    r"\b(?:gi|kimono|rashguard|singlet|swimsuit|bikini|cover[- ]up|costume|romper|jumpsuit|bodysuit|pajamas?|pyjamas?|pjs?)\b",
    re.IGNORECASE
)

recovered = 0
recovered_slots = {}
for asin, title, slot in unknowns:
    new_slot = derive_slot(title)
    if new_slot == "unknown":
        if BAG_SATCHEL_PATTERN.search(title):
            new_slot = "accessory"
        elif FOOTWEAR_PATTERN.search(title):
            new_slot = "footwear"
        elif SOCKS_TIGHTS_PATTERN.search(title):
            new_slot = "accessory"
        elif GI_UNIFORM_PATTERN.search(title):
            new_slot = "full_body"
            
    if new_slot != "unknown":
        recovered += 1
        recovered_slots[new_slot] = recovered_slots.get(new_slot, 0) + 1

print(f"Recoverable from unknown: {recovered} ({recovered/len(unknowns)*100:.1f}%)")
print("Recovered by slot:", recovered_slots)
