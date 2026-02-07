from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.services.analytics_logger import AnalyticsLogger
from app.services.file_store import FileStore
from app.services.llm_planner import LLMPlanner
from app.services.usage_limiter import UsageLimiter


@dataclass(slots=True)
class ServiceContainer:
    file_store: FileStore
    usage_limiter: UsageLimiter
    llm_planner: LLMPlanner
    analytics_logger: AnalyticsLogger


def build_services(settings: Settings) -> ServiceContainer:
    return ServiceContainer(
        file_store=FileStore(settings.data_dir),
        usage_limiter=UsageLimiter(settings.usage_db_path, settings.max_free_uses),
        llm_planner=LLMPlanner(
            settings.openai_api_key,
            settings.openai_model,
            settings.openai_base_url,
        ),
        analytics_logger=AnalyticsLogger(settings.usage_db_path),
    )
