# Evaluation Strategy & Search Quality Report

This document outlines the evaluation strategy, offline benchmarks, and observed query retrieval characteristics for the Semantic Fashion Recommendation Microservice.

---

## 1. Metrics & Scoring Semantics

### Score vs. Similarity
- **`score` (Fused Rank Score):** Reciprocal Rank Fusion (RRF, $k=60$) score aggregating positional rankings across dense vector search and sparse BM25 keyword search. Rank scores are query-dependent and **cannot be compared across queries**.
- **`similarity` (Cosine Similarity):** True vector dot product between L2-normalized dense embeddings of the user query and the catalog item ($[-1.0, 1.0]$). This metric is comparable across queries and forms the basis for guardrail calibration.

---

## 2. Ingestion & Catalog Distribution Limitations

From `data/ingestion_report.json` ($N=8,000$ active catalog items):
- **Accessory Dominance:** Accessories and jewelry represent **51.55%** (4,124 items) of the catalog.
- **Scarcity of Bottoms & Footwear:** Bottoms account for only **4.15%** (332 items) and footwear accounts for **3.44%** (275 items).
- **Price Bias:** 93.30% of raw metadata rows were dropped due to missing/null prices, concentrating the catalog in items with explicit price listings.
- **Review Snippets:** Review ingestion is implemented and tested, but the reviews file was not used in the current build; results do not include review snippets.

---

## 3. Observed Retrieval Behavior Across Query Categories

*(Note: Multilingual retrieval quality is unmeasured and cannot be claimed as verified from single spot checks. Below is the factual observed behavior and status across parsing modes).*

### Observed Behavior & Failure Analysis Table

| Query & Scenario | Mode | Phase 3 Observed Behavior | Root Cause | Status After Part A / Phase 4 |
|---|---|---|---|---|
| **Tamil (`கோடைக்கால கடற்கரை உடை`)** | Forced Fallback (no LLM) | Low similarity (0.5695), semantic drift toward nautical costume items | Cross-lingual embedding drift without query translation; BM25 vocabulary mismatch | **Mitigated**: A1 computes MAX similarity over variants; in FakeLLM/RealLLM mode scores 0.7265+. In fallback mode, remains unnormalized as expected. |
| **Hindi (`गर्मियों के लिए समुद्र तट के कपड़े`)** | Forced Fallback (no LLM) | Moderate similarity (0.6402), returns summer items | Vector alignment captures general beach/summer semantics | **Preserved**: Works via multilingual embeddings; LLM normalization adds slot & season context. |
| **French (`tenue de plage pour l'été`)** | Forced Fallback (no LLM) | French function words ("de", "pour", "l'été") polluted BM25 term matches | BM25 indexed English tokens only; foreign stop words matched sporadic English substrings | **Fixed (A3)**: BM25 Noise Guard drops stopwords and skips BM25 when $<50\%$ tokens in catalog vocabulary (`keyword_search_skipped` warning). |
| **Demographic (`something for my 5 year old boy`)** | Forced Fallback (no LLM) | Matched `boy` -> `men` + `adult` in Phase 2, failing to identify kids | Fallback regex lacked "year old" age pattern and boy/girl demographic mappings | **Fixed (A4)**: Regex captures `\d+\s*year\s+old` and maps to `age_group = "kids"` and `gender = "men"`. |
| **Non-Fashion Trap (`how to play acoustic guitar chords`)** | Forced Fallback & Real LLM | High-scoring false matches on generic items without clothing intent | Pure similarity retrieval has no domain boundary filter | **Fixed (A2)**: `is_fashion_query: bool` in parser. When false, retrieval is skipped entirely (HTTP 200 `not_a_fashion_query`). |

### Currency Handling
- Queries specifying non-USD currencies (e.g. `cotton t-shirt under 500 rupees`) correctly bypass price filtering and emit the warning `price_currency_not_supported`.
