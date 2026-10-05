# System Limitations and Failure Modes

This document catalogs observed failure modes, edge cases, and known architectural boundaries identified during evaluation of the Semantic Fashion Search microservice. Every failure case noted here is derived directly from empirical evaluation outputs, log traces, and audit samples.

---

## 1. Catalog Noise and Search Eligibility Guard

In the active catalog of 24,000 products extracted from the Amazon Fashion dataset, approximately 7.71% of items are classified into the `unknown` slot by the locked baseline classifier.
- **Peripheral Noise**: Keychains, vinyl decals, car stickers, novelty wall decor, loose zipper pulls, replacement buttons, ribbon spools, CPR training masks, and hardware tool holsters categorized under "Clothing, Shoes & Jewelry".
- **Search Eligibility Guard Layer (`app/attribute_correction.py`)**:
  - Non-destructive deterministic guard: `is_search_eligible_product(product, query, parsed)`.
  - **Rule 1**: Classified fashion items (`slot != "unknown"`) are retained.
  - **Rule 2**: Obvious peripheral items in the `unknown` slot are suppressed from generic fashion queries.
  - **Rule 3 (Query Awareness)**: `unknown` does NOT mean automatically invalid. If a user explicitly searches for peripheral items (e.g. `shoe charms`, `zipper pull`, `replacement buttons`, `birthday sash`), the guard retains them.
  - **Rule 4**: Legitimate fashion apparel items residing in `unknown` without peripheral tokens remain fully searchable.
- **Remaining Limitation**: Heuristic pattern matching covers known catalog noise categories; newly introduced unclassified non-apparel categories with novel vocabulary may evade filtering unless added to the deterministic lexicon.

---

## 2. Catalog Baseline vs. Effective Runtime Attributes

The baseline catalog attributes stored in `data/catalog.db` are locked and immutable ($N=24,000$ active rows, SHA-256 `1e70fb6a...`). Classification logic in `app/attributes.py` is likewise locked.
- **Runtime Interpretation Layer (`app/attribute_correction.py`)**:
  - `get_effective_product_slots(product)`: Expands multi-intent garments without mutating the database. For example, `American Trends Shorts Pajamas Set` (stored as `full_body` due to pajama keyword priority) resolves contextually to `{full_body, bottom}`, allowing retrieval under "shorts" or "bottoms". `Humaira Pendant Costume Jewelry` (stored as `full_body` due to "costume") resolves to `{accessory}`.
  - `get_effective_age_group(product)`: Corrects superficial token collisions. `infant CPR training mask` resolves to `adult` (training equipment, not babywear). `Sweet 16 Birthday Sash` resolves to `adult` (adult teen sizing). Adult shoe charms without baby/toddler apparel sizing resolve to `adult`.
  - `get_effective_gender(product)`: Extracts effective gender compatibility.
- **Remaining Limitation**: The catalog database retains the original raw classifications for auditing reproducibility; downstream consumers inspecting `data/catalog.db` directly without `app.attribute_correction` see raw uncorrected attributes.

---

## 3. Outfit Semantic/Style Compatibility vs. True Visual Compatibility

Outfit composition enforces both hard contract gates and soft compatibility scoring:
- **Hard Constraints**: Budget compliance ($\le \text{max\_budget}$), minimum item price threshold (`OUTFIT_MIN_ITEM_PRICE = 2.00`), demographic coherence (100% gender and age matching across slots), functional slot templates.
- **Semantic / Style Compatibility (`app/outfit.py`)**:
  - Occasion coherence bonus: Shared occasions (formal, casual, beach, workout, party, wedding).
  - Seasonal coherence bonus: Shared seasons (summer, winter, spring, fall).
  - Style conflict penalties: Formal + athletic clash (e.g., tuxedo + running shoes) or formal + novelty clash (e.g., formal gown + LED festival jacket).
  - Pairwise dense embedding cohesion: Mean pairwise cosine similarity across product embedding vectors.
  - Final score: $\text{score} = \text{mean\_individual\_score} + 0.15 \times \text{compatibility\_score}$.
- **CRITICAL LIMITATION — No True Visual Compatibility**:
  - The microservice evaluates **semantic and textual style compatibility**, NOT **visual compatibility**.
  - Raw product images are not downloaded or embedded. Dense vectors originate from text metadata (`paraphrase-multilingual-MiniLM-L12-v2`).
  - Subtle visual clashes (e.g. pattern clashes, undertone mismatch, visual silhouette imbalance) cannot be detected without computer vision models (e.g. CLIP / fashion vision encoders).

---

## 4. Deterministic Multilingual Fallback Engine

When the LLM parser is unavailable (circuit breaker OPEN on 429/503), the system routes queries through `app/multilingual.py`:
- **Deterministic Pipeline**:
  $$\text{Query} \to \text{Language Detection} \to \text{Lexicon Normalization} \to \begin{cases} \text{Structured Filters (slot, gender, age, price)} \\ \text{Canonical English Query} \end{cases} \to \begin{cases} \text{FAISS} \\ \text{BM25 (English tokens)} \end{cases} \to \text{RRF} (k=60)$$
- **Supported Languages**: English (`en`), Spanish (`es`), French (`fr`), Hindi (`hi`), Tamil (`ta`).
- **Offline & Zero-Call**: Operates 100% offline without external translation APIs or Gemini calls.
- **BM25 Activation**: Translating slot and intent keywords into `normalized_query_en` enables BM25 Okapi to match English catalog terms, preventing the failure mode where non-Latin queries fell back exclusively to dense embeddings.
- **Remaining Limitation**: Lexicons cover benchmark and common fashion terminology; open-domain colloquial slang or unsupported languages will trigger `low_confidence = True` and warning `filters_not_applied_without_llm`.

---

## 5. Evaluation Reporting: Hard Contract Gates vs. Soft Relevance Proxies

To prevent misleading claims of "perfection", the evaluation harness strictly bifurcates metrics:
- **Hard Contract Gates (System Correctness Gates)**:
  - English constraint violations = 0 (Gate PASS/FAIL).
  - Kids leakage on adult queries = 0 (Gate PASS/FAIL).
  - Outfit age coherence = 100.0% (Gate PASS/FAIL).
  - Outfit gender coherence = 100.0% (Gate PASS/FAIL).
  - Outfit budget compliance = 100.0% (Gate PASS/FAIL).
  - Forced fallback resilience = 100.0% (Gate PASS/FAIL).
- **Soft Relevance Proxies (Automated Heuristics)**:
  - `Precision@5`, `Recall@5`, `MRR@10`, `Multilingual Top-5 Overlap`.
  - These are **automated regex-based proxy metrics**, NOT human ground-truth labels.
  - Regexes may credit superficial keyword matches or penalize valid synonyms.
- **Human Ground-Truth Audit Status**:
  - `data/audit_sample.csv` contains 100 representative products awaiting manual human annotation.
  - Verified via `scripts/check_audit_status.py`. Current completion: 0.0% (unannotated). No automated script is permitted to fabricate human annotations.
