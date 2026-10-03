# System Limitations and Failure Modes

This document catalogs observed failure modes, edge cases, and known architectural boundaries identified during evaluation of the Semantic Fashion Search microservice. Every failure case noted here is derived directly from empirical evaluation outputs, log traces, and audit samples.

---

## 1. Catalog Noise and Unknown-Slot Items
In the active catalog of 24,000 products extracted from the Amazon Fashion dataset, approximately 18.2% of items are classified into the `unknown` slot by the deterministic rule hierarchy. Sampling and auditing the unknown slot revealed several non-apparel and peripheral items:
- **Novelty and Party Items**: Keychains, vinyl decals, car stickers, novelty wall decor, and holiday gift bags.
- **Craft and Sewing Supplies**: Loose zipper pulls, replacement buttons, ribbon spools, and patch kits.
- **Protective and Hardware Accessories**: CPR mask keychains, industrial eye shields, and hardware tool holsters categorized under "Clothing, Shoes & Jewelry".
- **Impact**: When queries have permissive or empty slot constraints, these non-garment products can occasionally appear in keyword or semantic neighbor lists.

---

## 2. Age and Gender Classification False Positives
The deterministic keyword extraction logic in `app/attributes.py` operates on titles and category trees. Specific edge-case false positives observed during evaluations:
- **CPR Training Mask**: Matched the `kids` age group rule due to product descriptions containing "infant/child CPR training pocket mask", despite being emergency training gear rather than children's apparel.
- **"Sweet 16" Birthday Sash**: Classified as `kids` because the token "16" or "teen/sweet 16" triggered youth patterns, although 16-year-old apparel typically maps to adult sizing.
- **Shoe Charms / Clog Pins**: Often tagged with `kids` or `unisex` due to cartoon themes, even when sold as adult fashion accessories.
- **Root Cause**: Reliance on superficial token presence without contextual syntactic dependency parsing.

---

## 3. Outfit Composition Edge Cases
While hard attribute filtering now guarantees 100% age, gender, and price budget coherence among combined outfit slots, semantic style consistency across slots remains an open challenge:
- **LED Rainbow Light-Up Coat for Winter Wedding**: In early outfit benchmark runs for "winter wedding guest outfit", a high-scoring top candidate was an LED flashing rainbow faux fur festival jacket because it matched winter coat embeddings and fit the price budget, despite being stylistically incompatible with formal wedding attire.
- **Infant vs. Child Discrepancies**: Prior to enforcing combo-level age coherence from item attributes, a query for "5-year-old boy outfit" could match infant booties alongside toddler tops because both fell under the broad `kids` partition.
- **Formal vs. Casual Style Clashes**: A query for "casual weekend brunch" occasionally paired casual distressed denim bottoms with satin evening formal footwear when footwear candidates lacked explicit casual style tags.
- **Mitigation**: Combos now strictly enforce combo-level attribute equality (`gender` and `age_group` must match across all slots) and apply minimum item price thresholds (`OUTFIT_MIN_ITEM_PRICE = 2.00`) to eliminate sub-dollar toy accessories and replacement laces ($0.50 boots/laces).

---

## 4. Multilingual Fallback and Non-English Queries
When the LLM parser is unavailable (due to rate limiting, circuit breaker trip, or simulated fallback), non-English queries enter rule-based degraded mode:
- **Tamil and Indic Script Failure**: Rule-based fallback operates primarily on English keyword heuristics. For Tamil queries (e.g. `கடற்கரை விடுமுறைக்காக 50 டாலருக்குள் கோடைக்கால உடை`), fallback produces 0 structured slot/gender/price filters. BM25 keyword matching returns 0 hits against an English-vocabulary catalog, leaving retrieval entirely dependent on multilingual sentence embeddings.
- **Zero-Relevant Fallback Queries**: Evaluation identified 8 non-English fallback queries yielding 0 relevant results under strict regex-proxy evaluation.
- **Degraded-Mode Signaling (D4)**: The service explicitly marks these responses with `low_confidence = True` and appends warning `filters_not_applied_without_llm` (or refuses the query if `NON_ENGLISH_FALLBACK_POLICY = "refuse"`).

---

## 5. Oracle Multilingual Overlap Clarification
- **100% Multilingual Overlap by Construction**: In benchmark reports, oracle-mode multilingual overlap is reported as 100%. This is **by construction**: the evaluation harness injects identical hand-written English reference queries (`normalized_query_en`) for all translated variants. It reflects the theoretical upper bound of the retrieval pipeline when an ideal parser is present, **not** an automated translation capability of the microservice itself.

---

## 6. Regex Relevance Proxy Limitations
- **Coarse Proxy vs. Human Judgment**: Precision@k and recall metrics in automated evaluations rely on query-specific regular expressions (`relevance_regex`). These regex patterns are necessary proxies for automated gating but exhibit known limitations:
  - Example: For query `"men's running shoes below $80"`, an initial regex `(?i)\b(run|running|sneaker|shoes?|trainer|trail)\b` matched `"ESDY Steel Toe Boots ... Work Shoes"`, falsely crediting industrial safety footwear as relevant. Tightening the regex excluded heavy boots and required athletic footwear keywords.
- **Coverage**: Automated regex checks do not evaluate fabric hand-feel, aesthetic appeal, or nuance of style fit.

---

## 7. Evaluation Sample Sizes and Statistical Power
- **Search Benchmark**: 48 product-mode queries (including multilingual variants across English, Spanish, French, Hindi, and Tamil) and 11 outfit-mode queries.
- **Audit Sample**: 100 catalog products stratified across slots, genders, and age groups.
- **Implication**: While these sample sizes provide immediate, deterministic regression gating, they do not constitute statistically exhaustive coverage across all long-tail fashion categories.
