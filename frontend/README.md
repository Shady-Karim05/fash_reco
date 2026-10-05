# Semantic Fashion Search & Recommendation — Frontend

A modern, high-performance, and responsive fashion e-commerce discovery frontend built with React, Vite, TypeScript, Tailwind CSS, and TanStack Query.

This frontend interfaces directly with the **Semantic Fashion Search & Recommendation Microservice** running on FastAPI at port `8000`.

---

## Architecture Overview

```text
Browser
  ↓
React + Vite (:5173)
  ↓ HTTP JSON
FastAPI Microservice (:8000)
  ├── POST /search   (Hybrid Dense FAISS + Sparse BM25 + Reciprocal Rank Fusion)
  ├── POST /outfit   (Deterministic Coordinated Cross-Slot Ensemble Generator)
  ├── GET /health    (Index & Catalog Readiness)
  └── GET /metrics   (Prometheus & System Metrics)
```

> **Decoupled Architecture Rule**: The frontend owns zero ranking, indexing, or recommendation algorithms. All natural language understanding, candidate retrieval, constraint satisfaction, and outfit composition are strictly owned and executed by the backend microservice.

---

## Tech Stack

- **Framework**: React 18 + Vite 5 + TypeScript
- **Routing**: React Router DOM v6
- **Styling**: Tailwind CSS + PostCSS + Custom Luxury Palette (Playfair Display & Plus Jakarta Sans typography)
- **Data Fetching & Caching**: TanStack Query (React Query v5) + Axios
- **Icons**: Lucide React

---

## Getting Started

### 1. Prerequisites
- **Node.js**: v18.0.0+ (Tested on Node v20 LTS)
- **npm**: v9.0.0+
- **Backend Microservice**: The FastAPI backend must be running on port `8000` (e.g., via Docker or `uvicorn app.main:app --port 8000`).

### 2. Installation

Navigate to the `frontend/` directory and install the dependencies:

```bash
cd frontend
npm install
```

### 3. Environment Variables Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Configured variables:

| Variable | Description | Default |
|---|---|---|
| `VITE_API_BASE_URL` | Base URL pointing to the FastAPI backend | `http://localhost:8000` |

*Note: The frontend does not hardcode `http://localhost:8000`. In development, Vite's dev server also proxies `/api` requests to ensure zero CORS hurdles.*

### 4. Running the Development Server

Start the local development server:

```bash
npm run dev
```

The application will be accessible at:
```text
http://localhost:5173
```

---

## Building for Production

### Type-Check and Build Bundle

```bash
npm run build
```

This compiles TypeScript and produces an optimized production bundle inside the `dist/` directory.

### Preview Production Build Locally

```bash
npm run preview
```

---

## Key Features & User Interface

1. **Atelier Home (`/`)**:
   - Hero section with live semantic prompt input.
   - Example search pills (e.g., *"red cocktail dress"*, *"summer linen blazer"*).
   - Prominent call-to-action cards for Catalog Search and Generative Outfit Styling.
   - Curated thematic prompt lookbooks.

2. **Semantic Search Catalog (`/search?q=...`)**:
   - Natural language fashion queries using dense Sentence Transformer vector embeddings combined with BM25.
   - Results counter, calibrated match percentage badges, and formatted prices.
   - **Desktop Layout**: 4-column / 3-column product grid with sticky filter & detected intent sidebar on the left.
   - **Mobile Layout**: Responsive grid with slide-out filter drawer.
   - Complete states: `idle`, `loading` (pulse skeletons), `success`, `empty` (with search suggestions), and user-friendly `error` handling (no raw Axios error dumps).

3. **Outfit Studio (`/outfit?q=...`)**:
   - Supports natural language ensemble prompts such as *"cocktail party outfit for women under $100"*.
   - Coordinates multi-piece looks displaying:
     - **Top**
     - **Bottom** (or **Full Body / Dress**)
     - **Footwear**
     - **Accessory**
   - Displays total ensemble price, template classification, and budget compliance status.

4. **Product Details View (`/product/:id`)**:
   - Displays all verified backend fields: title, brand, price, slot, accessory type, target audience, rank score, dense cosine similarity, and matching explanation.
   - Quick CTA to style the selected piece inside an outfit.

5. **Not Found (`*`)**:
   - Custom 404 page styled with atelier aesthetic and quick navigation back to the runway.

---

## Production Deployment Considerations

1. **CORS Configuration**:
   Ensure the backend FastAPI service allows the frontend production origin via `CORSMiddleware` (e.g. `allow_origins=["https://your-frontend-domain.com"]`).
2. **Reverse Proxy (Nginx / Cloudflare)**:
   For unified deployment, serve `frontend/dist` as static assets and reverse proxy `/search`, `/outfit`, `/health`, and `/metrics` to the upstream FastAPI container.
3. **Asset Caching**:
   Static JavaScript and CSS chunks in `dist/assets` contain content hashes and can be safely cached with `Cache-Control: max-age=31536000, immutable`.
