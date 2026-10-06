# Deployment Guide: Semantic Fashion Search & Recommendation System

This guide provides reproducible, step-by-step instructions for deploying the **Semantic Fashion Search & Recommendation Microservice** across local development, testing, and containerized Docker environments.

---

## 1. System Requirements

### Hardware Requirements
- **CPU:** Minimum 2 physical cores / 4 vCPUs (Intel Core i5 / AMD Ryzen 5 or cloud equivalent).
- **RAM:**
  - **Local Development:** Minimum 8.0 GiB (16.0 GiB recommended for running both PyTorch/FAISS and browser dev servers).
  - **Docker Container:** Minimum **3.7 GiB memory limit** (`-m 3.7g`). Peak resident set size (RSS) is ~1.45 GiB under active FAISS indexing and Sentence-Transformer embedding generation.
- **Disk Space:** Minimum 10 GiB free space (to store the catalog SQLite database, FAISS indices, Hugging Face model cache, and Docker layers).

### Operating System Compatibility
- **Windows:** Windows 10/11 64-bit with WSL2 backend or native PowerShell.
- **Linux:** Ubuntu 20.04/22.04 LTS, Debian 11/12, or RHEL 8/9.
- **macOS:** macOS Monterey (12.0) or newer (Apple Silicon M1/M2/M3 or Intel).

---

## 2. Python Version

The backend requires **Python 3.11.x** (CPython).
Verify your Python installation:

```bash
python --version
# Expected output: Python 3.11.x (e.g., Python 3.11.9)
```

> [!WARNING]
> Python 3.12+ or 3.10- may experience wheel incompatibilities with specific precompiled FAISS-CPU and PyTorch CPU distributions. Ensure Python 3.11 is active.

---

## 3. Node.js Version

The frontend requires **Node.js 18.x LTS or 20.x LTS** and **npm 9.x+**:

```bash
node -v
# Expected output: v18.x.x or v20.x.x

npm -v
# Expected output: 9.x.x or 10.x.x
```

---

## 4. Docker Requirements

- **Docker Engine:** Version 24.0 or newer.
- **Docker Compose (Optional):** Version 2.20 or newer.
- **Docker Desktop (Windows / macOS):** Ensure WSL2 integration is enabled on Windows. In Docker Desktop Settings $\to$ Resources, assign at least **4.0 GiB RAM** to the Docker daemon.

Verify Docker installation:

```bash
docker --version
# Example output: Docker version 26.1.1, build 4cf4084
```

---

## 5. Repository Setup

Clone the repository and inspect the directory structure:

```bash
git clone https://github.com/Shady-Karim05/fash_reco.git
cd fash_reco
```

### Directory Structure Overview
```text
fash_reco/
├── app/                  # FastAPI backend source code
│   ├── main.py           # Application entrypoint & routes
│   ├── service.py        # SearchService orchestration
│   ├── parser.py         # 2-Layer Query Understanding & Circuit Breaker
│   ├── index.py          # Hybrid FAISS + BM25 index
│   ├── filters.py        # Strict metadata filtering
│   ├── reranker.py       # Multi-factor candidate reranker
│   ├── outfit.py         # Progressive Candidate Expansion engine
│   └── cache.py          # Bounded LRU/TTL caching
├── data/                 # Catalog database & prebuilt indices
│   ├── catalog.db        # SQLite product catalog (22,063 active items)
│   ├── faiss.index       # Dense FAISS IndexFlatIP vector index
│   └── bm25.pkl          # Sparse BM25Okapi inverted index
├── frontend/             # Editorial React 18 + Vite client
├── tests/                # Automated pytest regression suite (301 tests)
├── Dockerfile            # Multi-stage production container build
├── pyproject.toml        # Backend package definition & dependencies
└── .env.example          # Environment configuration template
```

---

## 6. Environment Configuration

### Backend Environment Configuration
Copy the template `.env.example` to create your local `.env`:

```bash
# On Linux / macOS / PowerShell
cp .env.example .env
```

### Backend Environment Variables Reference

| Variable | Default Value | Description |
|:---|:---|:---|
| `HOST` | `0.0.0.0` | Network binding interface. |
| `PORT` | `8000` | Microservice HTTP listening port. |
| `DEBUG` | `false` | Enables debug logging and Swagger auto-reload. |
| `LLM_API_KEY` | *(empty)* | Google Gemini API key. If left blank, system falls back to Layer 1 deterministic parsing. |
| `LLM_MODEL` | `gemini-flash-lite-latest` | Model version for subjective styling query understanding. |
| `LLM_TIMEOUT_SECONDS` | `3.0` | Maximum timeout before tripping circuit breaker. |
| `EMBEDDING_MODEL_NAME` | `paraphrase-multilingual-MiniLM-L12-v2` | Sentence-Transformers 384-dimensional dense model. |
| `EMBEDDING_BATCH_SIZE` | `64` | Batch size during embedding generation. |
| `DATA_DIR` | `data` | Directory containing catalog and indices. |
| `DB_PATH` | `data/catalog.db` | SQLite catalog database path. |
| `FAISS_INDEX_PATH` | `data/faiss.index` | Serialized FAISS `IndexFlatIP` path. |
| `BM25_INDEX_PATH` | `data/bm25.pkl` | Serialized BM25 index path. |
| `RRF_K` | `60` | Constant smoothing denominator for Reciprocal Rank Fusion. |
| `RETRIEVAL_TOP_K` | `50` | Candidate pool depth per retrieval channel. |
| `LRU_CACHE_SIZE` | `1000` | Maximum bounded entries for in-memory caches. |

> [!NOTE]
> The backend operates fully even without `LLM_API_KEY`. When no key is provided, the system executes Layer-1 deterministic regex/gazetteer parsing with zero crashes or errors.

### Frontend Environment Configuration
The frontend communicates through Vite's internal development proxy or directly via `VITE_API_BASE_URL`.

Inspect or configure `frontend/.env`:
```bash
# frontend/.env
VITE_API_BASE_URL=http://localhost:8000
```

---

## 7. Backend Local Setup

### Step 1: Create Virtual Environment
```bash
# On Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# On Linux / macOS (bash/zsh)
python3.11 -m venv .venv
source .venv/bin/activate
```

### Step 2: Install Dependencies
Install CPU-optimized PyTorch wheels followed by application dependencies:

```bash
python -m pip install --upgrade pip setuptools wheel
pip install --extra-index-url https://download.pytorch.org/whl/cpu -e ".[dev]"
```

### Step 3: Verify Test Suite
Run the automated test suite to ensure all components and indices are intact:

```bash
pytest -q
# Expected output: 301 passed in ~10s
```

### Step 4: Launch Backend Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
The microservice will initialize the database, load FAISS and BM25 into memory, and listen at `http://localhost:8000`.

---

## 8. Frontend Local Setup

Open a new terminal window:

```bash
cd frontend

# Install npm dependencies
npm install

# Start Vite development server
npm run dev
```

The frontend application will be accessible at `http://localhost:5173`.
Vite is preconfigured in `frontend/vite.config.ts` to automatically proxy `/search`, `/outfit`, `/health`, and `/metrics` requests to `http://localhost:8000`.

---

## 9. Docker Build

The project features a **two-stage build** Dockerfile designed to minimize container size, isolate dependencies, and run under a non-root user.

```bash
docker build -t semantic-fashion-search:latest .
```

### Build Architecture Highlights:
- **Stage 1 (Builder):** Installs CPU-only PyTorch wheels into `/opt/venv` using `python:3.11-slim-bookworm`.
- **Stage 2 (Runtime):** Copies the isolated virtual environment and application code, creates a dedicated system user `appuser` (UID `10001`, GID `10001`), and sets up Hugging Face cache directories.

---

## 10. Docker Run

Run the container detached with a bounded memory limit and environment variables:

```bash
docker run -d \
  --name fashion-backend \
  -p 8000:8000 \
  -m 3.7g \
  --env-file .env \
  semantic-fashion-search:latest
```

### Process Management Commands

Check running container status:
```bash
docker ps
```
*Output shows container ID, image name, port mapping `0.0.0.0:8000->8000/tcp`, and health status `(healthy)`.*

Inspect live logs during startup:
```bash
docker logs -f fashion-backend
```

Stop and remove container:
```bash
docker stop fashion-backend
docker rm fashion-backend
```

---

## 11. Healthcheck

The container includes a built-in Docker `HEALTHCHECK` directive:
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
```

- **`--start-period=45s`:** Gives the container 45 seconds to download Sentence-Transformer weights and load indices into memory before failing checks.
- **`--interval=30s`:** Pings the health endpoint every 30 seconds.

Verify health via Docker inspect:
```bash
docker inspect --format='{{json .State.Health.Status}}' fashion-backend
# Output: "healthy"
```

---

## 12. API Verification

Verify the backend endpoints using `curl` (Linux/macOS) or `Invoke-RestMethod` (PowerShell).

### 1. Health Endpoint (`GET /health`)
```bash
curl -X GET http://localhost:8000/health
```
```json
{
  "status": "healthy",
  "index_loaded": true,
  "catalog_reachable": true,
  "llm_status": "ok",
  "index_size": 22063,
  "catalog_size": 22063
}
```

### 2. Semantic Search Endpoint (`POST /search`)
```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "red cocktail dress under $50", "top_k": 3}'
```
```json
{
  "results": [
    {
      "product_id": "B09P2YDVQ1",
      "title": "Women Elegant Midi Pencil Dress Ruffle Sleeve...",
      "price": 28.99,
      "slot": "full_body",
      "gender": "women",
      "score": 1.0,
      "similarity": 0.7178,
      "reason": "Matching color: red | Ideal for party"
    }
  ],
  "meta": {
    "latency_ms": 118.44,
    "index_version": 2
  }
}
```

### 3. Coordinated Outfit Recommendation (`POST /outfit`)
```bash
curl -X POST http://localhost:8000/outfit \
  -H "Content-Type: application/json" \
  -d '{"query": "formal outfit for men under $150", "top_k": 3}'
```

### 4. Metrics & Observability (`GET /metrics`)
```bash
curl -X GET http://localhost:8000/metrics
```

Prometheus exposition format:
```bash
curl -X GET http://localhost:8000/metrics/prometheus
```

---

## 13. Frontend Verification

### Production Build Test
Verify that the TypeScript types compile and the Vite production asset bundle builds cleanly:

```bash
cd frontend
npm run build
```
*Expected: zero TypeScript diagnostics and successful bundle generation in `frontend/dist`.*

### Web Interface Verification
1. Open `http://localhost:5173` in any modern browser.
2. Verify the **Atelier Fashion Engine** home page loads with luxury styling.
3. Test natural language search: enter `"winter jacket for men"` or click a curated pill.
4. Verify response latency badge displays search execution time ($<150\text{ ms}$).
5. Click a product card to verify the detail view modal and similar product recommendations.

---

## 14. Production Considerations

1. **Reverse Proxy & TLS Termination:**
   Deploy Nginx, Caddy, or an AWS Application Load Balancer in front of the container to terminate SSL/TLS and enforce rate limits:
   ```nginx
   server {
       listen 443 ssl http2;
       server_name api.atelierfashion.internal;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```
2. **Prometheus Scraping:**
   Configure Prometheus to scrape `http://fashion-backend:8000/metrics/prometheus` every 15 seconds to monitor p50/p95 latency and query throughput.
3. **Persistent Volume Mounting:**
   Mount the `data/` directory as an external volume to persist catalog updates:
   ```bash
   docker run -d \
     -v $(pwd)/data:/app/data \
     -p 8000:8000 \
     -m 3.7g \
     semantic-fashion-search:latest
   ```

---

## 15. Troubleshooting

### 1. Docker Memory Limitations (`OOMKilled` / Exit Code 137)
- **Symptom:** The container exits abruptly with code 137 during index loading or embedding generation.
- **Cause:** PyTorch and FAISS require ~1.45 GiB resident RAM. If the Docker daemon memory limit is set below 2.5 GiB, the Linux kernel OOM killer terminates the process.
- **Fix:** Allocate at least 3.7 GiB to the container via `-m 3.7g`. On Docker Desktop, navigate to **Settings $\to$ Resources $\to$ Advanced** and increase memory allocation to at least 4.0 GiB.

### 2. HuggingFace Model Download Failures
- **Symptom:** `urllib.error.URLError` or network timeouts when loading `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- **Cause:** Restricted egress or corporate proxy blocking access to `huggingface.co`.
- **Fix:** Pre-download model weights locally into the cache directory:
  ```bash
  python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
  ```
  In Docker, mount your host machine cache volume:
  ```bash
  -v $HOME/.cache/huggingface:/home/appuser/.cache/huggingface
  ```

### 3. Gemini Quota / Rate Limits (HTTP 429)
- **Symptom:** LLM query parsing logs HTTP 429 Resource Exhausted.
- **Resolution:** The system automatically protects against this! The built-in `LLMCircuitBreaker` intercepts 429 errors, trips to `OPEN` for 60 seconds, and immediately falls back to Layer 1 deterministic regex parsing. User queries never fail with HTTP 500 errors.

### 4. Port 8000 Already in Use
- **Symptom:** `ERROR: [Errno 98] Address already in use` or `bind: address already in use`.
- **Resolution:**
  - *Windows:*
    ```powershell
    netstat -ano | findstr :8000
    Stop-Process -Id <PID> -Force
    ```
  - *Linux / macOS:*
    ```bash
    lsof -i :8000
    kill -9 <PID>
    ```
  - Alternatively, map to a different host port:
    ```bash
    docker run -p 8080:8000 ...
    ```

### 5. Frontend API Connection Error
- **Symptom:** Red error banner in UI: *"Unable to connect to recommendation service"*.
- **Resolution:**
  1. Verify the backend container or process is running: `curl http://localhost:8000/health`.
  2. If using Docker for both or hosting on a custom IP, ensure `VITE_API_BASE_URL` in `frontend/.env` matches your backend address.
  3. Ensure CORS middleware in `app/main.py` permits the frontend origin.

### 6. Container Healthcheck Failure (`unhealthy`)
- **Symptom:** `docker ps` reports status `(unhealthy)`.
- **Cause:** The 45-second start period was exceeded before the model finished loading, or the index files were missing.
- **Fix:** Inspect the healthcheck error log:
  ```bash
  docker inspect --format='{{json .State.Health}}' fashion-backend
  ```
  Ensure all files in `data/` (`catalog.db`, `faiss.index`, `bm25.pkl`) exist and have read permissions.

---

## 16. Security Best Practices

1. **Non-Root Execution:** The production container executes strictly under user `appuser` (UID `10001`, GID `10001`). No container process runs as `root`.
2. **Zero Secret Leakage:** `.env` and API keys are strictly excluded from version control via `.gitignore`. Never hardcode secrets in source code or Dockerfiles.
3. **Bounded Query Boundaries:** The API restricts input strings to a maximum of 500 characters and clamps `top_k` between 1 and 50, preventing denial-of-service memory exhaustion.
4. **Prompt Injection Guardrails:** The LLM prompt treats user input as passive data enclosed in explicit delimiters, preventing prompt hijacking.
5. **No Dynamic Execution:** The microservice strictly prohibits `eval()`, `exec()`, or unparameterized SQL queries.
