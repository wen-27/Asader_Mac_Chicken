"""Application service that prepares catalog documents for the vector store."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.catalog.application.ports import ProductAliasRepository, ProductRepository


@dataclass(frozen=True)
class CatalogVectorDocument:
    id: str
    text: str
    metadata: dict[str, str | int | bool]


class CatalogVectorDocumentBuilder:
    def __init__(
        self,
        products: ProductRepository,
        aliases: ProductAliasRepository,
    ) -> None:
        self._products = products
        self._aliases = aliases

    async def build_documents(self) -> list[CatalogVectorDocument]:
        documents: list[CatalogVectorDocument] = []
        products = await self._products.list_active()
        for product in products:
            aliases = await self._aliases.list_by_product_code(product.code)
            alias_text = ", ".join(alias.alias for alias in aliases)
            documents.append(
                CatalogVectorDocument(
                    id=product.code.value,
                    text=(
                        f"{product.name.value}. Codigo {product.code.value}. "
                        f"Categoria {product.category.value}. Aliases: {alias_text}"
                    ),
                    metadata={
                        "code": product.code.value,
                        "name": product.name.value,
                        "category": product.category.value,
                        "price_cop": product.price.amount,
                        "requires_age_verification": product.requires_age_verification,
                    },
                )
            )
        return documents

