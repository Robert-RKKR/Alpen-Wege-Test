# Third-party
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application configuration, loaded from environment variables / a .env file.
    # Each attribute below is an overridable setting with a sensible default.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "Alpen Wege"
    DEBUG: bool = False

    DATABASE_URL: str = (
        "postgresql+asyncpg://alpenwege:alpenwege@localhost:5433/alpenwege"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql+psycopg2://alpenwege:alpenwege@localhost:5433/alpenwege"
    )

    REDIS_URL: str = "redis://localhost:6379/2"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 5

    FIRST_ADMIN_EMAIL: str | None = None


def get_settings() -> Settings:
    # Build and return the application settings.
    # Params: none.
    # Returns: a Settings instance populated from the environment / .env file.
    return Settings()
