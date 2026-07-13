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


PRODUCT_RULES: tuple[NaturalProductRule, ...] = (
    # Specific sizes must appear before generic products. For example, "medio
    # pollo" should become ASADO_MEDIO, not ASADO_ENTERO or a generic pollo.
    NaturalProductRule(
        "ASADO_34",
        ("pollo", "pollos", "asado"),
        ("3/4", "3 4", "tres cuartos", "tres cuarto"),
        ("broaster", "broasted", "broster"),
    ),
    NaturalProductRule(
        "ASADO_MEDIO",
        ("pollo", "pollos", "asado"),
        ("1/2", "1 2", "medio", "medios", "media", "mitad"),
        ("broaster", "broasted", "broster"),
    ),
    NaturalProductRule(
        "ASADO_CUARTO",
        ("pollo", "pollos", "asado"),
        ("1/4", "1 4", "cuarto", "cuartos"),
        ("broaster", "broasted", "broster", "tres cuartos", "3/4"),
    ),
    NaturalProductRule(
        "ASADO_ENTERO",
        ("asado",),
        ("entero", "completo", "uno", "un"),
        ("broaster", "broasted", "broster", "medio", "cuarto", "3/4", "1/2", "1/4"),
    ),
    NaturalProductRule(
        "BROASTER_34",
        ("broaster", "broasted", "broster"),
        ("3/4", "3 4", "tres cuartos", "tres cuarto"),
    ),
    NaturalProductRule(
        "BROASTER_MEDIO",
        ("broaster", "broasted", "broster"),
        ("1/2", "1 2", "medio", "medios", "media", "mitad"),
    ),
    NaturalProductRule(
        "BROASTER_CUARTO",
        ("broaster", "broasted", "broster"),
        ("1/4", "1 4", "cuarto", "cuartos"),
        ("tres cuartos", "3/4"),
    ),
    NaturalProductRule(
        "BROASTER_ENTERO",
        ("broaster", "broasted", "broster"),
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
        ("kola", "pepsi", "pina", "piña", "colombiana", "gaseosa"),
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
            "fritas",
            "adicional de papas",
            "adicional de papas fritas",
        ),
    ),
    NaturalProductRule("PAPA_SALADA", ("papa salada", "papas saladas", "papa cocida", "yuca salada", "papa o yuca salada")),
    NaturalProductRule("YUCA_FRITA", ("yuca frita", "yucas fritas", "adicional de yuca frita")),
    NaturalProductRule("BOTELLA_VIDRIO", ("botella vidrio", "botella de vidrio", "envase vidrio")),
    NaturalProductRule("ICOPOR", ("icopor", "icopores", "caja icopor", "cajas icopor")),
    NaturalProductRule(
        "ADICIONAL_SALSAS",
        ("adicional de salsas", "adicional de salsa", "extra salsas", "extra salsa", "salsa adicional"),
    ),
    NaturalProductRule("SOPA_ADICIONAL", ("sopa", "sopita", "sopa adicional")),
    NaturalProductRule("ICOPOR_SOPA", ("icopor sopa", "icopor para sopa", "vaso sopa")),
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


def parse_natural_order_rules(message: str) -> NaturalLanguageOrderParse:
    normalized = _normalize_for_matching(message)
    items: list[ParsedOrderItem] = []
    matched_codes: set[str] = set()

    for rule in PRODUCT_RULES:
        # Only one line per product code is emitted, even if the user repeats
        # several synonyms in the same message.
        if rule.code in matched_codes:
            continue
        if _matches_rule(normalized, rule):
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
        notes=["rule_based_parser"] if items else [],
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
    return " ".join(normalized.split())


def _collapse_repeated_vowels(text: str) -> str:
    return re.sub(r"([aeiou])\1+", r"\1", text)


def _matches_rule(text: str, rule: NaturalProductRule) -> bool:
    if any(_contains_term(text, exclusion) for exclusion in rule.exclusions):
        return False
    if not any(_contains_term(text, term) for term in rule.product_terms):
        return False
    if not rule.size_terms:
        return True
    return any(_contains_term(text, term) for term in rule.size_terms)


def _contains_term(text: str, term: str) -> bool:
    normalized_term = _normalize_for_matching(term)
    if not normalized_term:
        return False
    return re.search(rf"(^|\s){re.escape(normalized_term)}(\s|$)", text) is not None


def _quantity_before_product(text: str, rule: NaturalProductRule) -> int:
    # Quantities are interpreted as units before the matched product phrase:
    # "dos papas" => quantity 2, while "medio pollo" remains one ASADO_MEDIO.
    positions = [
        text.find(_normalize_for_matching(term))
        for term in rule.product_terms + rule.size_terms
        if text.find(_normalize_for_matching(term)) >= 0
    ]
    product_position = min(positions) if positions else 0
    prefix = text[:product_position].strip()
    tokens = prefix.split()
    if not tokens:
        return 1
    last = tokens[-1]
    if last.isdigit():
        return max(1, int(last))
    return NUMBER_WORDS.get(last, 1)
