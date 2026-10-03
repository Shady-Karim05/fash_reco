import json

with open("evals/parser_cases.json", encoding="utf-8") as f:
    cases = json.load(f)

a10_queries = [
    "gift for my mom",
    "what to wear to a wedding",
    "something comfortable for a long flight",
    "outfit for a job interview",
    "Hanes cotton crew t-shirt",
    "Under Armour workout tank",
    "Nike running shorts under $40",
    "Levi's jeans for men",
]

case_map = {c["query"]: c for c in cases}
for q in a10_queries:
    if q in case_map:
        print(f"FOUND: {q} -> {case_map[q]}")
    else:
        print(f"MISSING: {q}")
