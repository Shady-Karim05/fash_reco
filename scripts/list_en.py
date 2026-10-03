import json

with open("evals/queries.json", encoding="utf-8") as f:
    queries = json.load(f)

for q in queries:
    if q.get("language") == "en":
        print(f"{q['id']}: '{q['query']}' -> constraints={q.get('constraints')}")
