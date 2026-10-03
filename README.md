# Semantic Fashion Recommendation Microservice

A production-style microservice for semantic and multilingual fashion search on Amazon Fashion data, built with FastAPI, Sentence-Transformers, FAISS, BM25, and SQLite.

## Overview

- **Model:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-d dense embeddings, L2-normalized)
- **Vector Search:** FAISS `IndexFlatIP` (Cosine similarity over normalized vectors)
- **Keyword Search:** BM25Okapi (`rank_bm25`) over cleaned and derived search text
- **Fusion:** Reciprocal Rank Fusion (RRF, $k=60$) combining dense semantic vectors and sparse BM25 scores
- **Storage:** SQLite catalog with ACID transactions, schema versioning, soft deletion, and runtime dynamic indexing
- **API:** FastAPI + Uvicorn with Pydantic v2 schemas and structured error handling

---

## Ingestion & Dataset Findings

Dataset: Amazon Reviews 2023 (`Amazon Fashion` category from McAuley Lab).

Ingestion report summary from `data/ingestion_report.json`:
- **Total rows read:** 826,108
- **Dropped (no price / null / <= 0):** 770,719 (93.30%)
- **Dropped (non-fashion keyword: plush/toy/etc.):** 4,350 (0.53%)
- **Dropped (short title < 15 chars):** 1,178 (0.14%)
- **Dropped (no title):** 58 (0.01%)
- **Valid kept rows:** 49,803 (6.03%)
- **Sampled (Reservoir `seed=42`):** 10,000 (8,000 active catalog products, 2,000 held-out update test set)

### Attribute Coverage (Catalog $N=8,000$)

| Attribute | Breakdown |
|---|---|
| **Slot** | accessory: 51.55% (4,124), top: 15.43% (1,234), unknown: 15.26% (1,221), full_body: 10.17% (814), bottom: 4.15% (332), footwear: 3.44% (275) |
| **Gender** | women: 36.78% (2,942), unknown: 28.40% (2,272), men: 18.07% (1,446), unisex: 16.75% (1,340) |
| **Age Group** | adult: 93.12% (7,450), kids: 6.88% (550) |
| **Data Completeness** | empty description: 64.70% (5,176), empty features: 22.80% (1,824), no extracted color: 52.24% (4,179), review snippets: 0.00% (reviews file not used in current build) |

### Known Limitations
- The catalog is dominated by jewelry and accessories (51.55%), with bottoms (4.15%) and footwear (3.44%) being scarce.
- Review snippets are implemented but optional, and were not included in the current index build.
- `score` is an RRF rank fusion score (query-dependent and non-comparable across queries); `similarity` is true cosine similarity ($[-1.0, 1.0]$).

---

## Quickstart

### 1. Environment Setup
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. Ingestion & Index Building
```bash
python scripts/build_index.py
```

### 3. Run the Service
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4. Search Evaluation Script
```bash
python scripts/try_queries.py
```

---

## API Endpoints

### `GET /health`
Returns service liveness, readiness, index size, and component status.

### `POST /search`
Hybrid semantic search with fallback query execution and RRF ranking.

Example request:
```json
{
  "query": "men's running shorts",
  "top_k": 5
}
```

---

## Testing & Quality Assurance

```bash
ruff check app scripts tests
mypy --strict app
pytest -v --cov=app --cov-report=term-missing
```
