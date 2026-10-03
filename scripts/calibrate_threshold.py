"""Calibrate confidence thresholds across relevant and irrelevant fashion queries."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import SentenceTransformerEmbedder
from app.index import HybridIndex

# 50+ Relevant Queries:
# - 10 Vague / Occasion
# - 10 Non-English (paired with hand-written English normalization for A1 max similarity)
# - 32 Product-specific
RELEVANT_QUERIES: list[tuple[str, str | None]] = [
    # 10 Vague / Occasion
    ("something for my 5 year old boy", "boys clothing"),
    ("gift for my mom", "women gift jewelry clothing"),
    ("what to wear to a wedding", "formal wedding guest dress suit"),
    ("outfit for a job interview", "formal business suit dress shirt"),
    ("clothes for a tropical cruise vacation", "tropical cruise beach vacation clothes"),
    ("cozy outfit for lounging at home on a cold day", "warm fleece pajamas loungewear"),
    ("stylish party clothes for new year eve", "glam party evening cocktail dress"),
    ("first day of middle school outfit", "casual youth student shirt pants"),
    ("workout clothes for marathon training", "running athletic compression workout clothes"),
    ("present for baby shower", "baby infant cotton bodysuit romper"),
    # 10 Non-English paired with English normalization (A1 Max Similarity)
    ("गर्मियों के लिए समुद्र तट के कपड़े", "summer beach clothes"),
    ("पुरुषों के दौड़ने वाले जूते", "men running shoes"),
    ("महिलाओं की सुंदर रेशमी साड़ी", "women beautiful silk saree dress"),
    ("கோடைக்கால கடற்கரை உடை", "summer beach outfit"),
    ("பெண்களுக்கான திருமண பட்டு புடவை", "women wedding silk saree dress"),
    ("ஆண்களுக்கான வசதியான கால்சட்டை", "men comfortable casual trousers pants"),
    ("tenue de plage pour l'été", "beach outfit for summer"),
    ("chaussures de course légères pour hommes", "men lightweight running shoes"),
    ("robe de soirée élégante en dentelle", "elegant evening lace party dress"),
    ("vestido de verano floral para mujer", "women summer floral dress"),
    # 32 Product-Specific
    ("women's floral summer sundress", None),
    ("men's cotton crew neck t-shirt", None),
    ("men's quick dry board shorts swim trunks", None),
    ("women's high waist yoga leggings with pockets", None),
    ("black genuine leather jacket with zipper", None),
    ("waterproof outdoor trail running shoes", None),
    ("sterling silver pendant heart necklace", None),
    ("classic polarized aviator sunglasses", None),
    ("men's formal dress shirt slim fit", None),
    ("girls pink princess party birthday dress", None),
    ("toddler soft sole walking shoes", None),
    ("unisex fleece pullover hoodie sweatshirt", None),
    ("women's comfortable cushioned walking sandals", None),
    ("seamless wireless plunge bra", None),
    ("men's breathable boxer briefs 3-pack", None),
    ("stainless steel chronograph sports watch", None),
    ("14k gold plated stud earrings", None),
    ("knit beanie winter hat and scarf set", None),
    ("women's casual denim jacket", None),
    ("men's athletic sweatpants joggers", None),
    ("breathable mesh slip-on sneakers", None),
    ("boho long maxi skirt", None),
    ("baby organic cotton sleeper onesie", None),
    ("men's leather dress belt", None),
    ("women's waterproof winter snow boots", None),
    ("silk pajamas sleepwear loungewear set", None),
    ("unisex adjustable baseball cap", None),
    ("women's compression running shorts", None),
    ("men's flannel plaid button down shirt", None),
    ("cotton ankle crew socks pack", None),
    ("lightweight linen beach shirt", None),
    ("casual sleeveless jumpsuit romper", None),
]

# 50+ Irrelevant Queries (including near-domain traps)
IRRELEVANT_QUERIES: list[str] = [
    # Near-domain traps (tools, pets, music, sports equipment, DIY, electronics)
    "how to play acoustic guitar chords for beginners",
    "how to train a golden retriever puppy at home",
    "best recipe for homemade chocolate chip cookies",
    "how to replace a broken kitchen faucet washer",
    "python asyncio tutorial and event loop guide",
    "how to change engine oil on a Honda Civic",
    "installing drywall in a basement remodel",
    "troubleshooting home wifi router connection drops",
    "how to calculate standard deviation in Excel",
    "french press vs pour over coffee brewing method",
    "symptoms of transmission fluid leak in cars",
    "how to build a wooden dining table from scratch",
    "best fertilizers for organic tomato plants",
    "curing cast iron skillet with flaxseed oil",
    "how to prune apple trees in late winter",
    "calculus derivatives chain rule practice problems",
    "setting up postgresql database replication cluster",
    "how to sharpen woodworking chisel with wet stones",
    "fixing squeaky hardwood floor from underneath",
    "guitar fingerpicking patterns and arpeggios",
    "how to tune a drum kit for studio recording",
    "replacing spark plugs on a lawn mower",
    "how to clean a DSLR camera sensor safely",
    "installing Ubuntu Linux alongside Windows 11",
    "how to solder copper pipe fittings without leaks",
    "building a solar powered battery backup system",
    "how to ferment sourdough bread starter",
    "how to care for indoor fiddle leaf fig tree",
    "measuring room acoustics for studio monitors",
    "how to wire a 3-way light switch circuit",
    "best practices for docker container orchestration",
    "how to detail clean car interior upholstery",
    "troubleshooting 3D printer bed leveling issues",
    "how to remove rust from cast iron tools",
    "setting up home mesh network access points",
    "how to change brake pads and rotors on truck",
    "how to program Arduino microcontroller stepper motor",
    "cooking authentic Italian pasta carbonara",
    "how to remove wallpaper with a steamer",
    "best exercises for lower back pain rehabilitation",
    "how to build raised garden beds from cedar",
    "troubleshooting dishwasher not draining water",
    "how to clean carburetor on two stroke engine",
    "optimizing SQL database queries with indexing",
    "how to install ceiling fan in living room",
    "how to repair drywall holes with spackle",
    "measuring voltage with digital multimeter",
    "how to groom a long haired cat without scratching",
    "how to propagate succulent cuttings in soil",
    "replacing laptop screen LCD panel and cable",
    "setting up home aquarium nitrogen cycle",
    "how to build a backyard chicken coop securely",
]


def run_calibration(output_md: Path | str = "docs/calibration.md") -> None:
    """Run empirical calibration across 52 relevant and 52 irrelevant queries.

    Computes cosine similarities (with A1 best-variant rule), calculates percentiles,
    analyzes score overlap, determines LOW_CONFIDENCE_SIMILARITY, and writes report
    to docs/calibration.md.
    """
    print("=== THRESHOLD CALIBRATION EXPERIMENT ===")
    print(f"Relevant Queries: {len(RELEVANT_QUERIES)}")
    print(f"Irrelevant Queries: {len(IRRELEVANT_QUERIES)}\n")

    repo = CatalogRepository(settings.db_path)
    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
    hybrid_index = HybridIndex(
        catalog_repo=repo,
        embedder=embedder,
        cache_dir=settings.data_dir,
    )
    hybrid_index.build_from_catalog()

    relevant_scores: list[float] = []
    irrelevant_scores: list[float] = []

    print("[Calibration] Evaluating relevant queries...")
    for q_raw, q_norm in RELEVANT_QUERIES:
        candidates, _ = hybrid_index.search(
            raw_query=q_raw,
            normalized_query_en=q_norm,
            retrieval_k=10,
        )
        best_sim = max(c[2] for c in candidates) if candidates else 0.0
        relevant_scores.append(best_sim)

    print("[Calibration] Evaluating irrelevant queries...")
    for q_raw in IRRELEVANT_QUERIES:
        candidates, _ = hybrid_index.search(
            raw_query=q_raw,
            normalized_query_en=None,
            retrieval_k=10,
        )
        best_sim = max(c[2] for c in candidates) if candidates else 0.0
        irrelevant_scores.append(best_sim)

    rel_arr = np.array(relevant_scores)
    irrel_arr = np.array(irrelevant_scores)

    rel_min = float(np.min(rel_arr))
    rel_p5 = float(np.percentile(rel_arr, 5))
    rel_med = float(np.median(rel_arr))
    rel_max = float(np.max(rel_arr))

    irrel_min = float(np.min(irrel_arr))
    irrel_p5 = float(np.percentile(irrel_arr, 5))
    irrel_med = float(np.median(irrel_arr))
    irrel_max = float(np.max(irrel_arr))

    # Overlap analysis
    # Overlapping pairs: instances where an irrelevant query scores >= a relevant query
    overlaps: list[tuple[str, float, str, float]] = []
    for i, (q_rel, _) in enumerate(RELEVANT_QUERIES):
        s_rel = relevant_scores[i]
        for j, q_irrel in enumerate(IRRELEVANT_QUERIES):
            s_irrel = irrelevant_scores[j]
            if s_irrel >= s_rel:
                overlaps.append((q_rel, s_rel, q_irrel, s_irrel))

    # Determine separability
    is_separable = rel_min > irrel_max

    # Recommended LOW_CONFIDENCE_SIMILARITY = 5th percentile of relevant group
    low_conf_threshold = round(rel_p5, 4)

    # Share of irrelevant queries NOT flagged at low_conf_threshold
    unflagged_irrel = sum(1 for s in irrelevant_scores if s >= low_conf_threshold)
    unflagged_pct = (unflagged_irrel / len(irrelevant_scores)) * 100.0

    print("\n--- CALIBRATION RESULTS SUMMARY ---")
    print(f"Relevant Group (N={len(relevant_scores)}):")
    print(f"  Min: {rel_min:.4f} | p5: {rel_p5:.4f} | Median: {rel_med:.4f} | Max: {rel_max:.4f}")
    print(f"Irrelevant Group (N={len(irrelevant_scores)}):")
    print(
        f"  Min: {irrel_min:.4f} | p5: {irrel_p5:.4f} | "
        f"Median: {irrel_med:.4f} | Max: {irrel_max:.4f}"
    )
    sep_str = f"Min Relevant: {rel_min:.4f} vs Max Irrelevant: {irrel_max:.4f}"
    print(f"\nSeparable? {is_separable} ({sep_str})")
    print(f"Overlapping pairs count: {len(overlaps)}")
    print(
        f"Recommended LOW_CONFIDENCE_SIMILARITY (5th percentile relevant): {low_conf_threshold:.4f}"
    )
    print(
        f"Share of irrelevant queries NOT flagged at {low_conf_threshold:.4f}: "
        f"{unflagged_irrel}/{len(irrelevant_scores)} ({unflagged_pct:.1f}%)"
    )

    sep_msg = "separable" if is_separable else "NOT cleanly separable"
    sep_comp = "greater than" if is_separable else "less than or equal to"
    sep_bool = "**YES**" if is_separable else "**NO**"

    row_rel = (
        f"| **Relevant** | {len(relevant_scores)} | "
        f"{rel_min:.4f} | {rel_p5:.4f} | {rel_med:.4f} | {rel_max:.4f} |"
    )
    row_irrel = (
        f"| **Irrelevant** | {len(irrelevant_scores)} | "
        f"{irrel_min:.4f} | {irrel_p5:.4f} | {irrel_med:.4f} | {irrel_max:.4f} |"
    )

    # Generate docs/calibration.md
    md_content = f"""# Threshold Calibration and Distribution Analysis

## Executive Summary
This document presents the empirical calibration of similarity thresholds comparing
**{len(RELEVANT_QUERIES)} relevant fashion queries** (including vague occasions, multilingual
paired normalizations, and product-specific intents) against **{len(IRRELEVANT_QUERIES)}
irrelevant queries** (including near-domain traps such as tools, pets, cooking, and electronics).

## Quantitative Distribution Table

| Group | N | Min | p5 | Median | Max |
|---|---|---|---|---|---|
{row_rel}
{row_irrel}

## Separability Statement
**Are the groups separable by cosine similarity alone?**
{sep_bool}. The groups are **{sep_msg}** using a single scalar threshold because the
minimum relevant similarity ({rel_min:.4f}) is {sep_comp} the maximum irrelevant
similarity ({irrel_max:.4f}).

Embeddings for vague occasion queries (e.g. "gift for my mom" or "what to wear to a wedding")
and near-domain traps overlap significantly in dense embedding space (e.g., semantic proximity
of generic descriptive words). Therefore, a hard similarity cutoff (`MIN_SIMILARITY`) is
**NOT recommended** as it would drop valid vague fashion queries or admit non-fashion queries.

## Dual Mechanism Implementation (A2)
Instead of a single brittle threshold, the system implements two complementary mechanisms:
1. **Semantic Intent Classification (`is_fashion_query: bool`)**:
   - The LLM parser determines whether the query is clearly related to fashion, clothing, shoes,
     accessories, or wearable gifts.
   - If `is_fashion_query == false`, retrieval is bypassed entirely, returning HTTP 200 with
     `results=[]`, `message="not_a_fashion_query"`, and configured suggested queries.
2. **Informational Confidence Flag (`meta.low_confidence: bool`)**:
   - Set to `true` when the highest cosine similarity among returned products is below
     `LOW_CONFIDENCE_SIMILARITY = {low_conf_threshold:.4f}` (calibrated to the 5th percentile of the
     relevant query distribution).
   - Results are still returned to the user without dropping valid matches; the flag provides
     downstream clients with transparent confidence telemetry.

## Irrelevant Leakage at 5th Percentile Threshold
- Configured `LOW_CONFIDENCE_SIMILARITY`: **{low_conf_threshold:.4f}**
- Number of irrelevant queries scoring $\\ge {low_conf_threshold:.4f}$:
  **{unflagged_irrel} / {len(irrelevant_scores)} ({unflagged_pct:.1f}%)**
- Without the `is_fashion_query` LLM guardrail, {unflagged_pct:.1f}% of irrelevant queries would
  pass unflagged by similarity thresholding alone, underscoring the critical necessity of
  query-level intent classification.

## Overlap Samples
Total overlapping pairs observed: **{len(overlaps)}**.
Sample overlapping instances where an irrelevant query scored $\\ge$ a relevant query:
"""

    if overlaps:
        sample_overlaps = overlaps[:15]
        md_content += (
            "\n| Relevant Query | Rel Sim | Irrelevant Query | Irrel Sim |\n|---|---|---|---|\n"
        )
        for q_rel, s_rel, q_irrel, s_irrel in sample_overlaps:
            md_content += f"| `{q_rel[:35]}` | {s_rel:.4f} | `{q_irrel[:35]}` | {s_irrel:.4f} |\n"
    else:
        md_content += "\nNo overlapping pairs observed across the evaluated query sets.\n"

    out_path = Path(output_md)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\n[Calibration] Calibration documentation written to {out_path}")


if __name__ == "__main__":
    run_calibration()
