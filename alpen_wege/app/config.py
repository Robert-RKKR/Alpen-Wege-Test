# Third-party
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application configuration, loaded from environment variables / a .env
    # file.
    # Each attribute below is an overridable setting with a sensible default.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8"
    )

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
    JWT_EXPIRE_MINUTES: int = 60

    FIRST_ADMIN_EMAIL: str | None = None

    # GPX storage and upload
    GPX_STORAGE_DIR: str = "/data/gpx"
    GPX_MAX_UPLOAD_MB: int = 20

    # GPX cleaning thresholds
    GPX_MAX_SPEED_MS: float = 70.0
    GPX_MAX_GAP_NO_TIME_M: float = 5000.0
    GPX_SEGMENT_GAP_S: float = 300.0
    GPX_SEGMENT_GAP_MIN_M: float = 100.0
    GPX_MOVING_SPEED_MS: float = 0.5
    GPX_TIMESTAMP_MIN_YEAR: int = 2000
    GPX_TIMESTAMP_MAX_FUTURE_DAYS: int = 1

    # Elevation processing
    ELEVATION_MEDIAN_WINDOW: int = 5
    ELEVATION_THRESHOLD_M: float = 3.0
    GRADE_WINDOW_M: float = 50.0

    # Output shaping
    GEOJSON_MAX_POINTS: int = 1000
    GEOJSON_COORD_DECIMALS: int = 5
    GRAPH_MAX_POINTS: int = 300
    ROUTE_SIMPLIFY_TOLERANCE_M: float = 5.0

    # POI detection
    POI_COLLECT_RADIUS_M: float = 50.0
    POI_DETECTION_REQUIRES_TIMESTAMPS: bool = True
    RESCAN_LOCK_SECONDS: int = 1860

    # Processing lifecycle
    STUCK_PENDING_MINUTES: int = 5
    STUCK_PROCESSING_MINUTES: int = 30
    STUCK_MAX_ATTEMPTS: int = 3
    STATS_RECOMPUTE_DELAY_S: int = 5

    @field_validator("ELEVATION_MEDIAN_WINDOW")
    @classmethod
    def _odd_window(cls, v: int) -> int:
        if v < 1:
            raise ValueError("ELEVATION_MEDIAN_WINDOW must be at least 1")
        if v % 2 == 0:
            return v + 1
        return v


def get_settings() -> Settings:
    # Build and return the application settings.
    # Params: none.
    # Returns: a Settings instance populated from the environment / .env file.
    return Settings()
