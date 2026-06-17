import uuid

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.db_models import Stream, StreamStatus
from app.models.schemas import StreamCreate, StreamRead
from app.services.kinesis_service import KinesisVideoService

router = APIRouter(prefix="/streams", tags=["streams"])


@router.post("", response_model=StreamRead, status_code=status.HTTP_201_CREATED)
def create_stream(payload: StreamCreate, db: Session = Depends(get_db)) -> Stream:
    if db.query(Stream).filter(Stream.name == payload.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu isimde bir stream zaten mevcut.")

    kinesis_service = KinesisVideoService()
    try:
        stream_arn = kinesis_service.create_stream(payload.name)
    except (ClientError, BotoCoreError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AWS KVS hatasi: {exc}") from exc

    stream = Stream(name=payload.name, kvs_stream_arn=stream_arn, status=StreamStatus.ACTIVE)
    db.add(stream)
    db.commit()
    db.refresh(stream)
    return stream


@router.get("", response_model=list[StreamRead])
def list_streams(db: Session = Depends(get_db)) -> list[Stream]:
    return db.query(Stream).order_by(Stream.created_at.desc()).all()


@router.get("/{stream_id}", response_model=StreamRead)
def get_stream(stream_id: uuid.UUID, db: Session = Depends(get_db)) -> Stream:
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stream bulunamadi.")
    return stream


@router.post("/{stream_id}/stop", response_model=StreamRead)
def stop_stream(stream_id: uuid.UUID, db: Session = Depends(get_db)) -> Stream:
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stream bulunamadi.")
    stream.status = StreamStatus.STOPPED
    db.commit()
    db.refresh(stream)
    return stream


@router.delete("/{stream_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_stream(stream_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stream bulunamadi.")

    kinesis_service = KinesisVideoService()
    try:
        kinesis_service.delete_stream(stream.name)
    except (ClientError, BotoCoreError):
        pass  # AWS tarafinda zaten silinmis olabilir; yerel kaydi yine de temizle.

    db.delete(stream)
    db.commit()
