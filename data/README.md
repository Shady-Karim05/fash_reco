# Dataset Instructions: Amazon Fashion 2023

This service uses the Amazon Reviews 2023 dataset for the **Amazon Fashion** category, provided by the McAuley Lab at UC San Diego:
- Source: [Amazon Reviews 2023 (McAuley Lab)](https://amazon-reviews-2023.github.io/)

## Expected Files

Place raw files inside `data/` or in the project root:

1. **Product Metadata:**
   - Filename: `meta_Amazon_Fashion.jsonl` (or `data/meta_Amazon_Fashion.jsonl`)
   - Schema: JSONL format with fields `parent_asin`, `title`, `features`, `description`, `price`, `store`, `average_rating`, `rating_number`, `details`, `images`.

2. **User Reviews:**
   - Filename: `Amazon_Fashion.jsonl` (or `data/Amazon_Fashion.jsonl`)
   - Schema: JSONL format with fields `parent_asin`, `text`, `rating`, `helpful_vote`.

## Ingestion & Index Building

Run the streaming ingestion script:

```bash
python scripts/build_index.py
```

If the raw data files are not present, generate a synthetic catalog for local testing and development:

```bash
python scripts/generate_synthetic.py
```

This creates ~500 realistic synthetic fashion items adhering to the exact schema.
