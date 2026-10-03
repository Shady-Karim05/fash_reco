# Production Scale Considerations

The prototype is a single container serving about 10,000 products. This document describes what changes as it grows and why. None of the later stages are built in the prototype; they are the planned path.

## 1. Scaling stages

| Stage | Catalog size | Vector index | Keyword search | Catalog store | Cache |
|---|---|---|---|---|---|
| Prototype | ~10k | FAISS flat (exact) | `rank_bm25` in memory | SQLite | In-process LRU |
| Growth | 100k to 1M | FAISS HNSW or IVF | OpenSearch or Elasticsearch | Postgres | Redis |
| Large | 1M+ | Managed vector DB (for example Qdrant), sharded | OpenSearch cluster | Postgres + read replicas | Redis cluster |

Move up a stage when measured p95 latency, memory use, or ingestion time crosses its budget, not before.

## 2. Target architecture at scale

```mermaid
flowchart LR
    LB[Load balancer] --> A1[API replica 1]
    LB --> A2[API replica 2]
    LB --> A3[API replica N]
    A1 & A2 & A3 --> RC[(Redis cache)]
    A1 & A2 & A3 --> VDB[(Vector DB, sharded)]
    A1 & A2 & A3 --> KW[(Keyword search)]
    A1 & A2 & A3 --> PG[(Postgres)]
    A1 & A2 & A3 -.-> LLM[[LLM provider]]

    Feed([Catalog feed / admin]) --> Q[[Queue]]
    Q --> W[Embedding workers]
    W --> VDB
    W --> KW
    W --> PG
```

API replicas are stateless. Writes go through a queue so a catalog import never competes with search traffic.

## 3. Retrieval at scale

- **ANN indexing.** Exact search is fine at 10k vectors. At millions, use HNSW (best recall and latency, more memory) or IVF with product quantization (less memory, more tuning). Choose by measuring recall against exact search on a sample.
- **Sharding.** Shard by category or slot first, since most queries target a slot. Fan out and merge when a query spans slots.
- **Two-stage ranking.** Cheap retrieval returns about 50 to 200 candidates; an optional cross-encoder reranks the top 50 to 10. Add this only if evals show a quality gain worth the latency.
- **Hard filters in the index.** At scale, apply price, gender, and age group as index-level filters so filtering does not shrink the candidate list after retrieval.

## 4. Ingestion and a changing catalog

- Embedding is batched and runs in workers behind a queue. Ingestion is asynchronous at scale; the API returns a job ID.
- Upserts are incremental. A nightly job rebuilds the full index from the source of truth to remove drift and compact deleted entries.
- Soft delete takes effect immediately through a filter; physical removal happens at the nightly rebuild.
- Version rows and bump an index version on each write so caches invalidate without a flush.
- Blue-green index swap for full rebuilds: build the new index alongside the old one, then switch traffic.
- Re-embedding after a model change is a full rebuild, run offline and swapped in.

## 5. Measured Runtime Characteristics (N=24,000 Catalog Benchmark)

Empirical performance measured on single-node Intel/AMD Windows workstation (Python 3.11):

### 5.1 Ingestion & Update Pipeline Timings (Per 200-Item Batch)
Measured from `scripts/simulate_updates.py` across 30 incremental update batches (6,000 total items):

| Ingestion Step | Average Latency (ms) | % of Batch Time | Complexity & Notes |
|---|---|---|---|
| **Validate & Clean Text** | 285.74 ms | 2.01% | Regex normalization, attribute derivation |
| **Dense Embedding (CPU)** | 12,489.85 ms | 87.97% | MiniLM-L12-v2 CPU inference (bottleneck) |
| **SQLite Persistence** | 183.17 ms | 1.29% | WAL mode batch insert with vector BLOBs |
| **FAISS Dynamic Update** | 3.41 ms | 0.02% | Atomic in-place vector addition |
| **BM25 Rebuild Cost** | 1,212.25 ms | 8.54% | Rebuilding `rank_bm25` index over all active documents |
| **Bookkeeping & Cache** | 23.41 ms | 0.16% | Atomic index version bump, cache invalidation |
| **Total Batch Time** | **14,197.83 ms** | **100.0%** | **~71.0 ms per product** |

### 5.2 BM25 In-Memory Rebuild Trade-Off
- `rank_bm25` lacks incremental indexing; modifying a batch requires re-tokenizing and reconstructing internal doc frequencies across the entire catalog ($O(N)$ text scanning).
- At $N=24,000$, BM25 rebuild requires **1.21 seconds** per batch.
- While SQLite writes and FAISS updates take $<200$ ms combined, BM25 rebuild dominates post-embedding write latency.
- In production at $N \ge 100\text{k}$, BM25 must be offloaded to OpenSearch/Elasticsearch with inverted index segment merges to eliminate full-corpus rebuilds.

### 5.3 Cold-Start & Recovery Timings (Like-for-Like Comparison)
- **Initial Dense Embedding (CPU Inference):**
  - Scope: 24,000 active catalog items embedded from raw text strings.
  - Duration: **391.80 s** (average **16.32 ms per row**).
  - Text extraction and schema normalization: 22.90 s.
- **Cold-Start Restart (Loading Persisted Embeddings from SQLite):**
  - Scope: 24,000 active catalog items loaded from SQLite database (`data/catalog.db`).
  - Duration: **12.30 s** total (including SQLite BLOB read, FAISS IndexFlatIP reconstruction, and BM25 token corpus loading; average **0.51 ms per row**).
  - Rows Re-embedded: **0** (all 24,000 rows loaded from pre-computed BLOB storage).

### 5.4 Search Latency During Concurrent Ingestion
- Measured across 3,164 continuous concurrent search requests while writing 30 batches of 200 items each:
  - Search Latency p50: **109.20 ms**
  - Search Latency p95: **190.98 ms**
  - Zero search failures (0 errors, 100% availability under read-write load).
  - Version consistency: Queries accurately saw `index_version` advance from 1 to 31 without restarting.
| Embedding model on GPU or batched inference | Higher throughput for ingestion |
| Precomputed attributes | No LLM at query time for catalog data |

Track LLM spend per 1,000 queries and set a budget alarm.

## 6. Reliability

- Health checks: `/health` reports liveness and readiness (index loaded, catalog reachable, LLM reachable or degraded).
- Graceful degradation is a requirement: the LLM can be down and search still works.
- Rate limiting per client and request size limits at the gateway.
- Timeouts and retries with backoff on every external call; circuit breaker around the LLM.
- Backups of the catalog; indexes are reproducible from it.

## 7. Observability

- Structured JSON logs with a request ID, parsed filters, fallback flag, latency, and result count. No secrets or raw PII in logs.
- Metrics: latency percentiles, fallback rate, zero-result rate, cache hit rate, index size, ingestion lag.
- Alerts: fallback rate, zero-result rate, p95 regression, ingestion backlog.
- Query-drift monitoring: compare recent query topics and zero-result clusters against the catalog's coverage.

## 8. Quality improvement loop

1. Log impressions and clicks (with consent and privacy review).
2. Use clicks to build relevance labels, replacing the keyword proxy.
3. Train or tune a reranker; test with A/B experiments.
4. Evaluate per language and per category, and fix the weakest slice first.

## 9. Security and compliance

- Secrets from environment or a secret manager; never in code or logs.
- Input validation and length limits on all endpoints; protect `POST /products` and `DELETE` with authentication, since they change the catalog.
- Treat product text and reviews as untrusted input when sending them to an LLM (prompt-injection risk); the parser sees only the user query, not catalog text.
- Review dataset licensing before commercial use.

## 10. Future work

Cross-encoder reranking, image embeddings, personalization, `bought_together` signals for outfit pairing, LLM-based attribute tagging at scale, and size and availability filters.
