from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_data_dir: Path = Path("data")
    export_dir: Path = Path("exports")
    claude_bin: str = "claude"
    claude_timeout_seconds: int = 180
    claude_max_budget_usd: float | None = None
    default_query_limit: int = 500
    mysql_query_timeout_seconds: int = 30
    sample_rows: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
    )

    @field_validator("claude_max_budget_usd", mode="before")
    @classmethod
    def empty_budget_is_none(cls, value):
        if value == "":
            return None
        return value

    @property
    def sqlite_path(self) -> Path:
        return self.app_data_dir / "app.sqlite3"

    def ensure_dirs(self) -> None:
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
