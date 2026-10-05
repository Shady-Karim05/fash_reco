"""Deterministic offline multilingual query normalizer and lexicon engine.

Provides rule-based multilingual parsing and canonical English query derivation
for English, Spanish, French, Hindi, and Tamil without external API calls.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field


class MultilingualParseResult(BaseModel):
    """Result of deterministic multilingual query normalization."""

    detected_language: str = Field(
        default="en", description="Detected language code: en, es, fr, hi, ta."
    )
    normalized_query_en: str = Field(
        description="Canonical English search phrase for BM25 and dense retrieval."
    )
    gender: Literal["men", "women", "unisex"] | None = Field(default=None)
    age_group: Literal["adult", "kids"] = Field(default="adult")
    min_price: float | None = Field(default=None)
    max_price: float | None = Field(default=None)
    slots: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    season: str | None = Field(default=None)
    occasion: str | None = Field(default=None)
    brand: str | None = Field(default=None)
    is_fashion_query: bool = Field(default=True)
    is_confidently_parsed: bool = Field(default=False)
    warnings: list[str] = Field(default_factory=list)


def detect_language(query: str) -> str:
    """Detect language/script of query: 'ta', 'hi', 'fr', 'es', or 'en'."""
    # 1. Script-based detection
    if re.search(r"[\u0B80-\u0BFF]", query):
        return "ta"
    if re.search(r"[\u0900-\u097F]", query):
        return "hi"

    q_lower = query.lower()

    # 2. French characteristic markers
    french_markers = [
        r"\b(?:robe|chaussures?|manteau|ceinture|lunettes|foulard|débardeur|homme|hommes|femme|femmes|filles?|garçons?)\b",
        r"\b(?:d'été|d'hiver|à\s+moins\s+de|pour\s+les|en\s+cuir|en\s+soie)\b",
    ]
    for pat in french_markers:
        if re.search(pat, q_lower):
            return "fr"

    # 3. Spanish characteristic markers
    spanish_markers = [
        r"\b(?:vestido|zapatillas?|abrigo|cinturón|gafas|bufanda|camiseta|hombre|hombres|mujer|mujeres|niñas?|niños?)\b",
        r"\b(?:de\s+verano|de\s+invierno|por\s+menos\s+de|al\s+aire\s+libre|de\s+cuero|de\s+seda)\b",
    ]
    for pat in spanish_markers:
        if re.search(pat, q_lower):
            return "es"

    return "en"


# Slot patterns per language
# (slot_name, regex_pattern, canonical_en_term)
_SLOT_LEXICON: dict[str, list[tuple[str, str, str]]] = {
    "ta": [
        ("footwear", r"(?:காலணிகள்|காலணி|ஷூ|செருப்பு)", "shoes"),
        ("top", r"டேங்க்\s*டாப்", "tank top"),
        ("top", r"கோட்", "coat"),
        ("top", r"சட்டை", "shirt"),
        ("top", r"ஜாக்கெட்", "jacket"),
        ("top", r"ஸ்வெட்டர்", "sweater"),
        ("top", r"டாப்", "top"),
        ("full_body", r"(?:உடை|ஆடை|சூட்|கவுன்)", "dress"),
        ("bottom", r"(?:பேண்ட்|ஜீன்ஸ்|சார்ட்ஸ்|பாவாடை)", "pants"),
        ("accessory", r"(?:சன்கிளாஸ்கள்|சன்கிளாஸ்|கண்ணாடி)", "sunglasses"),
        ("accessory", r"தாவணி", "scarf"),
        ("accessory", r"பெல்ட்", "belt"),
        ("accessory", r"(?:குறுக்கு\s*பை|கைப்பை|பை)", "crossbody purse"),
        ("accessory", r"(?:வாட்ச்|கடிகாரம்|நகைகள்)", "accessory"),
    ],
    "hi": [
        ("footwear", r"(?:जूते|जूता|सैंडल|चप्पल)", "shoes"),
        ("accessory", r"(?:ड्रेस\s+बेल्ट|बेल्ट)", "dress belt"),
        ("accessory", r"(?:धूप\s*का\s*चश्मा|चश्मा)", "sunglasses"),
        ("accessory", r"स्कार्फ", "scarf"),
        ("accessory", r"(?:क्रॉसबॉडी\s*पर्स|पर्स|बैग)", "crossbody purse"),
        ("top", r"टैंक\s*टॉप", "tank top"),
        ("top", r"कोट", "coat"),
        ("top", r"टी-शर्ट", "t-shirt"),
        ("top", r"शर्ट", "shirt"),
        ("top", r"स्वेटर", "sweater"),
        ("top", r"जैकेट", "jacket"),
        ("top", r"टॉप", "top"),
        ("full_body", r"(?<!ड्रेस\s)(?:पोशाक|ड्रेस(?![\s\w]*बेल्ट)|गाउन)", "dress"),
        ("bottom", r"(?:पैंट|पतलून|जींस|शॉर्ट्स|स्कर्ट)", "pants"),
        ("accessory", r"(?:घड़ी|गहने)", "accessory"),
    ],
    "es": [
        (
            "footwear",
            r"\b(?:zapatillas?(?:\s+de\s+correr)?|zapatos?|botas?|sandalias?|calzado)\b",
            "shoes",
        ),
        ("accessory", r"\b(?:gafas(?:\s+de\s+sol)?)\b", "sunglasses"),
        ("accessory", r"\b(?:cinturón(?:\s+de\s+vestir)?|cinturones)\b", "dress belt"),
        ("accessory", r"\b(?:bufandas?)\b", "scarf"),
        ("accessory", r"\b(?:bolso(?:\s+bandolera)?|bolsas?|bandoleras?)\b", "crossbody purse"),
        ("top", r"\b(?:camisetas?(?:\s+sin\s+mangas))\b", "tank top"),
        ("top", r"\b(?:abrigos?)\b", "coat"),
        ("top", r"\b(?:camisas?|camisetas?|chaquetas?|jerséis|sudaderas?|blusas?|tops?)\b", "top"),
        ("full_body", r"\b(?:vestidos?|trajes?|monos?|conjunto)\b", "dress"),
        (
            "bottom",
            r"\b(?:pantalones?(?:\s+cortos)?|vaqueros|jeans|faldas?|shorts?|leggings?)\b",
            "pants",
        ),
        ("accessory", r"\b(?:relojes?|joyas?)\b", "accessory"),
    ],
    "fr": [
        ("footwear", r"\b(?:chaussures?(?:\s+de\s+course)?|baskets?|bottes?|sandales?)\b", "shoes"),
        ("accessory", r"\b(?:lunettes(?:\s+de\s+soleil)?)\b", "sunglasses"),
        ("accessory", r"\b(?:ceintures?(?:\s+habillée)?)\b", "dress belt"),
        ("accessory", r"\b(?:foulards?|écharpes?)\b", "scarf"),
        ("accessory", r"\b(?:sacs?(?:\s+à\s+bandoulière)?)\b", "crossbody purse"),
        ("top", r"\b(?:manteaux?|manteau)\b", "coat"),
        ("top", r"\b(?:débardeurs?)\b", "tank top"),
        ("top", r"\b(?:chemises?|t-shirts?|vestes?|pulls?|sweats?|blouses?|tops?)\b", "top"),
        ("full_body", r"\b(?:robes?|combinaisons?|costumes?|tenues?)\b", "dress"),
        ("bottom", r"\b(?:pantalons?|jeans?|jupes?|shorts?|leggings?)\b", "pants"),
        ("accessory", r"\b(?:montres?|bijoux)\b", "accessory"),
    ],
}

# Gender patterns per language
_GENDER_LEXICON: dict[str, list[tuple[str, str, str]]] = {
    # (gender_val, regex_pattern, en_label)
    "ta": [
        ("men", r"(?:ஆண்களுக்கான|ஆண்கள்|ஆண்)", "men"),
        ("women", r"(?:பெண்களுக்கான|பெண்கள்|பெண்)", "women"),
        ("kids", r"(?:சிறுமிகளுக்கான|சிறுமிகள்|சிறுவர்கள்|குழந்தைகள்)", "kids"),
    ],
    "hi": [
        ("men", r"(?:पुरुषों|पुरुष|मर्द)", "men"),
        ("women", r"(?:महिलाओं|महिला|औरत)", "women"),
        ("kids", r"(?:लड़कियों|लड़कों|बच्चों)", "kids"),
    ],
    "es": [
        ("men", r"\b(?:hombres?|caballeros?|para\s+hombre)\b", "men"),
        ("women", r"\b(?:mujeres?|damas?|para\s+mujer)\b", "women"),
        ("kids", r"\b(?:niñas?|niños?|chicos?|chicas?|infantil|bebés?)\b", "kids"),
    ],
    "fr": [
        ("men", r"\b(?:hommes?|pour\s+homme)\b", "men"),
        ("women", r"\b(?:femmes?|pour\s+femme|dames?)\b", "women"),
        ("kids", r"\b(?:filles?|garçons?|enfants?|bébés?)\b", "kids"),
    ],
}

# Concept terms to translate to English keywords
_CONCEPT_TERMS: dict[str, list[tuple[str, str]]] = {
    "ta": [
        (r"கடற்கரை", "beach"),
        (r"விடுமுறை(?:க்காக)?", "vacation"),
        (r"கோடைக்கால", "summer"),
        (r"குளிர்கால", "winter"),
        (r"ஓடும்", "running"),
        (r"உடற்பயிற்சி", "workout"),
        (r"ஜிம்", "gym"),
        (r"கருப்பு", "black"),
        (r"தோல்", "leather"),
        (r"நேர்த்தியான", "elegant"),
        (r"பட்டு", "silk"),
        (r"பழுப்பு", "brown"),
        (r"துருவப்படுத்தப்பட்ட", "polarized"),
        (r"வெளிப்புற", "outdoor"),
        (r"பயண(?:த்திற்கான)?", "travel"),
        (r"சூடான", "warm"),
    ],
    "hi": [
        (r"समुद्र\s*तट", "beach"),
        (r"छुट्टी", "vacation"),
        (r"गर्मियों", "summer"),
        (r"सर्दियों", "winter"),
        (r"दौड़ने", "running"),
        (r"वर्कआउट", "workout"),
        (r"जिम", "gym"),
        (r"काला|काले|काली", "black"),
        (r"चमड़े", "leather"),
        (r"सुंदर", "elegant"),
        (r"रेशमी", "silk"),
        (r"भूरी|भूरे", "brown"),
        (r"पोलराइज्ड", "polarized"),
        (r"आउटडोर", "outdoor"),
        (r"यात्रा", "travel"),
        (r"गर्म", "warm"),
    ],
    "es": [
        (r"\bverano\b", "summer"),
        (r"\bplaya\b", "beach"),
        (r"\bvacaciones\b", "vacation"),
        (r"\binvierno\b", "winter"),
        (r"\bcálido\b", "warm"),
        (r"\bcorrer\b", "running"),
        (r"\bgimnasio\b", "gym"),
        (r"\bnegr[oa]s?\b", "black"),
        (r"\bcuero\b", "leather"),
        (r"\belegante\b", "elegant"),
        (r"\bseda\b", "silk"),
        (r"\bmarrón\b", "brown"),
        (r"\bpolarizadas?\b", "polarized"),
        (r"\baire\s+libre\b", "outdoor"),
        (r"\bviajes?\b", "travel"),
        (r"\bcasual\b", "casual"),
    ],
    "fr": [
        (r"\bété\b", "summer"),
        (r"\bplage\b", "beach"),
        (r"\bvacances\b", "vacation"),
        (r"\bhiver\b", "winter"),
        (r"\bchaud\b", "warm"),
        (r"\bcourse\b", "running"),
        (r"\bsport\b", "sport"),
        (r"\bnoir[e]?s?\b", "black"),
        (r"\bcuir\b", "leather"),
        (r"\bélégant[e]?s?\b", "elegant"),
        (r"\bsoie\b", "silk"),
        (r"\bmarron\b", "brown"),
        (r"\bpolarisée?s?\b", "polarized"),
        (r"\bvoyages?\b", "travel"),
    ],
}


def _extract_price(query: str, lang: str) -> tuple[float | None, float | None]:
    """Extract price bounds from localized currency phrases."""
    q = query.lower()

    if lang == "ta":
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:டாலருக்கு|டாலர்)\s*(?:குறைவான|குறைவாக|உள்)?", q)
        if m:
            return None, float(m.group(1))

    elif lang == "hi":
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:डॉलर|डालर)\s*(?:से\s*कम|के\s*अंदर)?", q)
        if m:
            return None, float(m.group(1))

    elif lang == "es":
        m = re.search(r"(?:menos\s+de|por\s+menos\s+de|hasta)\s*(?:\$|usd)?\s*(\d+(?:\.\d+)?)", q)
        if m:
            return None, float(m.group(1))
        m2 = re.search(r"(\d+(?:\.\d+)?)\s*(?:dólares|dolares)", q)
        if m2:
            return None, float(m2.group(1))

    elif lang == "fr":
        m = re.search(r"(?:à\s+moins\s+de|moins\s+de|sous)\s*(?:\$|usd)?\s*(\d+(?:\.\d+)?)", q)
        if m:
            return None, float(m.group(1))
        m2 = re.search(r"(\d+(?:\.\d+)?)\s*dollars?", q)
        if m2:
            return None, float(m2.group(1))

    return None, None


def normalize_multilingual_query(raw_query: str) -> MultilingualParseResult:
    """Deterministically parse and normalize non-English fashion search queries."""
    lang = detect_language(raw_query)
    if lang == "en":
        return MultilingualParseResult(
            detected_language="en",
            normalized_query_en=raw_query,
            is_confidently_parsed=False,
        )

    # 1. Slot extraction
    slots: list[str] = []
    slot_en_terms: list[str] = []
    slot_rules = _SLOT_LEXICON.get(lang, [])
    for slot_name, pat, en_term in slot_rules:
        if re.search(pat, raw_query, re.IGNORECASE) and slot_name not in slots:
            slots.append(slot_name)
            slot_en_terms.append(en_term)

    # 2. Gender and age extraction
    gender: Literal["men", "women", "unisex"] | None = None
    age_group: Literal["adult", "kids"] = "adult"
    demographic_en_terms: list[str] = []

    gender_rules = _GENDER_LEXICON.get(lang, [])
    for g_val, pat, _en_term in gender_rules:
        if re.search(pat, raw_query, re.IGNORECASE):
            if g_val == "kids":
                age_group = "kids"
                # If gender not set yet, check if language specifies boys/girls
                is_girl = (
                    "பெண்" in raw_query
                    or "लड़की" in raw_query
                    or "niña" in raw_query.lower()
                    or "fille" in raw_query.lower()
                )
                is_boy = (
                    "ஆண்" in raw_query
                    or "लड़का" in raw_query
                    or "niño" in raw_query.lower()
                    or "garçon" in raw_query.lower()
                )
                if is_girl:
                    gender = "women"
                    demographic_en_terms.append("girls")
                elif is_boy:
                    gender = "men"
                    demographic_en_terms.append("boys")
                else:
                    demographic_en_terms.append("kids")
            elif g_val in ("men", "women", "unisex"):
                gender = g_val  # type: ignore[assignment]
                demographic_en_terms.append(f"{g_val}'s")

    # 3. Price extraction
    min_price, max_price = _extract_price(raw_query, lang)

    # 4. Extract concept keywords for English normalization
    concept_terms: list[str] = []
    season: str | None = None
    occasion: str | None = None
    colors: list[str] = []

    lang_concepts = _CONCEPT_TERMS.get(lang, [])
    for pat, en_term in lang_concepts:
        if re.search(pat, raw_query, re.IGNORECASE):
            concept_terms.append(en_term)
            if en_term in ("summer", "winter", "spring", "fall"):
                season = en_term
            if en_term in ("beach", "vacation", "workout", "gym", "party", "travel"):
                occasion = en_term
            if en_term in ("black", "brown", "red", "blue", "white", "silk"):
                colors.append(en_term)

    # 5. Build canonical English normalized query
    # E.g.: "summer dress for beach vacation under 50"
    query_parts: list[str] = []
    if demographic_en_terms:
        query_parts.extend(demographic_en_terms)
    if concept_terms:
        query_parts.extend(concept_terms)
    if slot_en_terms:
        query_parts.extend(slot_en_terms)
    if max_price is not None:
        query_parts.append(f"under {int(max_price) if max_price.is_integer() else max_price}")

    if query_parts:
        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped_parts = []
        for p in query_parts:
            if p not in seen:
                seen.add(p)
                deduped_parts.append(p)
        canonical_en = " ".join(deduped_parts)
        is_confidently_parsed = bool(slots or gender or max_price is not None)
    else:
        canonical_en = raw_query
        is_confidently_parsed = False

    warnings: list[str] = []
    if not is_confidently_parsed:
        warnings.append("filters_not_applied_without_llm")

    return MultilingualParseResult(
        detected_language=lang,
        normalized_query_en=canonical_en,
        gender=gender,
        age_group=age_group,
        min_price=min_price,
        max_price=max_price,
        slots=slots,
        colors=colors,
        season=season,
        occasion=occasion,
        brand=None,
        is_fashion_query=True,
        is_confidently_parsed=is_confidently_parsed,
        warnings=warnings,
    )
