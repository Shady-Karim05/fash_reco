# System Design

## 1. Problem and requirements

**Functional**
1. Accept a natural-language query in any language and return relevant products.
2. Support an outfit mode that returns a complete, coherent set of items.
3. Honor hard constraints (price, gender, age group) with no violations.
4. Accept new and updated products at runtime without a restart.

**Non-functional**
- Availability: `/search` must not fail because the LLM is slow or down.
- Latency: target p95 under 500 ms on a cache miss for a 10k-product catalog (to be verified by evals, not assumed).
- Explainability: each result carries a short reason and the parsed filters used.
- Observability: latency, fallback rate, zero-result rate, and cache hit rate are exposed.

**Out of scope for the prototype:** personalization, image search, payments, user accounts.

## 2. Search request flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant K as Cache
    participant P as Parser (LLM)
    participant R as Retrieval
    participant F as Filters
    participant O as Outfit composer

    C->>A: POST /search {query, mode, top_k}
    A->>A: Validate (length, top_k limits)
    A->>P: parse(query)
    alt LLM ok
        P-->>A: ParsedQuery
    else timeout / bad JSON (after one retry)
        P-->>A: Fallback ParsedQuery (no filters), used_fallback=true
    end
    A->>K: lookup(normalized_query, filters, mode, index_version)
    alt hit
        K-->>A: cached response
    else miss
        A->>R: vector top-50 + BM25 top-50
        R-->>A: fused candidates (RRF)
        A->>F: apply hard filters, exclude soft-deleted
        F-->>A: filtered candidates + excluded count
        A->>A: quality boost, confidence threshold
        opt mode == outfit
            A->>O: compose per slot
            O-->>A: outfit items
        end
        A->>K: store
    end
    A-->>C: results + meta
```

- Filters run before truncating to `top_k` so results do not run short.

### 2.1 Result Pipeline Order (Deterministic Processing)

Every search request passes through the following strict execution sequence:
1. **Query Parsing & Cache:** Check QueryCache for exact `(normalized_query_en, filters, mode, index_version)`. If missed, parse query via LLM or deterministic fallback.
2. **Dense & Sparse Retrieval:** Retrieve top-50 dense FAISS candidates and top-50 BM25 sparse candidates.
3. **RRF Rank Fusion:** Combine positions via Reciprocal Rank Fusion ($k=60$). Max score normalized to $[0, 1]$.
4. **Strict Hard Filtering:** Apply `passes_strict_filters` (slot match, gender compatibility, age group, price ceiling/floor). Exclude soft-deleted rows. Increment `excluded_by_filters`.
5. **Innerwear Policy:** Exclude `innerwear` items unless the user query explicitly targets innerwear keywords.
6. **Near-Duplicate Collapse:** Collapse near-identical variants sharing brand and the first 5 significant title tokens. Retain the highest-ranked variant; preserve distinct pack sizes. Increment `duplicates_collapsed`.
7. **Soft Ranking Boosts:** Add soft domain boosts: season (+0.03), occasion (+0.03), color (+0.02), brand (+0.05), and Bayesian quality score ($w_q = 0.05 \times \text{normalized quality}$).
8. **Truncation & Guardrails:** Truncate to requested `top_k`. If the top result similarity is below `LOW_CONFIDENCE_SIMILARITY`, flag `low_confidence = true`.
9. **Explanations:** Generate deterministic fact-based explanation strings for each result.
10. **Cache Storage:** Store full response in QueryCache.

### 2.2 Outfit Composition & Budget Semantics

1. **Templates Evaluated:**
   - `full_body + footwear + accessory`
   - `top + bottom + footwear + accessory`
2. **Coherence Enforced:**
   - Age coherence: All items must match the query target `age_group` (default `adult`).
   - Gender coherence: All items must be compatible with the target gender (`men` + `unisex` or `women` + `unisex`).
   - Accessory restrictions: Exclude phone cases, vehicle keychains, and toys.
   - Innerwear exclusion: Innerwear is never included in an outfit.
3. **Budget Compliance:**
   - Sum of item prices in the outfit must be $\le \text{max\_budget}$.
   - If no valid multi-item combination ($\ge 2$ items) can be composed within budget, the service returns `outfit = null`, `message = "no_outfit_within_budget"`.
   - The service will never return an outfit exceeding the user's budget.
4. **Slot Fallback Sequence:** If a slot pool is empty, slots drop in order `accessory -> footwear`. If fewer than 2 items remain, composition fails with `insufficient_items_for_outfit` (or `no_outfit_within_budget` if budget caused the failure).

## 3. Ingestion flow

```mermaid
sequenceDiagram
    participant S as Source (batch script or API caller)
    participant V as Validator
    participant T as Cleaning + attributes
    participant E as Embedder
    participant D as SQLite
    participant I as FAISS + BM25

    S->>V: raw records
    V-->>S: per-record rejections (missing title, null price)
    V->>T: valid records
    T->>T: clean text, derive gender, age group, slot, colour, season
    T->>E: search_text batch
    E-->>T: vectors
    T->>D: BEGIN; upsert rows, version += 1
    T->>I: add / replace vectors and BM25 docs
    alt all steps succeed
        D-->>T: COMMIT
        T->>T: index_version += 1 (invalidates cache)
    else any step fails
        D-->>T: ROLLBACK
        T-->>S: error with reason
    end
```

The batch script and `POST /products` call the same pipeline, so the two paths cannot drift apart.

## 4. Data model

```mermaid
erDiagram
    PRODUCT {
        text parent_asin PK
        text title
        text brand
        real price
        text gender
        text age_group
        text slot
        text colors
        text seasons
        text occasions
        text search_text
        text image_url
        real average_rating
        int rating_number
        real quality_score
        int version
        bool is_deleted
        text created_at
        text updated_at
    }
    REVIEW_SNIPPET {
        int id PK
        text parent_asin FK
        text text
        int helpful_vote
    }
    INGESTION_LOG {
        int id PK
        text run_id
        text parent_asin
        text outcome
        text reason
        text created_at
    }
    PRODUCT ||--o{ REVIEW_SNIPPET : has
    PRODUCT ||--o{ INGESTION_LOG : recorded_in
```

## 5. Degradation behavior

```mermaid
stateDiagram-v2
    [*] --> Normal
    Normal --> NoLLM: LLM timeout or invalid output
    NoLLM --> Normal: next request succeeds
    Normal --> NoMatch: best score below threshold
    NoMatch --> Normal: new query
    Normal --> EmptyAfterFilters: all candidates filtered out
    EmptyAfterFilters --> Normal: new query
```

| Condition | Behavior |
|---|---|
| LLM timeout, error, or invalid JSON | Retry once, then search with the raw query and no filters. `used_fallback = true`. |
| Query is clearly non-fashion (`is_fashion_query = false`) | Skip retrieval entirely, return HTTP 200 with `results=[]`, `message: "not_a_fashion_query"`, and suggested queries. |
| Best result below `LOW_CONFIDENCE_SIMILARITY` | Return ranked results normally with informational `meta.low_confidence = true`. |
| BM25 query has $<50\%$ catalog vocabulary overlap | Skip BM25 keyword component to prevent foreign stopword noise; set warning `keyword_search_skipped`. |
| Filters remove every candidate | Return an empty list and report `excluded_by_filters` so the cause is visible. |
| Outfit slot has no good item | Omit the slot. Never pad with an irrelevant item. (Innerwear slot is excluded from outfits). |
| Index write fails during ingestion | Roll back SQLite, restore previous FAISS and BM25 memory state for affected IDs, return error. |
| Process restarts | Rebuild FAISS and BM25 from SQLite or validated disk cache on startup. |

## 6. Key design decisions and trade-offs

### 6.1 Hard filters versus soft ranking
Price, gender, and age group are filters because a wrong value is a visible failure (a $45 item under a $30 budget, a girls' dress for a women's query). Season, occasion, and colour are boosts because the data for them is inferred and imperfect.

### 6.2 Unpriced products
In the full dataset of 826,108 rows, 774,720 products (93.78%) had no price. A strict price filter cannot make a promise about a product with unknown price. Default: index only priced products and report how many were dropped (50,152 valid items kept, 6.07%). A config flag allows including them, at the cost of the guarantee. This is a deliberate trade of catalog coverage for correctness.

Future work alternative: index all titled products and apply the price constraint only when the query contains one; unpriced items are excluded in that case.

### 6.3 Derived attributes at ingestion
Categories are empty in the sample, so slot cannot come from them. Deriving slot, gender, colour, and season once at ingestion keeps the query path fast and deterministic and makes the rules unit-testable. Rules run first; an LLM tagger is an optional improvement for products left `unknown`.

### 6.4 Description beats title for some products
A title such as "Mento Streamtail" says nothing about the product. Its description mentions a thong sandal for the beach. Search text therefore combines the title, brand, derived type, features, a trimmed description, and review snippets.

### 6.5 Kids versus adults
Kids' items share the catalog with adult items. Without an `age_group` filter, an adult query can return a children's dress. Default is adult unless the query indicates otherwise.

### 6.6 Rating handling
Raw average ratings overrate products with few reviews. A Bayesian average pulls low-count items toward the global mean. It is used only as a small ranking boost, never as a filter.

### 6.7 Outfit templates
An outfit is `full_body + footwear + accessory` or `top + bottom + footwear + accessory`. Both are built; the higher-scoring one is returned. This avoids pairing a dress with trousers.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Slot rules misclassify (for example "dress shirt") | Ordered rules with explicit exceptions and unit tests |
| LLM extracts wrong constraints | Pydantic validation; filters are echoed in `meta.parsed_filters` for inspection; eval measures parser accuracy |
| Embeddings weak for a language | Per-language consistency eval; fall back to BM25 on the English-normalized query |
| Index and database diverge | SQLite is the source of truth; rebuild on start; ingestion is transactional |
| Evaluation relies on a keyword proxy | Documented limitation plus a manual spot-check |
