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

    async def parse(self, message: str, catalog_context: str) -> NaturalLanguageOrderParse:
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


def test_rule_based_parser_does_not_assume_plain_chicken_is_asado() -> None:
    parsed = parse_natural_order_rules("quiero un pollo")

    assert parsed.items == []
    assert parsed.intent == "unknown"


def test_rule_based_parser_understands_fractions_and_word_quantities() -> None:
    parsed = parse_natural_order_rules("agrega dos medios pollos y tres papas francesas")

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_MEDIO", 2),
        ("PAPA_FRANCESA", 3),
    ]


def test_rule_based_parser_understands_three_quarters() -> None:
    parsed = parse_natural_order_rules("quiero 3/4 de pollo asado")

    assert [(item.code, item.quantity) for item in parsed.items] == [("ASADO_34", 1)]


def test_rule_based_parser_understands_plural_coca_litro_medio() -> None:
    parsed = parse_natural_order_rules("quiero dos cocas 1.5")

    assert [(item.code, item.quantity) for item in parsed.items] == [("COCA_COLA_15", 2)]


def test_rule_based_parser_does_not_add_ambiguous_litro_medio() -> None:
    parsed = parse_natural_order_rules("quiero dos gaseosas 1.5")

    assert parsed.items == []


def test_rule_based_parser_understands_gaseosa_kola_as_25_liter_variant_product() -> None:
    parsed = parse_natural_order_rules("Hola un pollo asado con gaseosa kola")

    assert [(item.code, item.quantity) for item in parsed.items] == [
        ("ASADO_ENTERO", 1),
        ("GASEOSA_25", 1),
    ]


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
        InterpretNaturalOrderCommand("quiero medio brosterr con una coca")
    )

    assert not result.needs_clarification
    assert result.parsed.items[0].code == "BROASTER_MEDIO"
    assert any(note.startswith("discarded_invalid_codes:") for note in result.parsed.notes)


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
