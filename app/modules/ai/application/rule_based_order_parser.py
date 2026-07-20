"""Deterministic natural-language parser for common restaurant orders.

Keep the most common ASADERO phrases here before involving Gemini. This module
is deliberately simple: it maps human aliases to catalog codes and extracts
small integer quantities without ever inventing products.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.ai.application.schemas import NaturalLanguageOrderParse, ParsedOrderItem
from app.shared.utils.text_normalizer import normalize_text


@dataclass(frozen=True)
class NaturalProductRule:
    code: str
    product_terms: tuple[str, ...]
    size_terms: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()


NUMBER_WORDS = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "par": 2,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
}


ASADO_STYLE_TERMS = (
    "asado",
    "asados",
    "asada",
    "asadas",
    "asadito",
    "asaditos",
)


BROASTER_TERMS = (
    "broaster",
    "broasterr",
    "broasther",
    "broasters",
    "broasted",
    "brouster",
    "broster",
    "brosterr",
    "brostter",
    "brostee",
    "brosters",
    "broche",
    "broches",
    "brosted",
    "bruster",
    "brusters",
)


COOKING_STYLE_TERMS = ASADO_STYLE_TERMS + BROASTER_TERMS


CHICKEN_TERMS = (
    "pollo",
    "pollos",
    "pollito",
    "pollitos",
)


UNSUPPORTED_COOKED_FOOD_TERMS = (
    "chorizo",
    "chorizos",
    "carne",
    "carnes",
    "res",
    "cerdo",
    "costilla",
    "costillas",
    "salchicha",
    "salchichas",
    "pescado",
    "pescados",
    "tilapia",
    "mojarra",
    "hamburguesa",
    "hamburguesas",
    "perro",
    "perros",
    "pincho",
    "pinchos",
    "arepa",
    "arepas",
    "mazorca",
    "mazorcas",
    "lomo",
    "chuleta",
    "chuletas",
    "morcilla",
    "morcillas",
)


PRODUCT_RULES: tuple[NaturalProductRule, ...] = (
    # Specific sizes must appear before generic products. For example, "medio
    # pollo" should become ASADO_MEDIO, not ASADO_ENTERO or a generic pollo.
    NaturalProductRule(
        "ASADO_34",
        ("pollo", "pollos", "asado"),
        ("3/4", "3 4", "tres cuartos", "tres cuarto"),
        BROASTER_TERMS,
    ),
    NaturalProductRule(
        "ASADO_MEDIO",
        ("pollo", "pollos", "asado"),
        ("1/2", "1 2", "medio", "medios", "media", "mitad"),
        BROASTER_TERMS,
    ),
    NaturalProductRule(
        "ASADO_CUARTO",
        ("pollo", "pollos", "asado"),
        ("1/4", "1 4", "cuarto", "cuartos"),
        BROASTER_TERMS + ("tres cuartos", "3/4"),
    ),
    NaturalProductRule(
        "ASADO_ENTERO",
        (
            "pollo",
            "pollos",
            "pollo asado",
            "pollos asados",
            "pollito asado",
            "pollitos asados",
            "pollitos",
            "asado",
            "asados",
            "asadito",
            "asaditos",
        ),
        ("entero", "completo", "uno", "un"),
        BROASTER_TERMS + ("medio", "cuarto", "3/4", "1/2", "1/4"),
    ),
    NaturalProductRule(
        "BROASTER_34",
        BROASTER_TERMS,
        ("3/4", "3 4", "tres cuartos", "tres cuarto"),
    ),
    NaturalProductRule(
        "BROASTER_MEDIO",
        BROASTER_TERMS,
        ("1/2", "1 2", "medio", "medios", "media", "mitad"),
    ),
    NaturalProductRule(
        "BROASTER_CUARTO",
        BROASTER_TERMS,
        ("1/4", "1 4", "cuarto", "cuartos"),
        ("tres cuartos", "3/4"),
    ),
    NaturalProductRule(
        "BROASTER_ENTERO",
        BROASTER_TERMS + ("broasteres",),
        ("entero", "completo", "uno", "un"),
        ("medio", "cuarto", "3/4", "1/2", "1/4"),
    ),
    NaturalProductRule(
        "COCA_COLA_15",
        ("coca", "cocas", "cocacola", "coca cola", "coca colas"),
        ("1.5", "1,5", "1 5", "litro y medio", "litro medio", "litroymedio"),
    ),
    NaturalProductRule(
        "GASEOSA_25",
        (
            "kola",
            "gaseosa kola",
            "gaseosa de kola",
            "pepsi",
            "gaseosa pepsi",
            "pina",
            "piña",
            "gaseosa pina",
            "gaseosa piña",
            "colombiana",
            "gaseosa colombiana",
            "manzana",
            "gaseosa manzana",
            "gaseosa",
        ),
        ("2.5", "2,5", "2 5", "dos litros y medio", "2 litros y medio"),
    ),
    NaturalProductRule(
        "QUATRO_15",
        ("quatro", "cuatro"),
        ("1.5", "1,5", "1 5", "litro y medio", "litro medio", "litroymedio"),
    ),
    NaturalProductRule(
        "PERSONAL_400",
        ("personal", "400", "400ml", "400 ml", "coca personal", "coca cola personal"),
        ("coca", "cocacola", "coca cola", "gaseosa"),
    ),
    NaturalProductRule(
        "JUGO_HIT_PERSONAL",
        (
            "jugo hit personal",
            "hit personal",
            "jugo tropical",
            "hit tropical",
            "jugo de tropical",
            "hit de tropical",
            "jugo mango",
            "hit mango",
            "jugo de mango",
            "hit de mango",
        ),
        exclusions=("litro", "1.5", "1,5", "2.5", "2,5"),
    ),
    NaturalProductRule(
        "PAPA_FRANCESA",
        (
            "papa francesa",
            "papas francesas",
            "papa",
            "papas",
            "porcion de francesa",
            "porcion de francesas",
            "porción de francesa",
            "porción de francesas",
            "papa frita",
            "papas fritas",
            "papita",
            "papitas",
            "papitas fritas",
            "fritas",
            "adicional de papas",
            "adicional de papas fritas",
        ),
    ),
    NaturalProductRule("PAPA_SALADA", ("papa salada", "papas saladas", "papa cocida", "yuca salada", "papa o yuca salada")),
    NaturalProductRule(
        "YUCA_FRITA",
        (
            "yuca frita",
            "yucas fritas",
            "adicional de yuca frita",
            "porcion de yuca frita",
            "porción de yuca frita",
        ),
    ),
    NaturalProductRule(
        "ADICIONAL_SALSAS",
        (
            "adicional de salsas",
            "adicional de salsa",
            "adicional de tartara",
            "adicional de tártara",
            "adicional de aji",
            "adicional de ají",
            "adicional de miel",
            "adicional de tomate",
            "adicional de salsa de tomate",
            "extra salsas",
            "extra salsa",
            "extra tartara",
            "extra tártara",
            "extra aji",
            "extra ají",
            "extra miel",
            "extra tomate",
            "extra salsa de tomate",
            "mas salsas",
            "más salsas",
            "mas salsa",
            "más salsa",
            "mas tartara",
            "más tártara",
            "mas aji",
            "más ají",
            "mas miel",
            "más miel",
            "mas tomate",
            "más tomate",
            "salsa adicional",
        ),
    ),
    NaturalProductRule("SOPA_ADICIONAL", ("sopa", "sopita", "sopa adicional")),
    NaturalProductRule(
        "ICOPOR_SOPA",
        (
            "icopor sopa",
            "icopor para sopa",
            "icopores para sopa",
            "icopor de sopa",
            "icopol sopa",
            "icopol para sopa",
            "icopor pa la sopa",
            "icopor pa sopa",
            "vaso sopa",
            "vasito sopa",
            "sopa con icopor",
            "sopa en icopor",
            "sopa con icopores",
            "sopa en icopores",
            "sopa con icopol",
            "sopa en icopol",
            "sopa en vasito",
            "sopa en vaso",
            "sopita con icopor",
            "sopita en icopor",
            "sopita con icopol",
            "sopita en icopol",
        ),
    ),
    NaturalProductRule(
        "LASAGNA_MIXTA",
        (
            "lasagna mixta",
            "lasagna mista",
            "lasana mixta",
            "lasana mista",
            "lasaña mixta",
            "lasaña mista",
            "lasagna",
            "lasana",
            "lasaña",
        ),
    ),
    NaturalProductRule("MADURO_QUESO", ("maduro", "maduro con queso", "platano maduro")),
    NaturalProductRule("AGUA_BOTELLA", ("agua", "agua botella", "botella de agua")),
    NaturalProductRule(
        "JUGO_HIT_LITRO",
        ("jugo hit litro", "hit litro", "hit litro tetra", "jugo hit litro tetra"),
    ),
    NaturalProductRule("CLUB_COLOMBIA", ("club colombia", "club")),
    NaturalProductRule("PILSEN_BOTELLA", ("pilsen", "pilsen botella")),
    NaturalProductRule("CERVEZA_MILLER_LATA", ("miller", "miller lata", "cerveza miller")),
    NaturalProductRule("CERVEZA_LATA", ("cerveza lata", "cerveza en lata", "lata de cerveza")),
    NaturalProductRule("ALOHA_VASO", ("aloha vaso", "vaso aloha")),
    NaturalProductRule("BOCATO_CONO", ("bocato", "bocato cono", "cono bocato")),
    NaturalProductRule("ARTESANAL", ("artesanal", "helado artesanal")),
    NaturalProductRule("PLATILLO_JUMBO", ("platillo jumbo",)),
    NaturalProductRule("PLATILLO", ("platillo",), exclusions=("jumbo",)),
    NaturalProductRule("PALETA_DRACULA", ("paleta dracula", "dracula")),
    NaturalProductRule("CHOCOCONO", ("chococono", "choco cono")),
    NaturalProductRule("ALOHA_LIMON", ("aloha limon", "aloha limón")),
    NaturalProductRule("PALETA_JET", ("paleta jet", "jet")),
    NaturalProductRule("CASERO", ("casero", "helado casero")),
    NaturalProductRule("MINI_POLET", ("mini polet",)),
    NaturalProductRule("POLET", ("polet",), exclusions=("mini polet",)),
)


def looks_like_unsupported_cooked_food_request(message: str) -> bool:
    """Return true when a grilled/broaster request names a non-catalog food."""
    normalized = _normalize_for_matching(message)
    return (
        _contains_any_terms(normalized, COOKING_STYLE_TERMS)
        and _contains_any_terms(normalized, UNSUPPORTED_COOKED_FOOD_TERMS)
        and not _contains_any_terms(normalized, CHICKEN_TERMS)
    )


def parse_natural_order_rules(message: str) -> NaturalLanguageOrderParse:
    normalized = _normalize_for_matching(message)
    items: list[ParsedOrderItem] = []
    matched_codes: set[str] = set()
    unsupported_cooked_food = looks_like_unsupported_cooked_food_request(normalized)
    half_combo_order = _looks_like_half_asado_half_broaster_order(normalized)

    for rule in PRODUCT_RULES:
        # Only one line per product code is emitted, even if the user repeats
        # several synonyms in the same message.
        if rule.code in matched_codes:
            continue
        if half_combo_order and rule.code == "ASADO_ENTERO":
            continue
        if unsupported_cooked_food and rule.code.startswith(("ASADO_", "BROASTER_")):
            continue
        if _matches_rule(normalized, rule):
            if rule.code == "SOPA_ADICIONAL" and _looks_like_soup_or_contents_question(normalized):
                continue
            items.append(
                ParsedOrderItem(
                    code=rule.code,
                    quantity=_quantity_before_product(normalized, rule),
                )
            )
            matched_codes.add(rule.code)

    wants_checkout = any(
        term in normalized
        for term in ("finalizar", "confirmar pedido", "terminar pedido", "checkout")
    )
    confidence = 0.92 if items else 0.0
    return NaturalLanguageOrderParse(
        intent="order_items" if items else "unknown",
        items=items,
        wantsCheckout=wants_checkout,
        confidence=confidence,
        notes=[
            *(["rule_based_parser"] if items else []),
            *(["unsupported_cooked_food"] if unsupported_cooked_food else []),
        ],
    )


def _normalize_for_matching(message: str) -> str:
    # Normalize punctuation and Spanish fraction symbols while preserving values
    # such as 1.5 because drink sizes depend on them.
    normalized = normalize_text(message)
    normalized = normalized.replace("½", " 1/2 ").replace("¼", " 1/4 ").replace("¾", " 3/4 ")
    normalized = re.sub(r"(?<=\d),(?=\d)", ".", normalized)
    normalized = re.sub(r"(?<=\d)\s*/\s*(?=\d)", "/", normalized)
    normalized = re.sub(r"(?<=\d)\.(?=\d)", ".", normalized)
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"[¿?¡!.,;:()]", " ", normalized)
    normalized = _collapse_repeated_vowels(normalized)
    normalized = re.sub(r"\bunpollo\b", "un pollo", normalized)
    return " ".join(normalized.split())


def _collapse_repeated_vowels(text: str) -> str:
    return re.sub(r"([aeiou])\1+", r"\1", text)


def _matches_rule(text: str, rule: NaturalProductRule) -> bool:
    if len(_order_segments(text)) > 1:
        return _matches_rule_in_any_segment(text, rule)
    if any(_contains_term(text, exclusion) for exclusion in rule.exclusions):
        return False
    if not any(_contains_term(text, term) for term in rule.product_terms):
        return False
    if rule.code == "ASADO_ENTERO" and _looks_like_whole_roasted_chicken(text):
        return True
    if rule.code == "BROASTER_ENTERO" and _looks_like_whole_broaster_chicken(text):
        return True
    if rule.code == "GASEOSA_25" and _looks_like_25_liter_soda_flavor(text):
        return True
    if not rule.size_terms:
        return True
    return any(_contains_term(text, term) for term in rule.size_terms)


def _looks_like_soup_or_contents_question(text: str) -> bool:
    return _contains_any_terms(
        text,
        (
            "trae sopa",
            "viene con sopa",
            "incluye sopa",
            "tiene sopa",
            "dan sopa",
            "me dan sopa",
            "con que viene",
            "con qué viene",
            "que trae",
            "qué trae",
            "que incluye",
            "qué incluye",
        ),
    )


def _looks_like_half_asado_half_broaster_order(text: str) -> bool:
    if "?" in text or "puedo" in text or "pueden" in text:
        return False
    has_half_asado = re.search(r"\bmedio\s+(?:pollo\s+)?asado\b|\bmedio\s+a\s+la\s+asado\b", text) is not None
    has_half_broaster = re.search(
        r"\bmedio\s+(?:pollo\s+)?(?:a\s+la\s+)?(?:broaster|broasted|broster|broche|brosted)\b",
        text,
    ) is not None
    return has_half_asado and has_half_broaster


def _matches_rule_in_any_segment(text: str, rule: NaturalProductRule) -> bool:
    # Mixed orders often put different chicken styles in one sentence:
    # "2 cuartos broaster y 1 cuarto asado". Match each side independently so
    # a broaster term in one item does not suppress the asado item in the next.
    segments = _order_segments(text)
    if len(segments) <= 1:
        return False
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        if any(_contains_term(segment, exclusion) for exclusion in rule.exclusions):
            continue
        if not any(_contains_term(segment, term) for term in rule.product_terms):
            continue
        if rule.code == "ASADO_ENTERO" and _looks_like_whole_roasted_chicken(segment):
            return True
        if rule.code == "BROASTER_ENTERO" and _looks_like_whole_broaster_chicken(segment):
            return True
        if rule.code == "GASEOSA_25" and _looks_like_25_liter_soda_flavor(segment):
            return True
        if not rule.size_terms or any(_contains_term(segment, term) for term in rule.size_terms):
            return True
    return False


def _looks_like_whole_roasted_chicken(text: str) -> bool:
    if not _contains_any_terms(
        text,
        (
            "pollo asado",
            "pollos asados",
            "pollito asado",
            "pollitos asados",
            "pollitos",
            "asado",
            "asados",
            "asadito",
            "asaditos",
        ),
    ):
        return False
    if _contains_any_terms(text, ("medio", "media", "mitad", "cuarto", "cuartos", "3/4", "1/2", "1/4")):
        return False
    if _has_quantity_before_any_term(text, ("pollo asado", "pollos asados", "asado", "asados")):
        return True
    return _contains_any_terms(
        text,
        (
            "vende",
            "vendes",
            "venden",
            "vender",
            "regala",
            "regalas",
            "colabora",
            "colaboras",
            "colaborar",
            "colaborarme",
            "me colabora",
            "me colaboras",
            "me puede colaborar",
            "me puedes colaborar",
            "puede colaborar",
            "puedes colaborar",
            "necesito",
            "quiero",
            "deme",
            "dame",
            "me da",
            "me das",
            "me hace",
            "favor",
            "porfa",
        ),
    )


def _looks_like_whole_broaster_chicken(text: str) -> bool:
    if _contains_any_terms(
        text,
        (
            "otro pedido",
            "nuevo pedido",
            "hacer pedido",
            "hacer otro pedido",
            "hacer un pedido",
            "pedir otra vez",
            "pedir de nuevo",
        ),
    ):
        return False
    if not _contains_any_terms(
        text,
        (
            *BROASTER_TERMS,
            *(f"pollo {term}" for term in BROASTER_TERMS),
            *(f"pollo a la {term}" for term in BROASTER_TERMS),
            *(f"pollos {term}" for term in BROASTER_TERMS),
        ),
    ):
        return False
    if _contains_any_terms(text, ("medio", "media", "mitad", "cuarto", "cuartos", "3/4", "1/2", "1/4")):
        return False
    if _has_quantity_before_any_term(
        text,
        (
            *BROASTER_TERMS,
            *(f"pollo {term}" for term in BROASTER_TERMS),
            *(f"pollo a la {term}" for term in BROASTER_TERMS),
            *(f"pollos {term}" for term in BROASTER_TERMS),
        ),
    ):
        return True
    return _contains_any_terms(
        text,
        (
            "vende",
            "vendes",
            "venden",
            "vender",
            "regala",
            "regalas",
            "colabora",
            "colaboras",
            "colaborar",
            "colaborarme",
            "me colabora",
            "me colaboras",
            "me puede colaborar",
            "me puedes colaborar",
            "puede colaborar",
            "puedes colaborar",
            "necesito",
            "quiero",
            "deme",
            "dame",
            "me da",
            "me das",
            "me hace",
            "favor",
            "porfa",
        ),
    )


def _looks_like_25_liter_soda_flavor(text: str) -> bool:
    return _contains_any_terms(
        text,
        (
            "kola",
            "gaseosa kola",
            "gaseosa de kola",
            "pepsi",
            "gaseosa pepsi",
            "pina",
            "piña",
            "gaseosa pina",
            "gaseosa piña",
            "colombiana",
            "gaseosa colombiana",
        ),
    )


def _contains_any_terms(text: str, terms: tuple[str, ...]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _has_quantity_before_any_term(text: str, terms: tuple[str, ...]) -> bool:
    quantity = r"(?:[1-9]\d*|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)"
    return any(
        re.search(rf"\b{quantity}\s+{_term_regex(_normalize_for_matching(term))}\b", text)
        for term in terms
    )


def _contains_term(text: str, term: str) -> bool:
    normalized_term = _normalize_for_matching(term)
    if not normalized_term:
        return False
    return re.search(rf"(^|\s){_term_regex(normalized_term)}(\s|$)", text) is not None


def _term_regex(normalized_term: str) -> str:
    return r"\s+".join(_word_regex(token) for token in normalized_term.split())


def _word_regex(token: str) -> str:
    if not token or any(char.isdigit() for char in token) or "/" in token or "." in token:
        return re.escape(token)
    variants = {token}
    if token.endswith("z") and len(token) > 2:
        variants.add(token[:-1] + "ces")
    if not token.endswith("s"):
        variants.add(token + "s")
        variants.add(token + "es")
    return "(?:" + "|".join(re.escape(variant) for variant in sorted(variants, key=len, reverse=True)) + ")"


def _quantity_before_product(text: str, rule: NaturalProductRule) -> int:
    # Quantities are interpreted as units before the matched product phrase:
    # "dos papas" => quantity 2, while "medio pollo" remains one ASADO_MEDIO.
    for term in rule.product_terms + rule.size_terms:
        normalized_term = _normalize_for_matching(term)
        if normalized_term and _contains_term(text, f"par de {normalized_term}"):
            return 2
    positions = _rule_positions(text, rule)
    product_position = min(positions) if positions else 0
    segment_start = _segment_start_for_position(text, product_position)
    prefix = text[segment_start:product_position].strip()
    tokens = prefix.split()
    if not tokens:
        return 1
    if "par" in tokens[max(0, len(tokens) - 5) :]:
        return 2
    for token in reversed(tokens[-4:]):
        if token in {"con", "y", "mas", "más"}:
            return 1
        if token.isdigit():
            return max(1, int(token))
        value = NUMBER_WORDS.get(token)
        if value is not None:
            return value
    return 1


def _rule_positions(text: str, rule: NaturalProductRule) -> list[int]:
    positions: list[int] = []
    for segment, offset in _order_segments_with_offsets(text):
        if any(_contains_term(segment, exclusion) for exclusion in rule.exclusions):
            continue
        for term in rule.product_terms + rule.size_terms:
            normalized_term = _normalize_for_matching(term)
            if not normalized_term:
                continue
            for match in re.finditer(rf"(^|\s)({_term_regex(normalized_term)})(\s|$)", segment):
                positions.append(offset + match.start(2))
    return positions


def _order_segments(text: str) -> list[str]:
    return [segment for segment, _ in _order_segments_with_offsets(text)]


def _order_segments_with_offsets(text: str) -> list[tuple[str, int]]:
    item_start = (
        r"(?:un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|[1-9]\d*|[1-9]\s*/\s*[1-9]|medio|media|mitad)\s+(?:de\s+)?(?:a\s+la\s+)?"
        r"(?:pollo|pollos|asado|asados|cuarto|cuartos|broaster|broasterr|broasther|broasters|broasted|brouster|broster|brosters|broche|broches|brosted|brosterr|brostter|brostee|bruster|brusters|coca|cocas|cocacola|gaseosa|gaseosas|papa|papas|yuca|sopa|lasagna|lasana|lasaña|maduro)\b"
    )
    boundary = re.compile(rf"\s+y\s+(?={item_start})|\s+(?={item_start})")
    segments: list[tuple[str, int]] = []
    start = 0
    for match in boundary.finditer(text):
        segment = text[start:match.start()].strip()
        if segment:
            offset = start + len(text[start:match.start()]) - len(text[start:match.start()].lstrip())
            segments.append((segment, offset))
        start = match.end() if match.group(0).strip() == "y" else match.start() + 1
    tail = text[start:].strip()
    if tail:
        offset = start + len(text[start:]) - len(text[start:].lstrip())
        segments.append((tail, offset))
    return segments or [(text, 0)]


def _segment_start_for_position(text: str, position: int) -> int:
    for segment, offset in _order_segments_with_offsets(text):
        if offset <= position < offset + len(segment):
            return offset
    return 0
