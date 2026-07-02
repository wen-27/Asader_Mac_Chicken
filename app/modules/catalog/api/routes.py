"""FastAPI router for this module. Keep controllers thin and delegate real work to application services."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.modules.catalog.application.vector_indexer import CatalogVectorDocumentBuilder
from app.modules.catalog.infrastructure.chroma.chroma_catalog_vector_store import (
    ChromaCatalogVectorStore,
)
from app.modules.catalog.infrastructure.sqlalchemy_product_repository import (
    SqlAlchemyProductAliasRepository,
    SqlAlchemyProductRepository,
)
from app.shared.infrastructure.database.session import get_async_session

router = APIRouter(prefix="/admin/catalog", tags=["admin-catalog"])


@router.post("/reindex-vector-store", status_code=status.HTTP_200_OK)
async def reindex_catalog_vector_store(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, int | bool]:
    builder = CatalogVectorDocumentBuilder(
        products=SqlAlchemyProductRepository(session),
        aliases=SqlAlchemyProductAliasRepository(session),
    )
    documents = await builder.build_documents()
    indexed_count = await ChromaCatalogVectorStore(settings).reindex(documents)
    return {"ok": True, "indexed_count": indexed_count}

