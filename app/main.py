"""FastAPI application factory: wires routers, logging and health endpoints without putting business rules in the web layer."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.logging import configure_logging
from app.config.settings import get_settings
from app.modules.admin.api.routes import router as admin_router, ws_router
from app.modules.catalog.api.routes import router as catalog_admin_router
from app.modules.internal.routes import router as internal_router
from app.modules.orders.application.payment_proofs import run_payment_proof_reminder_loop
from app.modules.telegram.api.routes import router as telegram_router
from app.modules.whatsapp.api.routes import router as whatsapp_router
from app.shared.infrastructure.health import check_chromadb, check_postgres, check_redis


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
        }

    @app.get("/health/dependencies", tags=["system"])
    async def health_dependencies() -> dict[str, object]:
        postgres_ok = await check_postgres()
        redis_ok = await check_redis(settings)
        chromadb_ok = await check_chromadb(settings)
        return {
            "status": "ok" if all([postgres_ok, redis_ok, chromadb_ok]) else "degraded",
            "dependencies": {
                "postgres": postgres_ok,
                "redis": redis_ok,
                "chromadb": chromadb_ok,
            },
        }

    @app.on_event("startup")
    async def start_payment_proof_reminders() -> None:
        stop_event = asyncio.Event()
        app.state.payment_proof_reminder_stop = stop_event
        app.state.payment_proof_reminder_task = asyncio.create_task(
            run_payment_proof_reminder_loop(settings, stop_event)
        )

    @app.on_event("shutdown")
    async def stop_payment_proof_reminders() -> None:
        stop_event = getattr(app.state, "payment_proof_reminder_stop", None)
        task = getattr(app.state, "payment_proof_reminder_task", None)
        if stop_event is not None:
            stop_event.set()
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app.include_router(whatsapp_router)
    app.include_router(telegram_router)
    app.include_router(admin_router)
    app.include_router(ws_router)
    app.include_router(catalog_admin_router)
    app.include_router(internal_router)

    return app


app = create_app()
