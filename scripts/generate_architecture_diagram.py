"""Generate high-resolution architecture diagram for docs/architecture.png."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def create_diagram(output_path: Path) -> None:
    width = 1600
    height = 1500
    img = Image.new("RGB", (width, height), color="#0B132B")  # Deep Navy Slate
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("arial.ttf", 26)
        font_sub = ImageFont.truetype("arial.ttf", 15)
        font_box_bold = ImageFont.truetype("arialbd.ttf", 15)
        font_small = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_box_bold = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Draw Title Header
    draw.text(
        (width // 2, 40),
        "Semantic Fashion Search & Recommendation Microservice",
        font=font_title,
        fill="#F8FAFC",
        anchor="mm",
    )
    draw.text(
        (width // 2, 70),
        "Final System Architecture & Runtime Inference Pipeline (Production Baseline)",
        font=font_sub,
        fill="#94A3B8",
        anchor="mm",
    )

    # Helper function to draw rounded boxes
    def draw_card(x1, y1, x2, y2, bg, border, title, lines=None, radius=8):
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=bg, outline=border, width=2)
        cx = (x1 + x2) // 2
        draw.text((cx, y1 + 16), title, font=font_box_bold, fill="#FFFFFF", anchor="mm")
        if lines:
            curr_y = y1 + 36
            for line in lines:
                draw.text((cx, curr_y), line, font=font_small, fill="#CBD5E1", anchor="mm")
                curr_y += 16

    def draw_arrow(x1, y1, x2, y2, color="#38BDF8", width=2):
        draw.line([x1, y1, x2, y2], fill=color, width=width)
        import math

        angle = math.atan2(y2 - y1, x2 - x1)
        arrow_size = 7
        ax1 = x2 - arrow_size * math.cos(angle - math.pi / 6)
        ay1 = y2 - arrow_size * math.sin(angle - math.pi / 6)
        ax2 = x2 - arrow_size * math.cos(angle + math.pi / 6)
        ay2 = y2 - arrow_size * math.sin(angle + math.pi / 6)
        draw.polygon([(x2, y2), (ax1, ay1), (ax2, ay2)], fill=color)

    # =========================================================================
    # COLUMN 1: Offline Ingestion & Dynamic Updates (Left: x=70..390)
    # =========================================================================
    draw.text(
        (230, 115), "OFFLINE INGESTION PIPELINE", font=font_box_bold, fill="#38BDF8", anchor="mm"
    )

    draw_card(
        70,
        140,
        390,
        210,
        "#1E293B",
        "#475569",
        "Raw Dataset (JSONL)",
        ["meta_Amazon_Fashion (30k Sample)", "Raw metadata, price, features"],
    )
    draw_arrow(230, 210, 230, 240)

    draw_card(
        70,
        240,
        390,
        310,
        "#1E293B",
        "#475569",
        "Cleaning & Transformation",
        ["Title filter >= 15 chars, noise strip", "Currency formatting & sanitization"],
    )
    draw_arrow(230, 310, 230, 340)

    draw_card(
        70,
        340,
        390,
        410,
        "#1E293B",
        "#475569",
        "Attribute Extraction",
        ["Slot, Gender, Age, Occasion, Color", "Bayesian Quality Score (m=10)"],
    )
    draw_arrow(230, 410, 230, 440)

    draw_card(
        70,
        440,
        390,
        510,
        "#1E293B",
        "#10B981",
        "SQLite Catalog DB",
        ["24,000 active + 6,000 held-out", "Integrity SHA-256 protected"],
    )
    draw_arrow(230, 510, 230, 540)

    draw_card(
        70,
        540,
        390,
        610,
        "#1E293B",
        "#475569",
        "Multilingual Embedder",
        ["paraphrase-multilingual-MiniLM-L12-v2", "384-dim normalized dense vectors"],
    )
    draw_arrow(230, 610, 230, 640)

    draw_card(
        70,
        640,
        390,
        715,
        "#1E293B",
        "#818CF8",
        "Dual In-Memory Index",
        ["FAISS IndexFlatIP (Dense vectors)", "BM25Okapi (Corpus vocabulary)"],
    )

    # Dynamic Catalog Updates (Bottom-Left)
    draw.text(
        (230, 775), "DYNAMIC CATALOG UPDATES", font=font_box_bold, fill="#F59E0B", anchor="mm"
    )
    draw_card(
        70,
        800,
        390,
        875,
        "#1E293B",
        "#F59E0B",
        "POST /products Admin API",
        ["Upsert single/batch products", "Atomic transaction rollback"],
    )
    draw_arrow(230, 875, 230, 905, color="#F59E0B")
    draw_card(
        70,
        905,
        390,
        980,
        "#1E293B",
        "#F59E0B",
        "Atomic SQLite & Index Sync",
        ["Persist SQLite + update vectors/tokens", "Increment index_version"],
    )
    draw_arrow(230, 980, 230, 1010, color="#F59E0B")
    draw_card(
        70,
        1010,
        390,
        1085,
        "#1E293B",
        "#EF4444",
        "Cache Invalidation",
        ["Purge stale query cache entries", "Enforce catalog consistency"],
    )

    # Link from Dual Index to Dense/Sparse in main pipeline
    draw.line([390, 677, 450, 677], fill="#818CF8", width=2)
    draw.line([450, 677, 450, 565], fill="#818CF8", width=2)
    draw_arrow(450, 565, 520, 565, color="#818CF8")

    # =========================================================================
    # COLUMN 2: Main Search Pipeline (Center: x=460..1060)
    # =========================================================================
    draw.text(
        (760, 115),
        "RUNTIME INFERENCE & RETRIEVAL ENGINE",
        font=font_box_bold,
        fill="#38BDF8",
        anchor="mm",
    )

    draw_card(
        660, 140, 860, 200, "#334155", "#64748B", "Client / Frontend", ["REST JSON API Requests"]
    )
    draw_arrow(760, 200, 760, 225)

    draw_card(
        640,
        225,
        880,
        285,
        "#1E293B",
        "#38BDF8",
        "FastAPI Microservice",
        ["Endpoints: /search, /products, /health", "Prometheus & rolling metrics"],
    )

    # Branching from FastAPI
    draw.line([760, 285, 760, 305], fill="#38BDF8", width=2)
    draw.line([565, 305, 955, 305], fill="#38BDF8", width=2)

    # Products admin branch
    draw_arrow(565, 305, 565, 325)
    draw_card(
        460,
        325,
        670,
        385,
        "#1E293B",
        "#F59E0B",
        "POST /products",
        ["Admin authorization gate", "Atomic batch ingestion"],
    )

    # Search branch
    draw_arrow(955, 305, 955, 325)
    draw_card(
        845,
        325,
        1065,
        385,
        "#1E293B",
        "#38BDF8",
        "POST /search",
        ["Accepts query, mode, top_k", "mode='product' | 'outfit'"],
    )

    draw_arrow(955, 385, 760, 415)

    # Query Understanding
    draw_card(
        540,
        415,
        980,
        490,
        "#1E293B",
        "#818CF8",
        "Query Parser & Circuit Breaker",
        [
            "Structured intent extraction: gender, age, budget, occasion",
            "Circuit Breaker (fail_max=3, cooldown=60s) -> Regex/Multilingual Fallback",
        ],
    )
    draw_arrow(760, 490, 760, 520)

    # Dual Hybrid Search
    draw_card(
        520,
        520,
        740,
        595,
        "#1E293B",
        "#6366F1",
        "Dense Vector Search",
        ["FAISS Cosine Similarity", "Raw + Translated English query"],
    )
    draw_card(
        780,
        520,
        1000,
        595,
        "#1E293B",
        "#6366F1",
        "Sparse Keyword Search",
        ["BM25Okapi scoring", "Stopword filter & vocab guard"],
    )

    draw_arrow(630, 595, 715, 630)
    draw_arrow(890, 595, 805, 630)

    # Fusion & Post-Filtering (with 30px gap between every card)
    draw_card(
        560,
        630,
        960,
        705,
        "#1E293B",
        "#A855F7",
        "Reciprocal Rank Fusion (RRF)",
        ["k=60 rank reciprocal fusion", "Merges vector & keyword rank lists"],
    )
    draw_arrow(760, 705, 760, 735)

    draw_card(
        560,
        735,
        960,
        810,
        "#1E293B",
        "#EC4899",
        "Search Eligibility Guard",
        ["Excludes active=0, innerwear policy", "Low-price and noise protection"],
    )
    draw_arrow(760, 810, 760, 840)

    draw_card(
        560,
        840,
        960,
        915,
        "#1E293B",
        "#EC4899",
        "Effective Attribute Correction",
        ["Runtime contextual re-interpretation", "Protected baseline rules preserved"],
    )
    draw_arrow(760, 915, 760, 945)

    draw_card(
        560,
        945,
        960,
        1020,
        "#1E293B",
        "#F43F5E",
        "Strict Hard Filters",
        [
            "Gender strict (unknowns excluded)",
            "Age group strict (adult vs kids)",
            "Individual budget limits",
        ],
    )
    draw_arrow(760, 1020, 760, 1050)

    draw_card(
        560,
        1050,
        960,
        1125,
        "#1E293B",
        "#10B981",
        "Soft Boost & Quality Ranking",
        [
            "Bayesian quality score weight (0.05)",
            "Season, occasion, brand boosts",
            "Near-duplicate title collapse",
        ],
    )
    draw_arrow(760, 1125, 760, 1160)

    # Branching to Product vs Outfit Result
    draw.line([760, 1160, 760, 1190], fill="#38BDF8", width=2)
    draw.line([635, 1190, 1170, 1190], fill="#38BDF8", width=2)

    # Product Result
    draw_arrow(635, 1190, 635, 1220)
    draw_card(
        510,
        1220,
        760,
        1315,
        "#064E3B",
        "#10B981",
        "Product Results (/search)",
        [
            "Ranked SearchResultItems",
            "Deterministic explanations",
            "SearchMeta (latency, version)",
        ],
    )

    # =========================================================================
    # COLUMN 3: Outfit Composition Subsystem (Right: x=1180..1520)
    # =========================================================================
    draw.text(
        (1350, 485), "OUTFIT COMPOSITION ENGINE", font=font_box_bold, fill="#38BDF8", anchor="mm"
    )

    draw_arrow(1170, 1190, 1170, 520)
    draw_arrow(1170, 520, 1220, 550)

    draw_card(
        1180,
        520,
        1520,
        600,
        "#1E293B",
        "#F59E0B",
        "Progressive Candidate Expansion",
        [
            "Pool depths: 50 -> 100 -> 200 -> 400",
            "Recovers scarce slots (footwear/bottom)",
            "Stops early when full template forms",
        ],
    )
    draw_arrow(1350, 600, 1350, 630)

    draw_card(
        1180,
        630,
        1520,
        710,
        "#1E293B",
        "#8B5CF6",
        "Per-Slot Strict Isolation",
        [
            "Slots: top, bottom, footwear, accessory",
            "Similarity floor (>= 0.35)",
            "Minimum item price ($2.00 floor)",
        ],
    )
    draw_arrow(1350, 710, 1350, 740)

    draw_card(
        1180,
        740,
        1520,
        820,
        "#1E293B",
        "#EC4899",
        "Demographic & Budget Constraints",
        [
            "100% Outfit Gender Coherence",
            "100% Outfit Age Coherence (no kids mix)",
            "Strict Total Budget Compliance",
        ],
    )
    draw_arrow(1350, 820, 1350, 850)

    draw_card(
        1180,
        850,
        1520,
        930,
        "#1E293B",
        "#6366F1",
        "Outfit Compatibility Scoring",
        [
            "Occasion & season agreement bonus",
            "Style clashing penalty",
            "Pairwise vector embedding cohesion",
        ],
    )
    draw_arrow(1350, 930, 1350, 960)

    draw_card(
        1180,
        960,
        1520,
        1045,
        "#1E293B",
        "#38BDF8",
        "Template Optimization & Fallback",
        [
            "Template 1: top + bottom + footwear + acc",
            "Template 2: full_body + footwear + acc",
            "Ordered fallback: accessory -> footwear",
        ],
    )
    draw_arrow(1350, 1045, 1350, 1220)

    draw_card(
        1180,
        1220,
        1520,
        1315,
        "#064E3B",
        "#10B981",
        "Outfit Response (/search)",
        [
            "OutfitPayload (items, total_price)",
            "complete flag & missing_slots",
            "Deterministic explanations per slot",
        ],
    )

    # Save diagram
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    print(f"Saved architecture diagram to {output_path}")


if __name__ == "__main__":
    create_diagram(Path("docs/architecture.png"))
