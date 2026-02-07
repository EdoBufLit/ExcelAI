from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.routers.transform import router as transform_router
from app.services.container import build_services

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    app = FastAPI(title=active_settings.app_name, version=active_settings.app_version)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = active_settings
    app.state.services = build_services(active_settings)
    log_message = "LLM provider configured: provider=%s model=%s base_url=%s"
    log_args = (
        app.state.services.llm_planner.provider,
        app.state.services.llm_planner.model,
        app.state.services.llm_planner.base_url or "(default)",
    )
    logger.info(log_message, *log_args)
    print(log_message % log_args)
    app.include_router(transform_router)

    @app.get("/health", tags=["system"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
