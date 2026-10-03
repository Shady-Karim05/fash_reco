# Semantic Fashion Recommendation Microservice

A production-style microservice for semantic and multilingual fashion search on Amazon Fashion data, built with FastAPI, Sentence-Transformers, FAISS, BM25, and SQLite.

## Overview

- **Model:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-d dense embeddings, L2-normalized)
- **Vector Search:** FAISS `IndexFlatIP` (Cosine similarity over normalized vectors)
- **Keyword Search:** BM25Okapi (`rank_bm25`) over cleaned and derived search text
- **Fusion:** Reciprocal Rank Fusion (RRF, $k=60$) combining dense semantic vectors and sparse BM25 scores
- **Storage:** SQLite catalog with ACID transactions, schema versioning, soft deletion, and runtime dynamic indexing
- **API:** FastAPI + Uvicorn with Pydantic v2 schemas, outfit composition mode, Query & Parse caches, and Prometheus observability metrics

---

## Ingestion & Dataset Findings

Dataset: Amazon Reviews 2023 (`Amazon Fashion` category from McAuley Lab).

Ingestion report summary from `data/ingestion_report.json` ($N=24,000$ active catalog products):
- **Total rows streamed:** 826,275
- **Dropped (missing/null/zero price):** 747,562 (90.47%)
- **Dropped (short title < 15 chars):** 44,176 (5.35%)
- **Dropped (non-fashion keyword: plush/toy/phone case/automotive):** 4,537 (0.55%)
- **Dropped (no title):** 0 (0.00%)
- **Valid kept rows:** 30,000 (3.63%)
- **Sampled (Reservoir `seed=42`):** 30,000 (24,000 initial active catalog products, 6,000 held-out update test set)

### Attribute Coverage (Catalog $N=24,000$)

| Attribute | Breakdown |
|---|---|
| **Slot** | accessory: 56.70% (13,609), top: 15.20% (3,649), full_body: 9.68% (2,324), unknown: 7.71% (1,851), bottom: 5.60% (1,343), footwear: 3.28% (787), innerwear: 1.82% (437) |
| **Gender** | women: 36.99% (8,878), unknown: 28.35% (6,804), men: 18.23% (4,375), unisex: 16.43% (3,943) |
| **Age Group** | adult: 92.39% (22,173), kids: 7.61% (1,827) |
| **Data Completeness** | empty description: 64.70% (15,528), empty features: 22.80% (5,472), review snippets: 0 (optional reviews file omitted during build) |

### Key Findings & Limitations
- **Unknown Gender Exclusion:** 28.35% (6,804 items) of catalog products have `gender = "unknown"`. Under strict gender filtering (`gender_include_unknown = False`), all 6,804 items are systematically excluded from queries specifying gender. Setting `GENDER_INCLUDE_UNKNOWN=true` allows unknown items through.
- **Slot Asymmetry:** Accessories and jewelry dominate at 56.70%, while footwear (3.28%) and bottoms (5.60%) are scarce, making separate top/bottom outfit combinations harder to satisfy than full-body dresses/suits.
- **Scoring Semantics:** `score` is an RRF rank fusion score (query-dependent and non-comparable across queries); `similarity` is true cosine dot-product ($[-1.0, 1.0]$).

---

## Evaluation Benchmark Results (48 Queries Across 5 Languages)

From `evals/results_fallback.json` and `evals/results_oracle.json`:

| Metric | Fallback Mode (No LLM) | Oracle Parse (Upper Bound) |
|---|---|---|
| **Precision@5 (Regex Proxy)** | 0.6783 | 0.9957 |
| **Recall@5 (Binary Proxy)** | 0.8261 | 1.0000 |
| **MRR@10** | 0.7681 | 1.0000 |
| **Latency p50** | 99.06 ms | 0.17 ms (cached) |
| **Latency p95** | 169.75 ms | 189.56 ms |
| **Multilingual Top-5 Overlap** | 9.91% | 100.0% |
| **Total Constraint Violations** | 125 | 0 |
| **Kids Leakage (Non-Kids Queries)** | 0 | 0 |
| **Innerwear Leakage** | 0 | 0 |
| **Near-Duplicate Rate (Top 5)** | 0.0% | 0.0% |
| **Outfit Budget Compliance** | 100.0% | 100.0% |
| **Outfit Completeness ($\ge 3$ slots)** | 60.0% | 80.0% |
| **Outfit Age & Gender Coherence** | 80.0% | 100.0% |
| **Forced Fallback Success Rate** | 100.0% | 100.0% |

---

## Quickstart

### 1. Environment Setup
```bash
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

pip install -e ".[dev]"
```

### 2. Ingestion & Index Building
```bash
python scripts/build_index.py
```

### 3. Run the Microservice
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4. Run Evaluation Benchmark
```bash
# Offline benchmark with hand-labeled oracle parses (upper bound)
python evals/run_evals.py --mode oracle

# Offline benchmark with forced deterministic fallback
python evals/run_evals.py --mode fallback
```

---

## API Endpoints

### `GET /health`
Returns service liveness, readiness, active catalog count, index size, and index version.

### `POST /search`
Supports both `mode="product"` and `mode="outfit"`.
```json
{
  "query": "beach outfit for summer under $80",
  "top_k": 5,
  "mode": "outfit"
}
```

### `GET /metrics` and `GET /metrics/prometheus`
Returns operational telemetry: search latency percentiles (p50, p90, p95, p99), query cache hit rates, parse cache hit rates, fallback rates, and active index size.

### `POST /products` & `DELETE /products/{id}` (Admin Key Protected)
Runtime dynamic catalog updates with atomic SQLite transactions, dynamic FAISS updates, and in-memory BM25 rebuilds.

---

## Verification & Code Quality

```bash
# Code style and linting
ruff check app scripts tests evals

# Strict static type checks
mypy --strict app

# Full test suite with coverage
pytest -v --cov=app --cov-report=term-missing
```
