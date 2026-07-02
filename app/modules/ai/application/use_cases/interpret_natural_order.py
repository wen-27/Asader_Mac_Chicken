"""Use case that interprets natural-language orders using rules, catalog context and the configured LLM fallback."""

from __future__ import annotations

from dataclasses import dataclass
import json

from app.modules.ai.application.ports import CachePort, NaturalLanguageOrderParser
from app.modules.ai.application.rule_based_order_parser import parse_natural_order_rules
from app.modules.ai.application.schemas import NaturalLanguageOrderParse, ParsedOrderItem
from app.modules.ai.application.semantic_search import CatalogSemanticSearch
from app.modules.catalog.application.ports import ProductRepository
from app.shared.domain.value_object import ProductCode


@dataclass(frozen=True)
class InterpretNaturalOrderCommand:
    message: str


@dataclass(frozen=True)
class InterpretNaturalOrderResult:
    parsed: NaturalLanguageOrderParse
    needs_clarification: bool


class InterpretNaturalOrder:
    MIN_CONFIDENCE = 0.70

    def __init__(
        self,
        products: ProductRepository,
        parser: NaturalLanguageOrderParser,
        semantic_search: CatalogSemanticSearch,
        cache: CachePort | None = None,
    ) -> None:
        self._products = products
        self._parser = parser
        self._semantic_search = semantic_search
        self._cache = cache

    async def execute(self, command: InterpretNaturalOrderCommand) -> InterpretNaturalOrderResult:
        # Fast path: deterministic rules cover the common restaurant language and
        # avoid paid/remote LLM calls for phrases like "medio pollo con papas".
        rule_parsed = await self._validate_codes(
            parse_natural_order_rules(command.message),
            command.message,
        )
        if rule_parsed.items:
            return InterpretNaturalOrderResult(parsed=rule_parsed, needs_clarification=False)

        catalog_context = await self._catalog_context()
        # LLM fallback only receives current catalog context. It must return
        # existing product codes; _validate_codes enforces that contract.
        parsed = await self._parser.parse(command.message, catalog_context)
        parsed = await self._validate_codes(parsed, command.message)
        needs_clarification = parsed.confidence < self.MIN_CONFIDENCE
        return InterpretNaturalOrderResult(parsed=parsed, needs_clarification=needs_clarification)

    async def _catalog_context(self) -> str:
        cache_key = "catalog-context:v1"
        if self._cache is not None:
            cached = await self._cache.get_text(cache_key)
            if cached:
                return cached

        # Catalog context is cached briefly because it is read often, but
        # PostgreSQL remains the source of truth for products and prices.
        products = await self._products.list_active()
        context = "\n".join(
            [
                json.dumps(
                    {
                        "code": product.code.value,
                        "name": product.name.value,
                        "category": product.category.value,
                        "price_cop": product.price.amount,
                        "restricted_to": product.restricted_to.value,
                    },
                    ensure_ascii=False,
                )
                for product in products
            ]
        )
        if self._cache is not None:
            await self._cache.set_text(cache_key, context, 300)
        return context

    async def _validate_codes(
        self,
        parsed: NaturalLanguageOrderParse,
        original_message: str,
    ) -> NaturalLanguageOrderParse:
        valid_items: list[ParsedOrderItem] = []
        invalid_codes: list[str] = []
        for item in parsed.items:
            product = await self._products.get_by_code(ProductCode(item.code))
            if product is None:
                invalid_codes.append(item.code)
                continue
            valid_items.append(item)

        if not valid_items and (parsed.items or parsed.intent == "order_items"):
            # If the model produced no usable code, try semantic catalog search
            # over products/aliases. This helps with typos without inventing SKUs.
            semantic_matches = await self._semantic_search.search(original_message, limit=3)
            for match in semantic_matches:
                product = await self._products.get_by_code(ProductCode(match.code))
                if product is not None:
                    valid_items.append(ParsedOrderItem(code=product.code.value, quantity=1))
                    break

        notes = list(parsed.notes)
        if invalid_codes:
            notes.append("discarded_invalid_codes:" + ",".join(invalid_codes))

        return parsed.model_copy(update={"items": valid_items, "notes": notes})
