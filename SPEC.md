# Project spec v2: Semantic Fashion Recommendation Microservice (Amazon Fashion data)

Paste this file into Antigravity as the task brief, or save it as `SPEC.md` in the repo root. Work phase by phase. After each phase, run `ruff`, `mypy`, and `pytest`, summarize the changes, and stop for review.

---

## 1. Goal

Build a production-style microservice that accepts natural-language, multilingual shopping queries (for example "I need an outfit for the beach this summer") and returns relevant fashion products or a complete outfit. The catalog must be updatable at runtime without a restart.

Rubric to optimize for: problem understanding (15), solution depth and production-scale thinking (25), design decisions (20), code quality (25), evals and monitoring (15).

## 2. Tech stack (fixed, do not substitute)

- Python 3.11, FastAPI + Uvicorn, Pydantic v2
- sentence-transformers, model `paraphrase-multilingual-MiniLM-L12-v2`
- `faiss-cpu` for vectors, `rank_bm25` for keywords
- SQLite for the catalog (source of truth)
- LLM behind an interface; key from env var `LLM_API_KEY`
- pytest, ruff, mypy, pre-commit, Docker

## 3. Dataset: Amazon Reviews 2023, Amazon Fashion (McAuley Lab)

Two files, joined on `parent_asin` (NOT `asin`; variants share a parent).

**Metadata fields used:** `parent_asin`, `title`, `features` (list), `description` (list), `price` (float or null), `store` (brand), `average_rating`, `rating_number`, `details` (dict), `images` (use only the MAIN `large` URL for display).
**Ignored:** `main_category` (constant "AMAZON FASHION"), `videos`, `bought_together`, all other image URLs.
**Reviews fields used:** `parent_asin`, `text`, `rating`, `helpful_vote`.

### 3.1 Observed data quality (design for these, add tests for each)

- `categories` is usually an empty list. Never depend on it.
- `price` is null for a majority of rows.
- `description` and `features` are often empty. The title may be uninformative (for example "Mento Streamtail").
- Descriptions contain symbols like `✔` and `➤` and run-together sentences.
- Gender appears in `details["Department"]` (for example "womens") or in the title ("Men's", "Women's", "Girls'").
- Kids' items are mixed in ("Girls' ... 9-10 Years").
- Title includes size and colour in parentheses, for example "(Flower Mix Blue, XL)".
- `rating_number` ranges from 1 to thousands; raw `average_rating` is unreliable for low counts.
- No season or occasion field exists.

### 3.2 Sampling and ingestion rules (`scripts/build_index.py`)

1. Stream the metadata file. Do not load it all into memory.
2. Keep a product only if: `title` has at least 15 characters AND `price` is not null AND `price` > 0. Count and print every dropped row by reason (`no_title`, `no_price`). These counts go in the README.
3. Take a random sample of 10,000 kept products with `seed=42`. Hold out a random 20% (2,000) for `simulate_updates.py`.
4. Stream the reviews file and keep only reviews whose `parent_asin` is in the sample. Per product keep the 2 best reviews by `helpful_vote`, requiring `len(text) >= 40`; truncate each to 150 chars.
5. Never commit raw data. Add `data/README.md` with download instructions and expected filenames.
6. If the data files are missing, `scripts/generate_synthetic.py` creates ~500 synthetic products with the same schema so the project still runs.

Configurable policy: `INCLUDE_UNKNOWN_PRICE` (default `false`). When `false`, unpriced products are not indexed. This preserves the guarantee that a price-constrained result never exceeds the budget.

### 3.3 Derived attributes (`app/attributes.py`)

Compute at ingestion, store in SQLite. Rules first; optional LLM tagging only for fields left `unknown`.

| Attribute | Values | Rule |
|---|---|---|
| `gender` | men, women, unisex, unknown | `details["Department"]` first (map "mens", "womens", "boys", "girls", "unisex"), then title regex (`men's`, `women's`, `girls'`, `boys'`) |
| `age_group` | adult, kids | kids if title matches `girls?'?s?\b|boys?'?s?\b|kids?|toddler|baby|infant|\d+\s*-\s*\d+\s*years?`; else adult |
| `slot` | top, bottom, full_body, footwear, accessory, unknown | Keyword rules below, checked against title first, then features, then description |
| `colors` | list[str] | Extract from the parenthesized part of the title and the title text using a fixed colour vocabulary |
| `seasons` | list of summer, winter, spring, fall | Keyword rules (`summer|beach|swim|sandal|tank|shorts|lightweight`, `winter|fleece|thermal|wool|insulated|parka`); empty if none match |
| `occasions` | list of beach, formal, casual, workout, party, travel | Keyword rules (`beach|swim|thong|flip flop`, `compression|athletic|running|workout|yoga`, `dress shirt|blazer|formal`, etc.) |
| `quality_score` | float | Bayesian average rating (see 5.3) |

Slot keyword rules (case-insensitive, ordered; first match wins):
- `footwear`: sandal, shoe, sneaker, boot, slipper, flip flop, loafer, clog, heel, flats, thong sandal
- `full_body`: dress (but NOT "dress shirt", "dress pants", "dress shoes", "dress socks"), jumpsuit, romper, swimsuit, one-piece, overall
- `bottom`: pants, shorts, jeans, skirt, leggings, trousers, capri, joggers, swim trunks
- `top`: shirt, t-shirt, tee, top, blouse, tank, sweater, hoodie, jacket, coat, cardigan, polo
- `accessory`: socks, sleeves, hat, cap, sunglasses, belt, scarf, bag, earrings, necklace, locket, watch, gloves
- else `unknown`: still searchable in products mode, excluded from outfit mode

Required tests: "Mento Streamtail" with its description resolves to `footwear`; "Palazzo Lounge Wide Leg Pants" resolves to `bottom`; "Trapeze Dress ... 9-10 Years" resolves to `full_body` and `kids`; "Dress Shirt" resolves to `top`, not `full_body`.

### 3.4 Embedding text

Build one `search_text` per product:
`{title without size tokens}. Brand: {store}. For: {gender}, {age_group}. Type: {slot}. {features[:3] joined}. {cleaned description[:400]}. Reviews: {review snippets}.`

Cleaning: remove symbols such as `✔ ➤ ★`, collapse whitespace, split run-together sentences at lowercase-to-uppercase boundaries, strip size tokens ("Size 9-12", "XL", "Large") from the title copy used for embedding. Keep the original title for display.

## 4. Folder structure

```
fashion-search/
├── app/
│   ├── main.py          # app factory, routes, lifespan
│   ├── config.py        # pydantic-settings, all config from env
│   ├── schemas.py       # request/response/domain models
│   ├── attributes.py    # gender, age_group, slot, colour, season rules
│   ├── cleaning.py      # text cleaning, search_text builder
│   ├── parser.py        # LLM query parser + fallback
│   ├── embedder.py      # model wrapper, batching
│   ├── index.py         # FAISS + BM25 + RRF fusion
│   ├── filters.py       # hard constraints
│   ├── outfit.py        # slot-based composition
│   ├── catalog.py       # SQLite repository, versioning, soft delete
│   ├── cache.py         # LRU query cache
│   ├── metrics.py       # counters and latency histograms
│   └── llm/
│       ├── base.py      # LLMClient protocol
│       ├── gemini.py    # concrete client (swap if using another provider)
│       └── fake.py      # deterministic client for tests
├── scripts/             # build_index.py, simulate_updates.py, generate_synthetic.py
├── evals/
├── tests/
├── docs/
├── Dockerfile
├── pyproject.toml
└── README.md
```

## 5. Features

### 5.1 Endpoints

| Method and path | Purpose |
|---|---|
| `POST /search` | Query in, ranked products or outfit out |
| `POST /products` | Add or update products (raw metadata format); clean, derive attributes, embed, upsert |
| `DELETE /products/{id}` | Soft delete |
| `GET /health` | Liveness and readiness (index loaded, catalog reachable, LLM reachable or degraded) |
| `GET /metrics` | Request count, p50/p95 latency, fallback rate, zero-result rate, cache hit rate, index size, dropped-at-ingestion counts |

`POST /search` request: `{ "query": str, "top_k": int = 10, "mode": "products" | "outfit" }`.
Response: results with `product_id`, `title`, `price`, `brand`, `image_url`, `slot`, `score`, `reason`, plus `meta`: `parsed_filters`, `used_fallback`, `latency_ms`, `index_version`, `excluded_by_filters`.

### 5.2 Query parser

- Output: Pydantic `ParsedQuery` with `is_fashion_query`, `occasion`, `season`, `gender`, `age_group`, `max_price`, `min_price`, `colors`, `slots`, `language`, `normalized_query_en`, `warnings`.
- `slots` allowed values: `"top"`, `"bottom"`, `"full_body"`, `"footwear"`, `"accessory"`, `"innerwear"`.
- `is_fashion_query`: boolean (default true); set false only for queries clearly unrelated to clothing, footwear, accessories, jewelry, or wearable gifts.
- Strict JSON-only prompt. Validate with Pydantic. On any failure (timeout, invalid JSON, schema error): retry once, then fall back to `ParsedQuery(normalized_query_en=raw_query)` with no filters and `used_fallback = true`. Fallback parser always sets `is_fashion_query = true`.
- Default `age_group` to `adult` unless the query mentions kids, child, boy, girl, baby, or similar.
- Timeout 3 seconds, configurable. LLM sits behind `LLMClient` so tests use `FakeLLMClient`.

### 5.3 Hybrid retrieval and ranking

- Embed `normalized_query_en` and the raw query. Take top 50 from FAISS (inner product on normalized vectors) and top 50 from BM25. Merge with Reciprocal Rank Fusion, `k = 60`.
- Both indexes support incremental add, with an id map from index position to `parent_asin`.
- Similarity computation: Maximum cosine similarity over all embedded query variants (raw query and normalized_query_en).
- BM25 Noise Guard: tokens shorter than 3 characters and multilingual stopwords are filtered out. BM25 is skipped if less than 50% of remaining query tokens exist in catalog vocabulary.
- Final score = RRF score plus a small quality boost: `0.05 * normalized(quality_score)`.
- Bayesian average: `(v / (v + m)) * R + (m / (v + m)) * C`, with `v = rating_number`, `R = average_rating`, `m = 10`, `C = global mean rating`. A 2.0 rating from 1 reviewer must not outrank a 4.3 from thousands.

### 5.4 Hard filters

- Strict: `max_price`, `min_price`, `gender` (a "men" query never returns `women`; `unisex` is allowed for both), `age_group`, and explicit `slots`.
- Soft boosts: season, occasion, colour.
- Soft-deleted products always excluded.
- Filter before truncating to `top_k`. Report how many candidates were removed in `meta.excluded_by_filters`.

### 5.5 Outfit composition (mode = "outfit")

- An outfit is either `full_body + footwear + accessory` or `top + bottom + footwear + accessory`. Build both candidates and return the one with the higher average score.
- Retrieve per slot with the same query and filters. Return one best item per slot with a short `reason`.
- Outfit mode ignores innerwear products.
- Omit a slot with no result above the threshold. Never pad with irrelevant items. Products with `slot = unknown` are never used in outfits.

### 5.6 Guardrails

- Dual-mechanism relevance protection:
  - Intent classification (`is_fashion_query`): If false, retrieval is skipped; returns HTTP 200 with `results=[]`, `message="not_a_fashion_query"`, and suggested queries.
  - Informational low confidence (`meta.low_confidence`): Set true when maximum similarity of returned items is below `LOW_CONFIDENCE_SIMILARITY` (5th percentile calibration). Results are still returned.
  - `MIN_SIMILARITY` defaults to 0.0 (disabled, not recommended due to distributional overlap).
- LRU cache keyed on `(normalized_query, filters, top_k, mode, index_version)`. Bump `index_version` on every catalog write.
- Input limits: query max 500 characters, `top_k` max 50.
- Structured JSON logs with a request id. Never log secrets.

### 5.7 Evolving catalog

- `POST /products` accepts a list of raw metadata records, runs the same cleaning and attribute derivation as the batch script (one shared code path), embeds in batches, and upserts into FAISS, BM25, and SQLite. If any step fails, roll back and return a clear error.
- Rows have `version`, `created_at`, `updated_at`, `is_deleted`. Re-posting the same `parent_asin` increments `version`.
- Records with missing title or null price are rejected with a per-record reason; valid records in the same request still succeed.
- `scripts/simulate_updates.py` posts the held-out 20% and prints how many became searchable.
- On startup, rebuild in-memory indexes from SQLite.

## 6. Coding standards

### 6.1 Style and typing
- PEP 8 via `ruff` (rules E, F, I, B, UP, SIM), line length 100.
- Full type hints; `mypy --strict` passes on `app/`.
- Use `pathlib`, f-strings, Pydantic models or dataclasses. No wildcard imports, no mutable default arguments.
- Google-style docstrings on every public function and class.

### 6.2 Design
- Layers: routes (HTTP only) call services; services call repositories and indexes. No business logic in route handlers.
- Dependency injection via FastAPI `Depends`. No global mutable state beyond objects built in the app lifespan.
- Depend on interfaces (`LLMClient`, `Embedder`, `VectorIndex`) so each can be swapped or faked.
- Functions do one thing and stay under about 40 lines. Ranking, fusion, filtering, and attribute rules are pure functions.
- Every tunable (model name, timeouts, thresholds, `k`, cache size, `INCLUDE_UNKNOWN_PRICE`) lives in `config.py`, read from env with defaults. No magic numbers.
- Batch and ingestion code must share one cleaning and attribute pipeline with the API ingestion path.

### 6.3 Errors and logging
- Custom exceptions (`CatalogError`, `IndexingError`, `ParserError`) mapped to HTTP errors in one handler.
- No bare `except:`. Catch specific exceptions, log with context, then recover or re-raise.
- `/search` degrades gracefully: LLM down means fallback parser; nothing returns a 500 for LLM failure.
- `logging` module with JSON formatting; no `print` in `app/`.

### 6.4 Testing
- pytest, at least 80% coverage on `index`, `filters`, `parser`, `catalog`, `outfit`, `attributes`, `cleaning`.
- Unit tests: RRF fusion math, every filter (including null price, kids vs adult, unisex), every attribute rule listed in 3.3, parser fallback paths, soft delete, versioning, Bayesian average.
- Integration tests: `TestClient` through all endpoints using `FakeLLMClient` and a fixture catalog built from the five real sample rows in `tests/fixtures/sample_meta.jsonl`.
- Regression test: add a product through `POST /products`, then find it through `/search` immediately.
- Tests are deterministic, need no network, and finish within 60 seconds.

### 6.5 Git and repo hygiene
- Small commits with clear messages (for example `feat(attributes): add slot rules`).
- `.gitignore` for data, indexes, `.env`, caches; provide `.env.example`.
- `pre-commit` running ruff and mypy. No secrets in code or history.

## 7. Evals (`evals/`)

`evals/queries.json`: at least 30 queries. Each has `id`, `query`, `language`, `relevance_regex` (case-insensitive pattern matched against title + features + description), and optional constraints (`max_price`, `gender`, `age_group`). Include at least 6 queries in English, Hindi, and Tamil variants (same intent, same regex). Example: "beach outfit for summer" with regex `sandal|swim|bikini|trunks|sun ?hat|cover[- ]?up|tank|shorts`.

Known limitation to state in the README: relevance is judged by a keyword proxy because the dataset has no relevance labels. Add a small manual spot-check of the top 5 for 10 queries and report it separately.

`evals/run_evals.py` prints a table and writes `evals/results.json` with:
- Recall@5 and MRR using the regex proxy
- Constraint-violation rate across price, gender, and age group (target 0%)
- Kids leakage: for queries with no kids intent, share of results with `age_group = kids` (target 0%)
- Multilingual consistency: mean top-5 overlap across language variants
- Fallback test: `FakeLLMClient` forced to fail; success rate must be 100%
- Latency p50 and p95; zero-result rate
- Catalog update test: add a product, confirm it is returned for a matching query
- Ingestion report: rows read, rows dropped by reason, rows indexed

Exit nonzero if the violation rate is above 0% or the fallback success rate is below 100%.

## 8. Phases and acceptance criteria

| Phase | Deliverable | Done when |
|---|---|---|
| 1 | Streaming ingestion, cleaning, attribute rules, SQLite, drop-count report | Required attribute tests pass; ingestion report printed |
| 2 | Embeddings, FAISS + BM25, RRF, `/search` without LLM | 10 manual queries look sensible; unit tests pass |
| 3 | Parser, fallback, hard filters (price, gender, age group) | Zero violations in tests; fallback tests pass |
| 4 | `POST /products`, soft delete, versioning, `simulate_updates.py` | New product searchable immediately; restart rebuilds the same index |
| 5 | Outfit mode, threshold, cache, quality boost, `/metrics` | Outfit returns one item per available slot; cache hit rate in metrics |
| 6 | Evals with exit codes | `run_evals.py` produces the full table |
| 7 | Dockerfile, README, architecture diagram | `docker build` and `docker run` work; README complete |

## 9. README must contain

1. Problem statement and assumptions
2. Architecture diagram (`docs/architecture.png`) and a walkthrough of the search and ingestion paths
3. Data findings: the table of observed quality issues from 3.1 and the ingestion drop counts
4. Design decisions and why: hybrid search; hard filters versus soft boosts; derived attributes at ingestion instead of at query time; priced-only index and the `INCLUDE_UNKNOWN_PRICE` trade-off; Bayesian rating; SQLite as source of truth; fallback parser
5. How to run: install, build index, start server, example `curl` calls, tests, evals
6. Eval results table and failure analysis, including the keyword-proxy limitation
7. Production scale: HNSW or IVF then a managed vector DB (Qdrant) at millions of items; queue and worker for embedding; Redis shared cache and stateless replicas; shard by category; nightly rebuild plus incremental updates; drift, zero-result, and fallback-rate alerts; A/B testing and click logging for learning-to-rank; LLM cost controls (cache, small model, timeouts); per-language evaluation; use of `bought_together` and images as future signals
8. Known limitations and next steps (cross-encoder reranking, image embeddings, personalization, LLM-based attribute tagging at scale)

## 10. Rules for the agent

- Follow the structure and phases exactly. Add no frameworks beyond those listed.
- Do not invent metrics. Every number in the README must come from `evals/results.json` or the ingestion report.
- If something is ambiguous, pick the simpler option and write the assumption in the README.
- Never hardcode keys. Never call a real LLM in tests.
- Use the five sample rows in `tests/fixtures/sample_meta.jsonl` as the baseline fixtures; add rows rather than changing them.
- After each phase: run `ruff`, `mypy`, `pytest`, fix failures, summarize, and wait for review.
