from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./app.db"
    llm_provider: str = "mock"  # "gemini" or "mock"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2  # extra tries for temporary provider problems (503, 429, timeouts)
    analyze_rate_limit_per_minute: int = 10
    frontend_dist: str = "../frontend/dist"
    log_level: str = "INFO"

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url.strip()
        # Neon/Heroku style URLs use "postgres://" and plain "postgresql://" leaves the driver to SQLAlchemy.
        # SQLAlchemy 2.1+ then picks psycopg v3, but this app installs psycopg2, so name the driver explicitly.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg2://" + url[len(prefix):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
