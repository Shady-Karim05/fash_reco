import json
import unicodedata

with open("evals/queries.json", encoding="utf-8") as f:
    data = json.load(f)

with open("scripts/tamil_debug.txt", "w", encoding="utf-8") as out:
    for item in data:
        if item.get("language") == "ta":
            q = item.get("query", "")
            chars = [(c, hex(ord(c)), unicodedata.name(c, 'UNKNOWN')) for c in q]
            out.write(f"{item.get('id')}: {q}\n")
            for c, h, name in chars:
                out.write(f"   {repr(c)} {h} {name}\n")
print("Wrote to scripts/tamil_debug.txt")
