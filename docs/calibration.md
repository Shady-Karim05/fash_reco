# Threshold Calibration and Distribution Analysis

## Executive Summary
This document presents the empirical calibration of similarity thresholds comparing **52 relevant fashion queries** (including vague occasions, multilingual paired normalizations, and product-specific intents) against **52 irrelevant queries** (including near-domain traps such as tools, pets, cooking, and electronics).

## Quantitative Distribution Table

| Group | N | Min Similarity | 5th Percentile | Median | Max Similarity |
|---|---|---|---|---|---|
| **Relevant Queries** | 52 | 0.5976 | 0.6191 | 0.7153 | 0.8619 |
| **Irrelevant Queries** | 52 | 0.1889 | 0.2427 | 0.4498 | 0.6654 |

## Separability Statement
**Are the groups separable by cosine similarity alone?**
**NO**. The groups are **NOT cleanly separable** using a single scalar threshold because the minimum relevant similarity (0.5976) is less than or equal to the maximum irrelevant similarity (0.6654).

Embeddings for vague occasion queries (e.g. "gift for my mom" or "what to wear to a wedding") and near-domain traps overlap significantly in dense embedding space (e.g., semantic proximity of generic descriptive words). Therefore, a hard similarity cutoff (`MIN_SIMILARITY`) is **NOT recommended** as it would either drop valid vague fashion queries or admit non-fashion queries.

## Dual Mechanism Implementation (A2)
Instead of a single brittle threshold, the system implements two complementary mechanisms:
1. **Semantic Intent Classification (`is_fashion_query: bool`)**:
   - The LLM parser determines whether the query is clearly related to fashion, clothing, shoes, accessories, or wearable gifts.
   - If `is_fashion_query == false`, retrieval is bypassed entirely, returning HTTP 200 with `results=[]`, `message="not_a_fashion_query"`, and configured suggested queries.
2. **Informational Confidence Flag (`meta.low_confidence: bool`)**:
   - Set to `true` when the highest cosine similarity among returned products is below `LOW_CONFIDENCE_SIMILARITY = 0.6191` (calibrated to the 5th percentile of the relevant query distribution).
   - Results are still returned to the user without dropping valid matches; the flag provides downstream clients with transparent confidence telemetry.

## Irrelevant Leakage at 5th Percentile Threshold
- Configured `LOW_CONFIDENCE_SIMILARITY`: **0.6191**
- Number of irrelevant queries scoring $\ge 0.6191$: **2 / 52 (3.8%)**
- Without the `is_fashion_query` LLM guardrail, 3.8% of irrelevant queries would pass unflagged by similarity thresholding alone, underscoring the critical necessity of query-level intent classification.

## Overlap Samples
Total overlapping pairs observed: **20**.
Sample overlapping instances where an irrelevant query scored $\ge$ a relevant query:

| Relevant Query | Rel Sim | Irrelevant Query | Irrel Sim |
|---|---|---|---|
| `outfit for a job interview` | 0.6254 | `best recipe for homemade chocolate ` | 0.6654 |
| `outfit for a job interview` | 0.6254 | `how to groom a long haired cat with` | 0.6343 |
| `clothes for a tropical cruise vacat` | 0.6334 | `best recipe for homemade chocolate ` | 0.6654 |
| `clothes for a tropical cruise vacat` | 0.6334 | `how to groom a long haired cat with` | 0.6343 |
| `first day of middle school outfit` | 0.6074 | `how to play acoustic guitar chords ` | 0.6130 |
| `first day of middle school outfit` | 0.6074 | `best recipe for homemade chocolate ` | 0.6654 |
| `first day of middle school outfit` | 0.6074 | `how to groom a long haired cat with` | 0.6343 |
| `first day of middle school outfit` | 0.6074 | `how to build a backyard chicken coo` | 0.6138 |
| `men's quick dry board shorts swim t` | 0.6459 | `best recipe for homemade chocolate ` | 0.6654 |
| `girls pink princess party birthday ` | 0.6264 | `best recipe for homemade chocolate ` | 0.6654 |
| `girls pink princess party birthday ` | 0.6264 | `how to groom a long haired cat with` | 0.6343 |
| `seamless wireless plunge bra` | 0.5976 | `how to play acoustic guitar chords ` | 0.6130 |
| `seamless wireless plunge bra` | 0.5976 | `best recipe for homemade chocolate ` | 0.6654 |
| `seamless wireless plunge bra` | 0.5976 | `how to groom a long haired cat with` | 0.6343 |
| `seamless wireless plunge bra` | 0.5976 | `how to build a backyard chicken coo` | 0.6138 |
