# Semantic Fashion Search

A microservice that turns natural-language, multilingual shopping queries into relevant fashion products or complete outfits.

> "I need an outfit to go to the beach this summer" returns sandals, swimwear, shorts, and a sun hat, even though no product title contains those words.

**Status:** initial commit. Design and documentation are complete; implementation follows the phases below. Evaluation numbers will be added to this README only after `evals/run_evals.py` has produced them.

---

## Why this exists

Keyword search matches words, not meaning. Shoppers describe occasions ("wedding guest", "beach holiday"), not product types ("sarong", "sandal"). They also search in their own language and state hard constraints ("under $30", "for men") that a ranking model must never violate.

This service combines:

1. **LLM query parsing** to extract intent and constraints from any language
2. **Hybrid retrieval** (multilingual embeddings + BM25, fused with Reciprocal Rank Fusion)
3. **Hard filters** for price, gender, and age group, so constraints are guaranteed, not hoped for
4. **Outfit composition** that returns one item per slot instead of five near-duplicates
5. **Incremental catalog updates** so new products are searchable without a restart or rebuild

## Key design decisions (short version)

| Decision | Reason |
|---|---|
| Hard filters, not soft similarity, for price/gender/age | "Under $30" must never return $45. Embeddings cannot guarantee that. |
| Hybrid search (vector + BM25) | Embeddings blur exact terms such as brand names; BM25 misses meaning. RRF combines both without score calibration. |
| Derive attributes at ingestion, not query time | Slot, gender, season, and colour are computed once and stored. Keeps the LLM off the hot path for catalog data. |
| LLM parser with rule-free fallback | If the LLM is down or returns bad JSON, search still works. `/search` never fails because of the LLM. |
| SQLite as source of truth, indexes rebuilt on start | Simple, durable, and restart-safe. FAISS and BM25 are caches of the catalog. |
| Priced products only in the index (configurable) | About half of the raw catalog has no price. Indexing them would break the price guarantee. See `docs/data-findings.md`. |

Full reasoning is in [`docs/system-design.md`](docs/system-design.md).

## Documentation

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Components, diagrams, technology choices |
| [`docs/system-design.md`](docs/system-design.md) | Request flows, data model, failure handling, design trade-offs |
| [`docs/data-findings.md`](docs/data-findings.md) | What the Amazon Fashion data actually looks like and how we handle it |
| [`docs/evaluation.md`](docs/evaluation.md) | Metrics, test set design, pass/fail gates |
| [`docs/production-scale.md`](docs/production-scale.md) | How this grows from 10k to millions of products |
| [`SPEC.md`](SPEC.md) | Implementation spec and coding standards used to build this |

## Tech stack

Python 3.11, FastAPI, Pydantic v2, sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`), FAISS, rank_bm25, SQLite, pytest, ruff, mypy, Docker.

## API (target contract)

| Method and path | Purpose |
|---|---|
| `POST /search` | Natural-language query in, ranked products or an outfit out |
| `POST /products` | Add or update products (clean, derive attributes, embed, upsert) |
| `DELETE /products/{id}` | Soft delete |
| `GET /health` | Liveness and readiness |
| `GET /metrics` | Latency percentiles, fallback rate, zero-result rate, cache hit rate |

Example request:

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "men'"'"'s outfit for the beach this summer under 60 dollars", "mode": "outfit"}'
```

Example response shape:

```json
{
  "results": [
    {
      "product_id": "B0811M2JG9",
      "title": "Example product",
      "price": 29.81,
      "slot": "footwear",
      "score": 0.0312,
      "reason": "Thong sandal described for beach use"
    }
  ],
  "meta": {
    "parsed_filters": {"gender": "men", "max_price": 60, "season": "summer"},
    "used_fallback": false,
    "latency_ms": 0,
    "index_version": 1,
    "excluded_by_filters": 0
  }
}
```

The values above are illustrative of the schema only.

## Getting started

```bash
# 1. Environment
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # set LLM_API_KEY

# 2. Data: see data/README.md for download instructions
python scripts/build_index.py   # prints an ingestion report (rows read, dropped, indexed)

# 3. Run
uvicorn app.main:app --reload

# 4. Test and evaluate
pytest
python evals/run_evals.py
```

If the raw data is not available, `python scripts/generate_synthetic.py` creates a small synthetic catalog with the same schema.

## Repository layout

```
app/        service code (routes, parser, index, filters, outfit, catalog)
scripts/    ingestion, synthetic data, catalog update simulation
evals/      labeled queries and the evaluation runner
tests/      unit and integration tests, plus fixtures from real sample rows
docs/       architecture and design documents
```

## Implementation roadmap

- [x] Design, specification, and documentation
- [ ] Phase 1: streaming ingestion, cleaning, attribute rules, catalog
- [ ] Phase 2: embeddings, FAISS + BM25, RRF fusion, `/search` without LLM
- [ ] Phase 3: LLM parser with fallback, hard filters
- [ ] Phase 4: `POST /products`, soft delete, versioning, update simulation
- [ ] Phase 5: outfit mode, confidence threshold, cache, `/metrics`
- [ ] Phase 6: evaluation suite
- [ ] Phase 7: Docker and final README results

## Evaluation results

_Not yet available._ This section will be filled from `evals/results.json`. No figures are reported before they are measured.

## Known limitations

- The dataset has no relevance labels, so the first evaluation uses a keyword-regex proxy, supplemented by a manual spot-check. See [`docs/evaluation.md`](docs/evaluation.md).
- Season and occasion are inferred from text, so they are boosts and not guarantees.
- No personalization; results depend only on the query and the catalog.
- Text only; product images are not used.

## Dataset and attribution

Uses the Amazon Reviews 2023 dataset (McAuley Lab) for research and prototyping. Check the dataset's terms before any commercial use. Raw data is not committed to this repository.

## License

To be decided by the repository owner.
