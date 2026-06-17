import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.db_models import AnalysisType, StreamStatus


class StreamCreate(BaseModel):
    name: str


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
