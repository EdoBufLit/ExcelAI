from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


@dataclass(slots=True)
class Settings:
    app_name: str = "Excel AI Transformer API"
    app_version: str = "0.1.0"
    data_dir: Path = Path("data")
    usage_db_path: Path = Path("data/usage.db")
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str | None = None
    max_free_uses: int = 5
    preview_rows: int = 15
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @classmethod
    def from_env(cls) -> "Settings":
        base_dir = Path(__file__).resolve().parent.parent
        data_dir_raw = os.getenv("DATA_DIR", str(base_dir / "data"))
        usage_db_raw = os.getenv("USAGE_DB_PATH", str(Path(data_dir_raw) / "usage.db"))
        cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

        llm_api_key = _first_env("LLM_API_KEY", "OPENAI_API_KEY", "KIMI_API_KEY")
        llm_model = _first_env("LLM_MODEL", "OPENAI_MODEL", "KIMI_MODEL") or "gpt-4.1-mini"
        llm_base_url = _first_env("LLM_BASE_URL", "OPENAI_BASE_URL", "KIMI_BASE_URL")

        return cls(
            data_dir=Path(data_dir_raw),
            usage_db_path=Path(usage_db_raw),
            openai_api_key=llm_api_key,
            openai_model=llm_model,
            openai_base_url=llm_base_url,
            max_free_uses=int(os.getenv("MAX_FREE_USES", "5")),
            preview_rows=int(os.getenv("PREVIEW_ROWS", "15")),
            cors_origins=_split_csv(cors_raw),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.usage_db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
