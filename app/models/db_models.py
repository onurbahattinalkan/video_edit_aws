import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StreamStatus(str, enum.Enum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class AnalysisType(str, enum.Enum):
    LABEL = "LABEL"
    FACE = "FACE"


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    kvs_stream_arn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[StreamStatus] = mapped_column(
        Enum(StreamStatus, native_enum=False), default=StreamStatus.CREATED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis_results: Mapped[list["AnalysisResult"]] = relationship(
        back_populates="stream", cascade="all, delete-orphan"
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    stream_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"))
    analysis_type: Mapped[AnalysisType] = mapped_column(Enum(AnalysisType, native_enum=False))
    label: Mapped[str] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Float)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stream: Mapped["Stream"] = relationship(back_populates="analysis_results")
