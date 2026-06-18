import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.db_models import AnalysisType, StreamStatus

VALID_VIDEO_URL_SCHEMES = {"http", "https", "rtsp"}


class StreamCreate(BaseModel):
    name: str


class StreamURLRequest(BaseModel):
    """Kullanicinin verdigi bir video URL'sinden (mp4/mkv dosyasi veya RTSP/HLS
    canli yayin baglantisi) Rekognition analizi baslatmak icin kullanilan istek govdesi."""

    video_url: str = Field(..., description="Analiz edilecek video dosyasi veya canli yayin baglantisi (HTTP(S)/RTSP)")
    stream_id: uuid.UUID | None = Field(
        None, description="Var olan bir stream'in id'si; verilmezse video_url icin otomatik bir stream olusturulur."
    )
    frame_skip: int = Field(10, ge=1, le=300, description="Rekognition'a gonderilecek frame araligi (her N frame'den biri)")
    include_faces: bool = Field(False, description="Yuz/duygu analizini de calistir")

    @field_validator("video_url")
    @classmethod
    def validate_video_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in VALID_VIDEO_URL_SCHEMES or not parsed.netloc:
            raise ValueError(
                f"video_url gecerli bir baglanti olmalidir (beklenen semalar: {', '.join(sorted(VALID_VIDEO_URL_SCHEMES))})."
            )
        return value


class StreamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kvs_stream_arn: str | None
    status: StreamStatus
    created_at: datetime


class AnalysisResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stream_id: uuid.UUID
    analysis_type: AnalysisType
    label: str
    confidence: float
    raw_data: dict
    created_at: datetime


class AnalyzeFrameResponse(BaseModel):
    stream_id: uuid.UUID
    results: list[AnalysisResultRead]
