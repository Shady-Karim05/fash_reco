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

## 2. Observations from the first five metadata rows

These come from a five-row sample and must be re-measured on the full sample during ingestion. The ingestion report is the authoritative source for percentages.

| Observation | Seen in sample | Handling |
|---|---|---|
| `categories` empty | 5 of 5 | Never rely on it; derive `slot` from text |
| `price` null / missing | 770,719 of 826,108 (93.30%) | Index priced products only by default; report dropped counts |
| `description` empty | 5,176 of 8,000 (64.70%) | Rely on title and features when absent |
| Uninformative title | "Mento Streamtail" | Description reveals "thong sandal ... beach"; keep description in search text |
| Gender in two places | `Department: womens` in 2 rows; "Men's", "Women's", "Girls'" in titles | Department first, then title regex |
| Kids' items mixed in | "Girls' ... 9-10 Years" (550 of 8,000, 6.88%) | `age_group` attribute, adult by default |
| Size and colour inside title | "(Flower Mix Blue, XL)" | Extract colour; strip size from embedding text |
| Rating counts vary from 1 to 3,032 | 2.0 from 1 rating vs 4.3 from 3,032 | Bayesian average |
| Symbols and run-together text in descriptions | `✔`, `➤`, joined sentences | Cleaning step |
| `main_category` constant | "AMAZON FASHION" | Ignored |
| No season or occasion field | all rows | Keyword rules at ingestion |

The reviews sample also showed that the catalog is not only clothing (a locket, earrings, socks, and sunglasses appeared), which is why `accessory` is a slot, and that many reviews ("Great", "Five Stars") carry no search signal, which is why snippets require a minimum length.

## 3. Ingestion rules

1. Stream the metadata; do not load it all into memory.
2. Keep a product only if the title has at least 15 characters and the price is present and positive.
3. Drop non-fashion items matching plush, stuffed animal, toy, or figurine (4,350 items, 0.53%).
4. Count every dropped row by reason and print the report.
5. Sample 10,000 kept products with `seed=42`; hold out 20% for the catalog update demo.
6. Keep reviews only for sampled products: best two by `helpful_vote`, at least 40 characters, trimmed to 150. (Review snippets are implemented and tested, but optional; no review file was present in the current build).

## 4. Derived attributes

| Attribute | Source | Notes |
|---|---|---|
| `gender` | `details.Department`, then title | `men`, `women`, `unisex`, `unknown`. Note on Kids: Kids items encode boys as gender `"men"` and girls as gender `"women"`, paired with `age_group = "kids"`. |
| `age_group` | Title patterns | `kids` or `adult` |
| `slot` | Ordered keyword rules on title, features, description | `accessory`, `top`, `bottom`, `full_body`, `footwear`, `innerwear`, `unknown` |
| `colors` | Title and parenthesized text against a colour vocabulary | List of standard colors |
| `seasons`, `occasions` | Keyword rules | Used as boosts, not filters |
| `quality_score` | Bayesian average of rating | Small ranking boost only |

## 5. Known data risks & limitations

- The catalog is heavily dominated by accessories and jewelry (51.55%), while footwear (3.44%) and bottoms (4.15%) are scarce.
- Dropping unpriced products (770,719 rows, 93.30% of raw metadata) biases the catalog toward items with prices. The ingestion report quantifies this and the README reports it.
- Review snippets are optional and not included in the current index build.
- Multilingual retrieval quality across low-resource scripts requires LLM query translation and normalization; unnormalized raw cross-lingual vector search alone can exhibit semantic drift.
- Review snippets can mention things unrelated to the product's intended use; they are a weak signal and limited to two short snippets.
- The dataset is US-centric (prices in USD, US sizing). Multilingual queries do not make the catalog multilingual.

## 6. License and usage

Check the dataset terms before any use beyond research and prototyping. Raw data is never committed.
