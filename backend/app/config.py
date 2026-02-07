from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    app_name: str = "Excel AI Transformer API"
    app_version: str = "0.1.0"
    data_dir: Path = Path("data")
    usage_db_path: Path = Path("data/usage.db")
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
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

        return cls(
            data_dir=Path(data_dir_raw),
            usage_db_path=Path(usage_db_raw),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
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
