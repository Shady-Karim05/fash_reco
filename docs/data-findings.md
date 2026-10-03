# Data Findings

Source: Amazon Reviews 2023, Amazon Fashion (McAuley Lab). Two files: product metadata and reviews, joined on `parent_asin` (not `asin`, because variants share a parent).

## 1. Fields used and ignored

| Field | Use |
|---|---|
| `parent_asin` | Product ID and join key |
| `title` | Primary text; display name |
| `features`, `description` | Extra embedding text after cleaning |
| `price` | Hard price filter |
| `store` | Brand |
| `details` | `Department` gives gender; other keys optional |
| `average_rating`, `rating_number` | Bayesian quality score |
| `images` | Only the MAIN `large` URL, for display |
| Reviews `text`, `helpful_vote` | Up to two short snippets per product for occasion cues |
| `main_category`, `categories`, `videos`, `bought_together` | Ignored (see below) |

## 2. Ingestion & Catalog Distributions (Measured on Full N=24,000 Build)

From `data/ingestion_report.json` ($N=24,000$ active catalog rows):
- **Raw Rows Processed:** 826,275 rows streamed.
- **Valid Rows Kept:** 30,000 rows (24,000 initial active catalog, 6,000 held-out updates).
- **Price Missing Dropped:** 747,562 rows (90.47%).
- **Short Title Dropped:** 44,176 rows (5.35%).
- **Non-Fashion Filtered:** 4,537 rows (0.55%) dropped via `NON_FASHION_KEYWORDS` (e.g. automotive accessories, plush toys, pet harnesses).

### Slot Distribution ($N=24,000$)
- `accessory`: 13,609 (56.70%)
- `top`: 3,649 (15.20%)
- `full_body`: 2,324 (9.68%)
- `unknown`: 1,851 (7.71%)
- `bottom`: 1,343 (5.60%)
- `footwear`: 787 (3.28%)
- `innerwear`: 437 (1.82%)

### Gender & Demographic Distribution ($N=24,000$)
- `women`: 8,878 (36.99%)
- `unknown`: 6,804 (28.35%)
- `men`: 4,375 (18.23%)
- `unisex`: 3,943 (16.43%)
- `adult`: 22,173 (92.39%)
- `kids`: 1,827 (7.61%)

---

## 5. Known Data Risks & Findings

1. **Unknown Gender Exclusion:**
   - 28.35% (6,804 items) of the catalog has `gender = "unknown"` because neither `Department` nor the title contains explicit gender markers (common for unisex jewelry, bags, beanies, and sunglasses).
   - Under strict gender filtering (`gender_include_unknown = False`), all 6,804 items are systematically excluded from results when a user query specifies a gender constraint (e.g. `men` or `women`).
   - If desired, setting `GENDER_INCLUDE_UNKNOWN=true` in `.env` allows `unknown` items to pass gender filters alongside explicit gender and unisex matches.
2. **Catalog Imbalance:**
   - Accessories dominate at 56.70%, while footwear (3.28%) and bottoms (5.60%) are scarce.
   - This asymmetry impacts outfit composition: full-body templates (`full_body + footwear + accessory`) succeed more easily than separate top/bottom templates due to the scarcity of bottom candidates.
3. **Price Filtering Bias:**
   - 90.47% of the raw McAuley Lab fashion dataset was dropped due to null or missing prices, concentrating the catalog on products with explicit price tags.
4. **Cross-Lingual Embedding Limitations:**
   - Multilingual queries in low-resource scripts (e.g. Tamil) experience semantic drift into jewelry and costumes when unaugmented by LLM query translation. Dense retrieval alone provides a 9.91% top-5 overlap across languages, which rises to 100% when normalized into English.

## 6. License and usage

Check the dataset terms before any use beyond research and prototyping. Raw data is never committed.
