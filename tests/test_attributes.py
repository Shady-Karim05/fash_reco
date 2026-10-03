"""Unit tests for attribute derivation rules."""

import pytest

from app.attributes import (
    compute_quality_score,
    derive_age_group,
    derive_colors,
    derive_gender,
    derive_occasions,
    derive_seasons,
    derive_slot,
)


class TestSlotDerivation:
    """Tests for slot keyword rules and precedence."""

    def test_mento_streamtail_resolves_to_footwear(self) -> None:
        """Required test: 'Mento Streamtail' with description resolves to footwear."""
        title = "Mento Streamtail"
        description = "Comfortable thong sandal designed for beach walking and summer."
        slot = derive_slot(title, features=[], description=description)
        assert slot == "footwear"

    def test_palazzo_lounge_pants_resolves_to_bottom(self) -> None:
        """Required test: 'Palazzo Lounge Wide Leg Pants' resolves to bottom."""
        title = "DouBCQ Women's Palazzo Lounge Wide Leg Casual Flowy Pants(Flower Mix Blue, XL)"
        slot = derive_slot(title)
        assert slot == "bottom"

    def test_trapeze_dress_resolves_to_full_body_and_kids(self) -> None:
        """Required test: 'Trapeze Dress ... 9-10 Years' resolves to full_body and kids."""
        title = (
            "Pastel by Vivienne Honey Vanilla Girls' Trapeze Dress with Elastic Straps for Kids "
            "(9-10 Years, Dark Floral Mint)"
        )
        slot = derive_slot(title)
        age = derive_age_group(title)
        assert slot == "full_body"
        assert age == "kids"

    def test_dress_shirt_resolves_to_top_not_full_body(self) -> None:
        """Required test: 'Dress Shirt' resolves to top, not full_body."""
        title = "Van Heusen Men's Dress Shirt Regular Fit Poplin Solid"
        slot = derive_slot(title)
        assert slot == "top"

    def test_compound_dress_names(self) -> None:
        """Verify dress pants, shoes, socks, belts, buckles, watches resolve correctly."""
        assert derive_slot("Kenneth Cole REACTION Men's Dress Pants") == "bottom"
        assert derive_slot("Calvin Klein Men's Dress Shoes Leather Loafer") == "footwear"
        assert derive_slot("Dockers Men's Dress Socks 4-Pack") == "accessory"
        assert derive_slot("Sportoli Men's Classic Stitched Uniform Dress Buckle") == "accessory"
        assert derive_slot("Tommy Hilfiger Men's Leather Dress Belt") == "accessory"
        assert derive_slot("Seiko Men's Automatic Dress Watch") == "accessory"

    def test_sleee_onesie_costume_resolves_to_full_body(self) -> None:
        """Regression test for A1: SLEEE animal onesie pajamas resolves to full_body."""
        title = "SLEEE Adult Animal Onesie Coaplay Costume Halloween Pajamas"
        features = ["Hand washed and laid flat to dry"]
        slot = derive_slot(title, features=features, description="")
        age = derive_age_group(title)
        assert slot == "full_body"
        assert age == "adult"

    def test_ski_snow_jacket_and_pants_set_resolves_to_full_body(self) -> None:
        """Verify ski/snow jacket and pants sets resolve to full_body."""
        set_title = "SKIING Women's Waterproof Ski Jacket Suit Jacket and Pants Set"
        assert derive_slot(set_title) == "full_body"
        assert derive_slot("Snow Jacket and Pants 2-Piece Suit") == "full_body"

    def test_top_keywords(self) -> None:
        """Verify top keywords added in Phase 3."""
        assert derive_slot("Hanes Men's Tagless Undershirt 3-Pack") == "top"
        assert derive_slot("Nike Fleece Pullover Sweatshirt") == "top"
        assert derive_slot("Columbia Puffer Outdoor Vest") == "top"
        assert derive_slot("Men's Waffle Knit Henley Shirt") == "top"
        assert derive_slot("Under Armour Men's Squad Woven 1/4 Zip") == "top"
        assert derive_slot("Fleece Quarter Zip Jacket") == "top"
        assert derive_slot("Silk Lace Trim Camisole Top") == "top"
        assert derive_slot("Women's Long Sleeve Bodysuit") == "top"

    def test_jewelry_and_accessory_keywords(self) -> None:
        """Verify jewelry and accessory keywords added in Phase 3."""
        assert derive_slot("Sterling Silver Beads Charm Bracelet") == "accessory"
        assert derive_slot("14k Gold Engagement Rings Set") == "accessory"
        assert derive_slot("Vintage Locket Pendant Necklace") == "accessory"
        assert derive_slot("Stainless Steel Cuban Link Chain") == "accessory"
        assert derive_slot("Cute Leather Keychain Ring") == "accessory"
        assert derive_slot("Crystal Flower Brooch Pin") == "accessory"
        assert derive_slot("Beach Boho Ankle Bracelet Anklet") == "accessory"
        assert derive_slot("Men's Tuxedo Cufflinks") == "accessory"
        assert derive_slot("Pearl Hair Clip Hairpins") == "accessory"
        assert derive_slot("Velvet Sports Headband") == "accessory"
        assert derive_slot("Costume Fashion Jewelry Set") == "accessory"
        assert derive_slot("Breathable Cotton Face Mask") == "accessory"

    def test_swim_trunks_resolves_to_bottom(self) -> None:
        """Verify swim trunks resolve to bottom."""
        title = "Kanu Surf Men's Havana Quick Dry Swim Trunks"
        assert derive_slot(title) == "bottom"

    def test_romper_and_jumpsuit_resolve_to_full_body(self) -> None:
        """Verify rompers and jumpsuits resolve to full_body."""
        assert derive_slot("Women's Casual Sleeveless Jumpsuit Romper") == "full_body"
        assert derive_slot("One-Piece Athletic Swimsuit") == "full_body"

    def test_accessories_resolve_correctly(self) -> None:
        """Verify accessory categories resolve to accessory."""
        assert derive_slot("Polarized Vintage Sunglasses") == "accessory"
        assert derive_slot("GlowGem Sterling Silver Heart Locket Necklace") == "accessory"
        assert derive_slot("Leather Casual Belt") == "accessory"
        assert derive_slot("Fleece Winter Beanie Hat") == "accessory"

    def test_unknown_slot_fallback(self) -> None:
        """Verify unclassifiable products resolve to unknown."""
        assert derive_slot("Random Item Without Clothing Clues") == "unknown"

    def test_a4_regression_cases_and_rules(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A4 required regression tests printing matching rule."""
        from app.attributes import SLOT_PATTERNS

        def find_matching_rule(title: str) -> tuple[str, str]:
            for slot_name, pattern in SLOT_PATTERNS:
                m = pattern.search(title)
                if m:
                    return slot_name, f"Pattern for '{slot_name}' matched word '{m.group(0)}'"
            return "unknown", "No pattern matched (unknown)"

        cases = [
            ("DKNY Pull On Ponte Pant (CHA Charcoal, L)", "bottom"),
            ("Time and Tru Grey Acid Wash High Rise Fitted Stretch Jeggings - Small", "bottom"),
            ("Women's Opaque High Waist Tights", "bottom"),
            ("Seamless High Rise Compression Leggings", "bottom"),
            ("Men's Athletic Fleece Jogger Pants", "bottom"),
            ("Greater Half Custom Joker Baseball Jersey Button Down (Small-4XL)", "top"),
            ("SEIKO Selection Solar Men's Athletic Chronograph SBPY147", "accessory"),
            ("Silk Jacquard Classic Necktie", "accessory"),
            ("Men's Formal Silk Neck Tie", "accessory"),
            ("Classic Silk Bow Tie", "accessory"),
            ("Adjustable Elastic Suspenders", "accessory"),
            ("Paisley Cotton Bandana", "accessory"),
            ("Anti-Fog Swimming Goggles", "accessory"),
            ("Durable Replacement Shoelaces", "accessory"),
            ("Crystal Bridal Tiara", "accessory"),
            ("Gold Royal Queen Crown", "accessory"),
            ("Embroidered Iron-On Patch", "accessory"),
            ("Enamel Suit Lapel Pin", "accessory"),
            ("Surgical Steel Body Piercing", "accessory"),
            ("Titanium Nose Bone Stud", "accessory"),
            ("Stainless Steel Barbell Ring", "accessory"),
            ("Holy Catholic Wood Rosary", "accessory"),
            ("Vintage Glass Bead Rosaries", "accessory"),
            ("Blue Light Blocking Reading Glasses", "accessory"),
            ("Retro Round Frame Glasses", "accessory"),
            ("Calvin Klein Women's Wireless Bra", "innerwear"),
            ("Seamless Lace Triangle Bralette", "innerwear"),
            ("Cotton Comfort Brief Panties", "innerwear"),
            ("Lace Trim Silk Panty", "innerwear"),
            ("Men's Stretch Cotton Briefs", "innerwear"),
            ("Comfort Flex Cotton Boxers 3-Pack", "innerwear"),
            ("Seamless Breathable Thermal Underwear", "innerwear"),
            ("Hanes Men's Tagless Undershirt 3-Pack", "top"),
        ]

        for title, expected_slot in cases:
            slot, rule_msg = find_matching_rule(title)
            print(f"[A4 Test] Title: '{title}' -> Derived: {slot} | Rule: {rule_msg}")
            assert slot == expected_slot, (
                f"Failed for '{title}': got '{slot}', expected '{expected_slot}'"
            )


class TestGenderDerivation:
    """Tests for gender classification rules."""

    def test_gender_from_department(self) -> None:
        """Details department takes precedence."""
        assert derive_gender({"Department": "womens"}, "Generic Item") == "women"
        assert derive_gender({"Department": "mens"}, "Generic Item") == "men"
        assert derive_gender({"Department": "boys"}, "Generic Item") == "men"
        assert derive_gender({"Department": "girls"}, "Generic Item") == "women"
        assert derive_gender({"Department": "unisex-adult"}, "Generic Item") == "unisex"

    def test_gender_from_title(self) -> None:
        """Title regex fallback works when department is absent."""
        assert derive_gender({}, "YUEDGE Men's Crew Socks") == "men"
        assert derive_gender(None, "Nemidor Women's Vintage Swing Dress") == "women"
        assert derive_gender({}, "Unisex Pullover Hoodie") == "unisex"
        assert derive_gender({}, "Men's and Women's Running Shoes") == "unisex"
        assert derive_gender({}, "Unbranded Item No Target") == "unknown"

    def test_a4_boys_girls_unisex_regression(self) -> None:
        """Regression test for A4: title containing both boys and girls is unisex."""
        title = (
            "Cartoon Cute Baseball Caps Outdoor Hip Hop Hats with Devil Horns "
            "Adjistable Cotton Sun Caps for Boys Girls"
        )
        gender = derive_gender({}, title)
        print(f"[A4 Gender Test] Title: '{title}' -> Derived: {gender}")
        assert gender == "unisex"


class TestAgeGroupDerivation:
    """Tests for adult vs kids age group classification."""

    def test_kids_patterns(self) -> None:
        """Verify youth, toddler, and year patterns trigger kids."""
        assert derive_age_group("Girls' Summer Sundress") == "kids"
        assert derive_age_group("Boys' Athletic Shorts") == "kids"
        assert derive_age_group("Toddler Walking Shoes") == "kids"
        assert derive_age_group("Baby Infant Cotton Romper") == "kids"
        assert derive_age_group("Kids Party Dress 7-8 Years") == "kids"

    def test_wondertify_false_positive_resolves_to_adult(self) -> None:
        """Regression test for A2: WONDERTIFY earrings with 'For Women Girls' resolves to adult."""
        title = (
            "WONDERTIFY Paisley Floral Leather Earring Ethnic Flourish Flower Leaf Teardrop "
            "Double-Sided Dangle Earrings Lightweight Leaf Earrings For Women Girls Colorful"
        )
        assert derive_age_group(title) == "adult"

    def test_adult_default(self) -> None:
        """Adult is default for standard clothing."""
        assert derive_age_group("Men's Athletic Crew Socks") == "adult"
        assert derive_age_group("Women's Palazzo Lounge Wide Leg Pants") == "adult"


class TestColorDerivation:
    """Tests for color extraction against fixed vocabulary."""

    def test_extract_colors_from_parentheses_and_title(self) -> None:
        """Verify extraction from parenthesized expressions and title text."""
        colors1 = derive_colors("Flowy Pants(Flower Mix Blue, XL)")
        assert "blue" in colors1
        assert "floral" in colors1

        colors2 = derive_colors("Men's Moisture Control Socks (Blue, Size 9-12)")
        assert colors2 == ["blue"]

        colors3 = derive_colors("Classic Red and Black Plaid Shirt")
        assert "black" in colors3
        assert "red" in colors3


class TestSeasonsAndOccasions:
    """Tests for seasons and occasions keyword extraction."""

    def test_seasons_keywords(self) -> None:
        """Verify summer and winter keywords match appropriately."""
        summer_seasons = derive_seasons("lightweight beach sandal for summer vacation")
        assert "summer" in summer_seasons

        winter_seasons = derive_seasons("thermal insulated fleece parka jacket for winter")
        assert "winter" in winter_seasons

    def test_occasions_keywords(self) -> None:
        """Verify beach, workout, and formal occasions."""
        assert "beach" in derive_occasions("thong flip flop sandal for beach")
        assert "workout" in derive_occasions("compression running yoga athletic leggings")
        assert "formal" in derive_occasions("classic business dress shirt for formal events")


class TestBayesianRating:
    """Tests for Bayesian quality score calculation."""

    def test_high_volume_moderate_rating_beats_single_low_rating(self) -> None:
        """Required test: A 2.0 rating from 1 reviewer must not outrank a 4.3 from thousands."""
        score_single_low = compute_quality_score(average_rating=2.0, rating_number=1)
        score_high_vol = compute_quality_score(average_rating=4.3, rating_number=2000)

        assert score_high_vol > score_single_low

    def test_single_perfect_rating_pulled_toward_mean(self) -> None:
        """A single 5.0 rating should be pulled heavily toward the prior mean."""
        global_mean = 4.2
        m = 10.0
        score = compute_quality_score(5.0, 1, global_mean=global_mean, m=m)
        expected = (1 / 11.0) * 5.0 + (10 / 11.0) * 4.2
        assert abs(score - expected) < 0.001

    def test_zero_or_null_ratings_return_global_mean(self) -> None:
        """Null or zero count ratings return global mean baseline."""
        assert compute_quality_score(None, None) == 4.2
        assert compute_quality_score(4.5, 0) == 4.2


class TestPhase5AttributesA1dA2A3A4:
    """Comprehensive tests for Part A fixes A1(d), A2, A3, and A4."""

    # A1(d) regression tests
    def test_a1d_humaira_pendant_resolves_to_accessory(self) -> None:
        title = "Humaira Nautical Brass Sand Timer Pendant Necklace Sand Watch (Silver and Yellow)"
        assert derive_slot(title) == "accessory"

    def test_a1d_american_trends_shorts_resolves_to_bottom(self) -> None:
        title = "American Trends Men's Workout Shorts Athletic Gym Running Shorts"
        assert derive_slot(title) == "bottom"

    def test_a1d_armory_replicas_cloak_pin_resolves_to_accessory(self) -> None:
        title = "Armory Replicas Medieval Dress Cloak Pin Brooch"
        assert derive_slot(title) == "accessory"

    def test_a1d_apple_watch_band_resolves_to_adult(self) -> None:
        title = "Compatible with Apple Watch Band (Small Version) Volleyball Boy Sports"
        assert derive_age_group(title) == "adult"

    # A2 Parametrized Slot Tests
    @pytest.mark.parametrize(
        ("title", "expected_slot"),
        [
            ("Calvin Klein Womens Roll Cuff Short (Pacific, 12)", "bottom"),
            ("Wilson Compression Short with Cup Pocket - Adult, Large", "bottom"),
            (
                "Becca by Rebecca Virtue Women's Color Code Tab Side Hipster Bikini Bottom Sea M",
                "bottom",
            ),
            (
                "Saxon. Children's Starter Pull-On Jods Breech, Equestrian Schooling | Navy 16",
                "bottom",
            ),
        ],
    )
    def test_a2_bottom_slot_cases(self, title: str, expected_slot: str) -> None:
        slot = derive_slot(title)
        assert slot == expected_slot

    def test_a2_saxon_jods_age_group_is_kids(self) -> None:
        title = "Saxon. Children's Starter Pull-On Jods Breech, Equestrian Schooling | Navy 16"
        assert derive_age_group(title) == "kids"

    def test_a2_singular_short_does_not_match_short_sleeve(self) -> None:
        assert derive_slot("Hanes Men's Short Sleeve Graphic T-Shirt") == "top"
        assert derive_slot("Nike Women's Short-Sleeve Running Top") == "top"

    @pytest.mark.parametrize(
        ("title", "expected_slot"),
        [
            ("Flexees by Maidenform Ultra Firm Hi-Waist Brief Shapewear, 83061", "innerwear"),
            ("Hung HGE015 Big Boy Jock White", "innerwear"),
            ("Women's Seamless Lace Thong 3-Pack", "innerwear"),
            ("Mento Streamtail Thong Sandal Beach Flip Flop", "footwear"),
        ],
    )
    def test_a2_innerwear_vs_footwear_thong(self, title: str, expected_slot: str) -> None:
        slot = derive_slot(title)
        assert slot == expected_slot

    @pytest.mark.parametrize(
        ("title", "expected_slot"),
        [
            (
                "Limited Too Cute Girls Christmas Holiday Fashion Crossbody Small Purse (Tree)",
                "accessory",
            ),
            (
                "Michael Kors Fulton Large Flat Multi Function Leather Phone Case (Black)",
                "accessory",
            ),
            (
                "Aristar By Charmant Eyeglasses AR6724 AR/6724 073 Light Brown Optical Frame 52mm",
                "accessory",
            ),
            ("Vogue VO 3963 Women's Eyeglasses Matte Brushed Blue 53", "accessory"),
            ("US Air Force Wings Lanyard (Licensed by USAF)", "accessory"),
            ("Official Our Lady of Mount Carmel Brown Scapular - 100% Wool! (1-Pack)", "accessory"),
            (
                "Anodized Black Sugical Steel Double Flare Tunnles Plugs Earlets "
                "11/16 Inch 18mm 1 Pair",
                "accessory",
            ),
            ("NEONBLOND Pin US Hiking Trails John Muir Trail - California", "accessory"),
        ],
    )
    def test_a2_accessory_slot_cases(self, title: str, expected_slot: str) -> None:
        slot = derive_slot(title)
        assert slot == expected_slot

    def test_a2_limited_too_is_kids(self) -> None:
        title = "Limited Too Cute Girls Christmas Holiday Fashion Crossbody Small Purse (Tree)"
        assert derive_age_group(title) == "kids"

    def test_a2_bare_pin_lowest_priority_accessory_rule(self) -> None:
        # A title with a higher priority keyword like dress, shirt, pants
        assert derive_slot("Safety Pin Graphic Print Cotton T-Shirt") == "top"
        assert derive_slot("Pin Stripe Formal Dress Shirt") == "top"
        assert derive_slot("US Flag Lapel Pin") == "accessory"

    @pytest.mark.parametrize(
        ("title", "expected_slot"),
        [
            ("Carter's Baby Boy's 2-Piece Fireman Snug Fit Cotton PJs 12 Months", "full_body"),
            ("Nike Baby Boys Just Do It Coverall - Black (6 Months)", "full_body"),
        ],
    )
    def test_a2_full_body_cases(self, title: str, expected_slot: str) -> None:
        assert derive_slot(title) == expected_slot

    @pytest.mark.parametrize(
        ("title", "expected_slot"),
        [
            ("Blundstone Men's Metatarsal Guard Gumboot,Grey Waterproof,AU 8 M", "footwear"),
            (
                "Hazel's Star Fashion Flip Flip with Extra Padded Soft Insole, Black, "
                "Size 11 (M) US",
                "footwear",
            ),
        ],
    )
    def test_a2_footwear_cases(self, title: str, expected_slot: str) -> None:
        assert derive_slot(title) == expected_slot

    # A3 Non-fashion keyword tests
    @pytest.mark.parametrize(
        "title",
        [
            "Kiwi Heavy Duty Waterproofing Spray 12 oz",
            "Kiwi Black Shoe Polish 1.125 oz Tin",
            "Sally Hansen Hard as Nails Nail Polish Red",
            "Head & Shoulders Daily Shampoo 400ml",
            "Vaseline Intensive Care Body Lotion 20 oz",
            "Chanel No. 5 Luxury Perfume 50ml",
            "Pheromone Cologne for Men Attract Women",
            "Armani Acqua Di Gio Men's Cologne 100ml",
            "Suavecito Pomade Firme Hold Hair Wax",
        ],
    )
    def test_a3_non_fashion_keywords_rejected(self, title: str) -> None:
        from app.pipeline import validate_raw_record

        is_valid, reason = validate_raw_record({"title": title, "price": 19.99})
        assert not is_valid
        assert reason == "non_fashion_keyword"

    def test_a3_polish_eagle_tshirt_kept(self) -> None:
        from app.pipeline import validate_raw_record

        title = "Polish Eagle Graphic T-Shirt Cotton Vintage"
        is_valid, reason = validate_raw_record({"title": title, "price": 19.99})
        assert is_valid
        assert reason is None

    # A4 Accessory type derivation tests
    @pytest.mark.parametrize(
        ("title", "slot", "expected_type"),
        [
            ("Oakley Polarized Sunglasses", "accessory", "eyewear"),
            ("Vogue Women's Eyeglasses Frame", "accessory", "eyewear"),
            ("Michael Kors Leather Crossbody Purse Bag", "accessory", "bag"),
            ("Nike Backpack Daypack", "accessory", "bag"),
            ("Double Flared Saddle Plugs Body Tunnels 18mm", "accessory", "body_jewelry"),
            ("Nose Bone Stud Piercing Barbell", "accessory", "body_jewelry"),
            ("Seiko Automatic Analog Watch", "accessory", "watch"),
            ("Wool Beanie Knit Winter Hat", "accessory", "hat"),
            ("Silk Patterned Neck Scarf", "accessory", "scarf"),
            ("Tommy Hilfiger Leather Belt", "accessory", "belt"),
            ("Gold Hoop Dangle Earrings Jewelry", "accessory", "jewelry"),
            ("Satin Headband Hairpins", "accessory", "hair"),
            ("Compression Ankle Running Socks", "accessory", "socks"),
            ("Winter Thermal Knit Gloves", "accessory", "gloves"),
            ("Military Lanyard Keychain", "accessory", "other"),
            ("Cotton Crew T-Shirt", "top", None),  # non-accessory gets None
        ],
    )
    def test_a4_derive_accessory_type(
        self, title: str, slot: str, expected_type: str | None
    ) -> None:
        from app.attributes import derive_accessory_type

        acc_type = derive_accessory_type(title, slot)
        assert acc_type == expected_type
