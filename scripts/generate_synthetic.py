"""Generate synthetic Amazon Fashion products adhering to the dataset schema."""

import json
import random
from pathlib import Path

TITLES_BY_SLOT: dict[str, list[tuple[str, str, str]]] = {
    "footwear": [
        (
            "Comfort Walk Men's Breathable Leather Loafers Slip-On Driving Shoes",
            "Men's",
            "Genuine leather loafers with cushioned insole for everyday walking comfort.",
        ),
        (
            "SunnyBreeze Women's Bohemian Beach Thong Sandals with Ankle Strap",
            "Women's",
            "Lightweight summer thong sandals perfect for beach vacations and casual wear.",
        ),
        (
            "ProRunner Unisex Lightweight Breathable Running Shoes Athletic Sneakers",
            "Unisex-Adult",
            "Shock absorbing athletic running sneakers with mesh upper and durable outsole.",
        ),
        (
            "WinterWarm Men's Waterproof Insulated Snow Boots Fleece Lined",
            "Men's",
            "Heavy-duty winter snow boots with anti-skid rubber sole and warm thermal lining.",
        ),
        (
            "KidsStep Boys & Girls Toddler Canvas Sneakers Lightweight Walking Shoes",
            "Kids",
            "Easy slip-on toddler canvas sneakers with flexible non-slip rubber soles.",
        ),
    ],
    "full_body": [
        (
            "FloralCharm Women's Summer Bohemian Spaghetti Strap Trapeze Maxi Dress",
            "Women's",
            "Flowy floral beach dress featuring breathable fabric and adjustable straps.",
        ),
        (
            "PrincessGlow Girls' Party Princess Lace Trapeze Dress (4-5 Years)",
            "Girls",
            "Elegant party dress for young girls with delicate lace trim and ribbon bow.",
        ),
        (
            "OceanSplash Women's One-Piece Ruched Tummy Control Swimsuit Bathing Suit",
            "Women's",
            "Flattering one-piece swimsuit designed for pool parties and beach holidays.",
        ),
        (
            "ChicStyle Women's Elegant Wide-Leg Sleeveless Jumpsuit Romper with Belt",
            "Women's",
            "Versatile formal evening jumpsuit suitable for cocktail parties and weddings.",
        ),
    ],
    "bottom": [
        (
            "Coastline Men's Quick Dry Summer Beach Board Shorts Swim Trunks with Pockets",
            "Men's",
            "Breathable swim trunks with mesh lining and adjustable drawstring waistband.",
        ),
        (
            "DouBCQ Women's Palazzo Lounge Wide Leg Casual Flowy Pants (Navy, XL)",
            "Women's",
            "Soft and lightweight palazzo pants featuring high elastic waist and relaxed fit.",
        ),
        (
            "UrbanDenim Men's Slim Fit Stretch Casual Denim Jeans Pants",
            "Men's",
            "Classic five-pocket slim fit stretch jeans built for everyday durability.",
        ),
        (
            "ZenFlex Women's High Waisted Yoga Pants with Pockets Workout Leggings",
            "Women's",
            "Non see-through 4-way stretch athletic leggings for yoga, running, and fitness.",
        ),
    ],
    "top": [
        (
            "ClassicFit Men's Long Sleeve Button Down Wrinkle-Free Dress Shirt",
            "Men's",
            "Crisp cotton blend dress shirt designed for business formal and office work.",
        ),
        (
            "SoftBreeze Women's Casual Lightweight V-Neck Summer Short Sleeve T-Shirt",
            "Women's",
            "Everyday basic tee made with ultra-soft combed cotton and flattering drape.",
        ),
        (
            "AlpineGear Unisex Heavyweight Fleece Pullover Hoodie Sweatshirt",
            "Unisex-Adult",
            "Cozy thermal winter hoodie featuring kangaroo pocket and ribbed cuffs.",
        ),
        (
            "ActiveDry Men's Athletic Moisture Wicking Performance Workout Tank Top",
            "Men's",
            "Quick-drying workout tank top engineered for gym, running, and training.",
        ),
    ],
    "accessory": [
        (
            "PolarShade Unisex Polarized UV400 Protection Classic Sunglasses",
            "Unisex-Adult",
            "Vintage retro sunglasses with anti-glare polarized lenses and sturdy hinges.",
        ),
        (
            "WinterFrost Women's Cable Knit Cashmere Scarf and Beanie Hat Set",
            "Women's",
            "Luxuriously warm winter scarf and slouchy beanie hat for cold weather.",
        ),
        (
            "GlowGem Vintage Heart Shaped Locket Pendant Necklace in Sterling Silver",
            "Women's",
            "Handcrafted photo locket pendant on fine chain, ideal gift for anniversaries.",
        ),
        (
            "ToughStrap Men's Genuine Full Grain Leather Casual Dress Belt",
            "Men's",
            "Durable single prong leather belt suitable for jeans and dress trousers.",
        ),
        (
            "RONNOX Women's 3-Pairs Bright Colored Calf Compression Tube Socks",
            "Women's",
            "Graduated compression socks designed for athletic recovery and long travel.",
        ),
    ],
}

STORES = [
    "GiveGift",
    "DouBCQ",
    "Pastel by Vivienne",
    "Mento",
    "RONNOX",
    "Nemidor",
    "PattyBoutik",
    "Hanes",
    "Gildan",
    "Under Armour",
    "Columbia",
]

COLORS = ["Black", "White", "Blue", "Red", "Green", "Pink", "Navy", "Floral", "Beige"]


def generate_synthetic_catalog(
    num_products: int = 500,
    output_path: Path | str = "data/synthetic_meta.jsonl",
    seed: int = 42,
) -> Path:
    """Generate synthetic fashion items adhering to Amazon Fashion schema.

    Args:
        num_products: Number of products to generate (~500).
        output_path: File destination for the JSONL dataset.
        seed: Random seed for deterministic generation.

    Returns:
        Path to generated JSONL file.
    """
    random.seed(seed)
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    slots = list(TITLES_BY_SLOT.keys())

    with open(out_file, "w", encoding="utf-8") as f:
        for i in range(num_products):
            slot = random.choice(slots)
            template, dept, desc = random.choice(TITLES_BY_SLOT[slot])
            store = random.choice(STORES)
            color = random.choice(COLORS)

            parent_asin = f"SYNTH_{slot[:3].upper()}_{i:04d}"
            title = f"{store} {template} ({color})"

            # ~15% unpriced to test ingestion drop rules
            price = None if random.random() < 0.15 else round(random.uniform(9.99, 129.99), 2)

            rating_count = random.choice([1, 2, 5, 25, 150, 850, 3200])
            avg_rating = round(random.uniform(2.5, 4.9), 1)

            features = [
                f"High quality materials from {store}",
                f"Designed for comfort and style in {color}",
                "Easy care and machine washable",
            ]

            images = [
                {
                    "variant": "MAIN",
                    "thumb": f"https://images.example.com/synth/{parent_asin}_thumb.jpg",
                    "large": f"https://images.example.com/synth/{parent_asin}_large.jpg",
                    "hi_res": f"https://images.example.com/synth/{parent_asin}_hires.jpg",
                }
            ]

            record = {
                "main_category": "AMAZON FASHION",
                "title": title,
                "average_rating": avg_rating,
                "rating_number": rating_count,
                "features": features,
                "description": [desc],
                "price": price,
                "images": images,
                "videos": [],
                "store": store,
                "categories": [],
                "details": {
                    "Department": dept,
                    "Package Dimensions": "10 x 8 x 2 inches; 12 Ounces",
                },
                "parent_asin": parent_asin,
                "bought_together": None,
            }
            f.write(json.dumps(record) + "\n")

    return out_file


if __name__ == "__main__":
    generated_path = generate_synthetic_catalog()
    print(f"Successfully generated 500 synthetic records at {generated_path}")
