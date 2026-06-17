from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Uygulama genelinde kullanilan ayarlar. Degerler .env dosyasindan okunur."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AWS
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "eu-central-1"

    # Kinesis Video Streams
    kvs_stream_name: str = "demo-video-stream"

    # Rekognition
    rekognition_min_confidence: float = 80.0
    rekognition_max_labels: int = 10

    # Veritabani
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/video_stream_db"

    # Uygulama
    app_env: str = "development"
    app_debug: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
