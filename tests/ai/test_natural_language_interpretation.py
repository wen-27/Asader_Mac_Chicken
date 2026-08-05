"""Automated test module. It documents expected behavior and protects production bot flows from regressions."""

from __future__ import annotations

import pytest

from app.modules.ai.application.schemas import NaturalLanguageOrderParse, ParsedOrderItem
from app.modules.ai.application.rule_based_order_parser import parse_natural_order_rules
from app.modules.ai.application.semantic_search import CatalogSemanticMatch, CatalogSemanticSearch
from app.modules.ai.application.use_cases import InterpretNaturalOrder, InterpretNaturalOrderCommand
from app.modules.catalog.domain.enums import ProductCategory
from app.modules.catalog.domain.product import Product
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ProductCode, ProductName


class FakeProductRepository:
    def __init__(self) -> None:
        self.products = {
            "ASADO_ENTERO": Product(
                code=ProductCode("ASADO_ENTERO"),
                name=ProductName("1 Asado Entero"),
                category=ProductCategory.POLLO_ASADO,
                price=MoneyCOP(44500),
            ),
            "ASADO_34": Product(
                code=ProductCode("ASADO_34"),
                name=ProductName("3/4 Asado"),
                category=ProductCategory.POLLO_ASADO,
                price=MoneyCOP(34000),
            ),
            "ASADO_MEDIO": Product(
                code=ProductCode("ASADO_MEDIO"),
                name=ProductName("1/2 Asado"),
                category=ProductCategory.POLLO_ASADO,
                price=MoneyCOP(22300),
            ),
            "BROASTER_MEDIO": Product(
                code=ProductCode("BROASTER_MEDIO"),
                name=ProductName("1/2 Broasted"),
                category=ProductCategory.POLLO_BROASTER,
                price=MoneyCOP(25500),
            ),
            "PAPA_FRANCESA": Product(
                code=ProductCode("PAPA_FRANCESA"),
                name=ProductName("Papa Francesa"),
                category=ProductCategory.ADICIONALES,
                price=MoneyCOP(8200),
            ),
            "COCA_COLA_15": Product(
                code=ProductCode("COCA_COLA_15"),
                name=ProductName("Coca-Cola 1.5 L"),
                category=ProductCategory.BEBIDAS,
                price=MoneyCOP(8500),
            ),
            "YUCA_FRITA": Product(
                code=ProductCode("YUCA_FRITA"),
                name=ProductName("Yuca frita"),
                category=ProductCategory.ADICIONALES,
                price=MoneyCOP(5000),
            ),
            "LASAGNA_MIXTA": Product(
                code=ProductCode("LASAGNA_MIXTA"),
                name=ProductName("Lasagna Mixta"),
                category=ProductCategory.ESPECIALES,
                price=MoneyCOP(20000),
            ),
            "JUGO_HIT_PERSONAL": Product(
                code=ProductCode("JUGO_HIT_PERSONAL"),
                name=ProductName("Jugos Hit personal"),
                category=ProductCategory.BEBIDAS,
                price=MoneyCOP(3000),
            ),
        }

    async def get_by_code(self, code: ProductCode):
        return self.products.get(code.value)

    async def list_active(self):
        return list(self.products.values())

    async def add(self, product):
        self.products[product.code.value] = product
        return product


class FakeParser:
    def __init__(self, parsed: NaturalLanguageOrderParse) -> None:
        self.parsed = parsed
        self.calls = 0

    async def parse(self, message: str, catalog_context: str) -> NaturalLanguageOrderParse:
        self.calls += 1
        return self.parsed


class FakeVectorStore:
    async def search(self, query: str, limit: int = 5):
        if "broster" in query or "brosterr" in query:
            return [CatalogSemanticMatch("BROASTER_MEDIO", 0.92, "medio broaster")]
        if "pappas" in query:
            return [CatalogSemanticMatch("PAPA_FRANCESA", 0.88, "papa francesa")]
        return []


def test_rule_based_parser_understands_asado_and_coca_litro_medio() -> None:
    parsed = parse_natural_order_rules("Necesito un pollo asado con una Cocacola 1.5")

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_ENTERO", 1),
        ("COCA_COLA_15", 1),
    ]
    assert parsed.confidence >= 0.9


def test_rule_based_parser_understands_whole_broster_like_whole_asado() -> None:
    parsed = parse_natural_order_rules(
        "Muy buenas tardes veci me vendes 2 pollos broster con adicional de miel porfavor"
    )

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("BROASTER_ENTERO", 2),
        ("ADICIONAL_SALSAS", 1),
    ]
    assert parsed.confidence >= 0.9


def test_rule_based_parser_tolerates_broche_autocorrect_for_quarter_broaster() -> None:
    parsed = parse_natural_order_rules(
        "Porfa para pedir un cuarto broche pechuga ala a la calle 5 numero numero 40-37 lagos 2"
    )

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("BROASTER_CUARTO", 1),
    ]
    assert parsed.confidence >= 0.9


def test_rule_based_parser_tolerates_common_broaster_typos() -> None:
    examples = {
        "quiero medio bruster": [("BROASTER_MEDIO", 1)],
        "quiero un cuarto brostter pierna": [("BROASTER_CUARTO", 1)],
        "me vende dos pollos broasther": [("BROASTER_ENTERO", 2)],
        "necesito un pollo brouster": [("BROASTER_ENTERO", 1)],
        "dame 3/4 broasterr": [("BROASTER_34", 1)],
        "Para pedir medio pollo asado y medio a la brother": [("ASADO_MEDIO", 1), ("BROASTER_MEDIO", 1)],
        "Me puedes enviar medio pollo a la brosther porfa": [("BROASTER_MEDIO", 1)],
    }

    for message, expected in examples.items():
        parsed = parse_natural_order_rules(message)
        assert [(item.code, item.quantity) for item in parsed.items] == expected


def test_rule_based_parser_tolerates_polo_typo_for_half_chicken() -> None:
    parsed = parse_natural_order_rules("medio polo")

    assert [(item.code, item.quantity) for item in parsed.items] == [("ASADO_MEDIO", 1)]


def test_rule_based_parser_treats_numeric_three_quarters_as_34_presentation() -> None:
    parsed = parse_natural_order_rules("3 cuartos de pollo a la broster (2pierna pernil 1 pechuga)")

    assert [(item.code, item.quantity) for item in parsed.items] == [("BROASTER_34", 1)]


def test_rule_based_parser_understands_mixed_whole_brosters_and_asado() -> None:
    parsed = parse_natural_order_rules("Buenos días me vendes dos pollos brosters y un pollo asado")

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_ENTERO", 1),
        ("BROASTER_ENTERO", 2),
    ]
    assert parsed.confidence >= 0.9


def test_rule_based_parser_accepts_plural_aliases_generically() -> None:
    examples = {
        "quiero dos lasagnas": [("LASAGNA_MIXTA", 2)],
        "quiero tres maduros": [("MADURO_QUESO", 3)],
        "quiero dos aguas": [("AGUA_BOTELLA", 2)],
        "quiero dos jugos hit personales": [("JUGO_HIT_PERSONAL", 2)],
        "quiero dos cervezas miller": [("CERVEZA_MILLER_LATA", 2)],
        "quiero tres paletas dracula": [("PALETA_DRACULA", 3)],
    }

    for message, expected in examples.items():
        parsed = parse_natural_order_rules(message)
        assert [(item.code, item.quantity) for item in parsed.items] == expected


def test_rule_based_parser_charges_soup_icopor_only_for_soup_context() -> None:
    parsed = parse_natural_order_rules("quiero una sopa con icopor")

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("SOPA_ADICIONAL", 1),
        ("ICOPOR_SOPA", 1),
    ]

    generic_icopor = parse_natural_order_rules("quiero dos icopores")
    glass_bottle = parse_natural_order_rules("quiero una botella de vidrio")

    assert generic_icopor.items == []
    assert glass_bottle.items == []


def test_rule_based_parser_charges_only_icopor_for_included_chicken_soup_container() -> None:
    parsed = parse_natural_order_rules("medio asado con sopa en icopor porfa")

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_MEDIO", 1),
        ("ICOPOR_SOPA", 1),
    ]


def test_rule_based_parser_charges_soup_icopor_with_irregular_text() -> None:
    examples = [
        "quiero sopa en icopol",
        "me da una sopita con icopor pa llevar",
        "quiero una sopa en vasito",
        "sopa con icopores porfa",
        "quiero sopa no en bolsa sino en icopor",
        "una sopa no en bolsa en vasito",
    ]

    for message in examples:
        parsed = parse_natural_order_rules(message)
        assert ("ICOPOR_SOPA", 1) in [(item.code, item.quantity) for item in parsed.items]


def test_rule_based_parser_charges_paid_sauce_extras_only_when_requested() -> None:
    paid_examples = {
        "con adicional de tartara": [("ADICIONAL_SALSAS", 1)],
        "quiero mas miel": [("ADICIONAL_SALSAS", 1)],
        "extra salsa de tomate": [("ADICIONAL_SALSAS", 1)],
        "adicional de aji": [("ADICIONAL_SALSAS", 1)],
    }

    for message, expected in paid_examples.items():
        parsed = parse_natural_order_rules(message)
        assert [(item.code, item.quantity) for item in parsed.items] == expected

    assert parse_natural_order_rules("bastante tartara").items == []
    assert parse_natural_order_rules("con la napa de salsa").items == []


def test_rule_based_parser_does_not_assume_plain_chicken_is_asado() -> None:
    parsed = parse_natural_order_rules("quiero un pollo")

    assert [(item.code, item.quantity) for item in parsed.items] == [("ASADO_ENTERO", 1)]
    assert parsed.intent == "order_items"


def test_rule_based_parser_keeps_unstyled_whole_and_quarters_before_style_question() -> None:
    parsed = parse_natural_order_rules("Me da porfavor 1 pollo y 2 cuartos de pollo pierna pernil")

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_CUARTO", 2),
        ("ASADO_ENTERO", 1),
    ]


def test_rule_based_parser_tolerates_joined_unpollo_typo() -> None:
    parsed = parse_natural_order_rules("dame unpollo porfa")

    assert [(item.code, item.quantity) for item in parsed.items] == [("ASADO_ENTERO", 1)]


def test_rule_based_parser_understands_fractions_and_word_quantities() -> None:
    parsed = parse_natural_order_rules("agrega dos medios pollos y tres papas francesas")

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_MEDIO", 2),
        ("PAPA_FRANCESA", 3),
    ]


def test_rule_based_parser_understands_real_chat_roasted_chicken_and_half_order() -> None:
    parsed = parse_natural_order_rules("Me regala pollo y medio entonces")

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_ENTERO", 1),
        ("ASADO_MEDIO", 1),
    ]


def test_rule_based_parser_does_not_convert_roasted_chicken_and_half_price_question_to_half_order() -> None:
    parsed = parse_natural_order_rules("Pollo y medio q vale")

    assert parsed.items == []
    assert parsed.intent == "unknown"


def test_rule_based_parser_does_not_convert_chicken_and_soup_question_to_soup_order() -> None:
    examples = [
        "ven ustedes venden pollo con sopa ?",
        "Disculpe le queda sopa?",
        "Hay aun sopa?",
        "Todavía tienen sopita",
        "Tiene sopita ?",
        "Me guardas sopita cierto?",
        "Sopa no",
        "sin sopita por favor",
        "no sopa",
        "Con sopa?",
        "Una pregunta vine con sopa?",
        "Vienen con sopa?",
    ]

    for example in examples:
        parsed = parse_natural_order_rules(example)
        assert parsed.items == []
        assert parsed.intent == "unknown"


def test_rule_based_parser_keeps_chicken_when_customer_declines_soup() -> None:
    parsed = parse_natural_order_rules("Me regala medio pollo asado sin sopa")

    assert [(item.code, item.quantity) for item in parsed.items] == [("ASADO_MEDIO", 1)]


def test_rule_based_parser_does_not_charge_included_roasted_sides_as_addons() -> None:
    parsed = parse_natural_order_rules("Por favor me envía un pollo asado con papa y yuca, sopa y aji")

    assert [(item.code, item.quantity) for item in parsed.items] == [("ASADO_ENTERO", 1)]


def test_rule_based_parser_respects_replaced_papa_side_without_addon() -> None:
    parsed = parse_natural_order_rules(
        "Me gustaría ordenar un pollo asado y en lugar de papá, me dieras solo yuca frita, es posible?"
    )

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_ENTERO", 1),
        ("YUCA_FRITA", 1),
    ]


def test_rule_based_parser_understands_platano_con_queso_as_maduro() -> None:
    parsed = parse_natural_order_rules("Para pedir por favor 1 pollo asado, 2 plátanos con queso")

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_ENTERO", 1),
        ("MADURO_QUESO", 2),
    ]


def test_rule_based_parser_does_not_convert_cooking_instruction_to_whole_chicken() -> None:
    parsed = parse_natural_order_rules("Pero por fis bien asado y me regalas tártara y tienes sopa")

    assert parsed.items == []
    assert parsed.intent == "unknown"


def test_rule_based_parser_understands_three_quarters() -> None:
    parsed = parse_natural_order_rules("quiero 3/4 de pollo asado")

    assert [(item.code, item.quantity) for item in parsed.items] == [("ASADO_34", 1)]


def test_rule_based_parser_understands_mixed_quarter_chicken_styles() -> None:
    parsed = parse_natural_order_rules(
        "Me regala por favor 2 cuartos de pechuga broaster y 1 cuarto de pechuga asado"
    )

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_CUARTO", 1),
        ("BROASTER_CUARTO", 2),
    ]


def test_rule_based_parser_understands_implicit_quarter_piece_with_style() -> None:
    asado = parse_natural_order_rules("Pechuga asada")
    broaster = parse_natural_order_rules("Y pechuga broaster")
    mixed = parse_natural_order_rules("Buenas tardes para pedir medio a la broster y una pierna asada")
    fries_piece = parse_natural_order_rules("me podría enviar entonces una pierna pernil con papa francesa")
    styled_fries_piece = parse_natural_order_rules("pechuga broaster con papa francesa")
    split_pieces = parse_natural_order_rules(
        "me puede vender por favor dos pechugas, una asada y una broaster"
    )

    assert [(item.code, item.quantity) for item in asado.items] == [("ASADO_CUARTO", 1)]
    assert [(item.code, item.quantity) for item in broaster.items] == [("BROASTER_CUARTO", 1)]
    assert [(item.code, item.quantity) for item in mixed.items] == [
        ("ASADO_CUARTO", 1),
        ("BROASTER_MEDIO", 1),
    ]
    assert [(item.code, item.quantity) for item in fries_piece.items] == [("BROASTER_CUARTO", 1)]
    assert [(item.code, item.quantity) for item in styled_fries_piece.items] == [("BROASTER_CUARTO", 1)]
    assert [(item.code, item.quantity) for item in split_pieces.items] == [
        ("ASADO_CUARTO", 1),
        ("BROASTER_CUARTO", 1),
    ]


def test_rule_based_parser_understands_plural_coca_litro_medio() -> None:
    parsed = parse_natural_order_rules("quiero dos cocas 1.5")

    assert [(item.code, item.quantity) for item in parsed.items] == [("COCA_COLA_15", 2)]


def test_rule_based_parser_does_not_add_ambiguous_litro_medio() -> None:
    parsed = parse_natural_order_rules("quiero dos gaseosas 1.5")

    assert parsed.items == []


def test_rule_based_parser_understands_numeric_whole_broster_typo() -> None:
    parsed = parse_natural_order_rules("1 pollo a la brostee")

    assert [(item.code, item.quantity) for item in parsed.items] == [("BROASTER_ENTERO", 1)]


def test_rule_based_parser_understands_gaseosa_kola_as_25_liter_variant_product() -> None:
    parsed = parse_natural_order_rules("Hola un pollo asado con gaseosa kola")

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_ENTERO", 1),
        ("GASEOSA_25", 1),
    ]


def test_rule_based_parser_only_adds_manzana_when_25_liter_is_explicit() -> None:
    unavailable_size = parse_natural_order_rules("quiero una manzana litro")
    available_size = parse_natural_order_rules("quiero una manzana 2.5")

    assert unavailable_size.items == []
    assert [(item.code, item.quantity) for item in available_size.items] == [("GASEOSA_25", 1)]


def test_rule_based_parser_understands_additional_papas_fritas() -> None:
    parsed = parse_natural_order_rules(
        "Quiero un pollo asado con adicional de papas fritas y una Cocacola 1.5"
    )

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_ENTERO", 1),
        ("COCA_COLA_15", 1),
        ("PAPA_FRANCESA", 1),
    ]


def test_rule_based_parser_ignores_polite_greeting_and_extracts_all_products() -> None:
    parsed = parse_natural_order_rules(
        "hola buenos dias me regala medio broaster una sopa y un hit de mango"
    )

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("BROASTER_MEDIO", 1),
        ("JUGO_HIT_PERSONAL", 1),
        ("SOPA_ADICIONAL", 1),
    ]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Me hace el favor y me vende 2 pollos asados", [("ASADO_ENTERO", 2)]),
        ("me vendes dos pollos asados por favor", [("ASADO_ENTERO", 2)]),
        ("Muy buenas tardes me vendes 2 pollos asados con ají y tartara", [("ASADO_ENTERO", 2)]),
        ("Muy buenas tardes me puedes colaborar con 2 pollos asados con ají y tartara", [("ASADO_ENTERO", 2)]),
        (
            "Muy buenas tardes me puedes colaborar con 2 pollos asados con ají y tartara, que valen?",
            [("ASADO_ENTERO", 2)],
        ),
        ("deme dos asados", [("ASADO_ENTERO", 2)]),
        ("me regalas un par de pollos asados", [("ASADO_ENTERO", 2)]),
        ("buenas me das dos pollitos asados", [("ASADO_ENTERO", 2)]),
        ("porfa un asadito con papitas", [("ASADO_ENTERO", 1), ("PAPA_FRANCESA", 1)]),
        ("necesito 1 asado y dos porciones de yuca frita", [("ASADO_ENTERO", 1), ("YUCA_FRITA", 2)]),
        (
            "Buenas tardes me regalas porfa un pollo asado con yuca frita",
            [("ASADO_ENTERO", 1), ("YUCA_FRITA", 1)],
        ),
        (
            "hola buen dia seria un pollo asado una coca cola 1.5 y papitas",
            [("ASADO_ENTERO", 1), ("COCA_COLA_15", 1), ("PAPA_FRANCESA", 1)],
        ),
        (
            "me colabora con medio broaster y una sopita",
            [("BROASTER_MEDIO", 1), ("SOPA_ADICIONAL", 1)],
        ),
    ],
)
def test_rule_based_parser_understands_real_customer_polite_orders(
    message: str,
    expected: list[tuple[str, int]],
) -> None:
    parsed = parse_natural_order_rules(message)

    assert [(item.code, item.quantity) for item in parsed.items] == expected


def test_rule_based_parser_understands_generic_papas_as_francesa() -> None:
    parsed = parse_natural_order_rules(
        "Hola necesito un pollo asado con unas papas y una Cocacola 1.5"
    )

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_ENTERO", 1),
        ("COCA_COLA_15", 1),
        ("PAPA_FRANCESA", 1),
    ]


def test_rule_based_parser_tolerates_repeated_vowel_typo() -> None:
    parsed = parse_natural_order_rules("quiero una lasaaña")

    assert [(item.code, item.quantity) for item in parsed.items] == [("LASAGNA_MIXTA", 1)]


def test_rule_based_parser_does_not_charge_soup_when_customer_asks_if_included() -> None:
    parsed = parse_natural_order_rules("Me regalas un pollo asado, con que viene? Trae sopa?")

    assert [(item.code, item.quantity) for item in parsed.items] == [("ASADO_ENTERO", 1)]


@pytest.mark.parametrize(
    "message",
    [
        "quiero un chorizo asado",
        "me das una carne asada",
        "quiero costilla asada",
        "me regalas una salchicha broaster",
        "quiero pescado broaster",
    ],
)
def test_rule_based_parser_does_not_convert_unsupported_asado_or_broaster_foods_to_chicken(
    message: str,
) -> None:
    parsed = parse_natural_order_rules(message)

    assert parsed.items == []
    assert parsed.intent == "unknown"
    assert "unsupported_cooked_food" in parsed.notes


def test_rule_based_parser_understands_lasagna_typos() -> None:
    examples = [
        "quiero agregar una lasaña",
        "lasaña mista",
        "lasagna mixta",
        "quiero una lasana mista",
    ]

    for example in examples:
        parsed = parse_natural_order_rules(example)
        assert [(item.code, item.quantity) for item in parsed.items] == [("LASAGNA_MIXTA", 1)]


@pytest.mark.asyncio
async def test_semantic_search_recovers_misspelled_product() -> None:
    parser = FakeParser(
        NaturalLanguageOrderParse(
            intent="order_items",
            items=[ParsedOrderItem(code="BROSTERR_MEDIO", quantity=1)],
            confidence=0.84,
        )
    )
    use_case = InterpretNaturalOrder(
        products=FakeProductRepository(),
        parser=parser,
        semantic_search=CatalogSemanticSearch(FakeVectorStore()),
        llm_fallback_enabled=True,
    )

    result = await use_case.execute(
        InterpretNaturalOrderCommand("quiero medio brosterrr con una coca")
    )

    assert not result.needs_clarification
    assert result.parsed.items[0].code == "BROASTER_MEDIO"
    assert any(note.startswith("discarded_invalid_codes:") for note in result.parsed.notes)


@pytest.mark.asyncio
async def test_unsupported_asado_food_does_not_fall_back_to_ai_as_chicken() -> None:
    parser = FakeParser(
        NaturalLanguageOrderParse(
            intent="order_items",
            items=[ParsedOrderItem(code="ASADO_ENTERO", quantity=1)],
            confidence=0.92,
        )
    )
    use_case = InterpretNaturalOrder(
        products=FakeProductRepository(),
        parser=parser,
        semantic_search=CatalogSemanticSearch(FakeVectorStore()),
        llm_fallback_enabled=True,
    )

    result = await use_case.execute(InterpretNaturalOrderCommand("quiero un chorizo asado"))

    assert result.needs_clarification
    assert result.parsed.items == []
    assert "unsupported_cooked_food" in result.parsed.notes
    assert parser.calls == 0


@pytest.mark.asyncio
async def test_low_confidence_requests_clarification() -> None:
    parser = FakeParser(NaturalLanguageOrderParse(confidence=0.5))
    use_case = InterpretNaturalOrder(
        products=FakeProductRepository(),
        parser=parser,
        semantic_search=CatalogSemanticSearch(FakeVectorStore()),
        llm_fallback_enabled=True,
    )

    result = await use_case.execute(InterpretNaturalOrderCommand("quiero algo rico"))

    assert result.needs_clarification


@pytest.mark.asyncio
async def test_semantic_search_runs_when_parser_returns_no_items() -> None:
    parser = FakeParser(NaturalLanguageOrderParse(intent="order_items", items=[], confidence=0.8))
    use_case = InterpretNaturalOrder(
        products=FakeProductRepository(),
        parser=parser,
        semantic_search=CatalogSemanticSearch(FakeVectorStore()),
        llm_fallback_enabled=True,
    )

    result = await use_case.execute(InterpretNaturalOrderCommand("agrega dos pappas francesas"))

    assert result.parsed.items[0].code == "PAPA_FRANCESA"


@pytest.mark.asyncio
async def test_ai_cannot_keep_invented_codes() -> None:
    parser = FakeParser(
        NaturalLanguageOrderParse(
            items=[ParsedOrderItem(code="INVENTADO", quantity=2)],
            confidence=0.9,
        )
    )
    use_case = InterpretNaturalOrder(
        products=FakeProductRepository(),
        parser=parser,
        semantic_search=CatalogSemanticSearch(FakeVectorStore()),
        llm_fallback_enabled=True,
    )

    result = await use_case.execute(InterpretNaturalOrderCommand("quiero producto inventado"))

    assert result.parsed.items == []
    assert "discarded_invalid_codes:INVENTADO" in result.parsed.notes


@pytest.mark.asyncio
async def test_interpret_natural_order_uses_rules_before_llm() -> None:
    parser = FakeParser(NaturalLanguageOrderParse(confidence=0.0))
    use_case = InterpretNaturalOrder(
        products=FakeProductRepository(),
        parser=parser,
        semantic_search=CatalogSemanticSearch(FakeVectorStore()),
    )

    result = await use_case.execute(
        InterpretNaturalOrderCommand("Necesito un pollo asado con una Cocacola 1.5")
    )

    assert not result.needs_clarification
    assert [(item.code, item.quantity) for item in result.parsed.items] == [
        ("ASADO_ENTERO", 1),
        ("COCA_COLA_15", 1),
    ]
