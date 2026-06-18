"""Kullanicinin verdigi video URL'sinden (mp4/mkv dosyasi veya RTSP/HLS canli
yayin) Rekognition ile analiz yapan ve MJPEG olarak yayinlayan API rotalari.
"""

import logging
import uuid
from collections.abc import Generator

import cv2
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.database import SessionLocal
from app.models.db_models import Stream, StreamStatus
from app.models.schemas import StreamURLRequest
from app.services.analysis_service import AnalysisService
from app.services.rekognition_service import RekognitionService
from app.utils.video_helper import VideoStreamError, VideoStreamSimulator, resolve_stream_url
from app.utils.video_utils import frame_to_jpeg_bytes

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])

MJPEG_BOUNDARY = "frame"


def _run_url_stream_analysis(stream_id: uuid.UUID, video_url: str, frame_skip: int, include_faces: bool) -> None:
    """Arka planda video URL'sinden frame okuyup Rekognition ile analiz eden gorev.

    Request-scoped DB oturumu yanit donduktan sonra kapandigi icin bu gorev
    kendi veritabani oturumunu acar ve isi bittiginde kapatir.
    """
    db = SessionLocal()
    stream = db.get(Stream, stream_id)
    if not stream:
        logger.error("Arka plan analizi icin stream bulunamadi: %s", stream_id)
        db.close()
        return

    analyzed_frame_count = 0
    try:
        stream.status = StreamStatus.ACTIVE
        db.commit()
        logger.info("Stream %s icin URL analizi baslatildi: %s", stream_id, video_url)

        analysis_service = AnalysisService(db)
        resolved_url = resolve_stream_url(video_url)
        with VideoStreamSimulator(resolved_url, frame_skip=frame_skip) as simulator:
            for frame in simulator.frames():
                db.refresh(stream)
                if stream.status == StreamStatus.STOPPED:
                    logger.info("Durdurma istegi alindi, analiz sonlandiriliyor: stream_id=%s", stream_id)
                    break

                jpeg_bytes = frame_to_jpeg_bytes(frame)
                results = analysis_service.analyze_frame(stream_id, jpeg_bytes, include_faces=include_faces)
                analyzed_frame_count += 1
                logger.info(
                    "Stream %s: frame #%s analiz edildi, %s sonuc kaydedildi.",
                    stream_id,
                    analyzed_frame_count,
                    len(results),
                )

        db.refresh(stream)
        if stream.status != StreamStatus.STOPPED:
            stream.status = StreamStatus.STOPPED
            db.commit()
        logger.info(
            "Stream %s icin URL analizi tamamlandi (toplam %s frame analiz edildi).",
            stream_id,
            analyzed_frame_count,
        )
    except VideoStreamError as exc:
        logger.error("Stream %s icin video kaynagi hatasi: %s", stream_id, exc)
        stream.status = StreamStatus.FAILED
        db.commit()
    except Exception:
        logger.exception("Stream %s icin arka plan analizi sirasinda beklenmeyen hata.", stream_id)
        stream.status = StreamStatus.FAILED
        db.commit()
    finally:
        db.close()


@router.post("/start-analysis", status_code=status.HTTP_202_ACCEPTED)
def start_analysis(
    payload: StreamURLRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Verilen video URL'sinden frame okuyup Rekognition ile analiz etmeyi arka planda baslatir."""
    if payload.stream_id:
        stream = db.get(Stream, payload.stream_id)
        if not stream:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Stream bulunamadi.")
    else:
        stream = Stream(name=f"url-stream-{uuid.uuid4().hex[:8]}", status=StreamStatus.CREATED)
        db.add(stream)
        db.commit()
        db.refresh(stream)

    background_tasks.add_task(
        _run_url_stream_analysis, stream.id, payload.video_url, payload.frame_skip, payload.include_faces
    )

    logger.info("URL tabanli video analizi planlandi: stream_id=%s, video_url=%s", stream.id, payload.video_url)
    return {"stream_id": stream.id, "status": "scheduled", "video_url": payload.video_url}


def _draw_label_overlay(frame: cv2.Mat, labels: list[dict]) -> cv2.Mat:
    overlay = frame.copy()
    y = 30
    for label_data in labels[:8]:
        text = f"{label_data['label']} ({label_data['confidence']:.1f}%)"
        cv2.putText(overlay, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
        y += 25
    return overlay


def _mjpeg_generator(
    video_url: str, frame_skip: int, analysis_interval: int, stream_id: uuid.UUID | None
) -> Generator[bytes, None, None]:
    rekognition_service = RekognitionService()
    persist_db = SessionLocal() if stream_id else None
    analysis_service = AnalysisService(persist_db) if persist_db else None

    current_labels: list[dict] = []
    frame_counter = 0

    try:
        resolved_url = resolve_stream_url(video_url)
        with VideoStreamSimulator(resolved_url, frame_skip=frame_skip) as simulator:
            for frame in simulator.frames():
                if frame_counter % analysis_interval == 0:
                    try:
                        jpeg_bytes = frame_to_jpeg_bytes(frame)
                        current_labels = rekognition_service.detect_labels(jpeg_bytes)
                        if analysis_service and stream_id:
                            analysis_service.analyze_frame(stream_id, jpeg_bytes)
                        logger.info(
                            "video-feed: frame #%s analiz edildi, %s etiket bulundu.",
                            frame_counter,
                            len(current_labels),
                        )
                    except Exception:
                        logger.exception("video-feed: frame analizi basarisiz, onceki etiketler kullaniliyor.")

                overlay_frame = _draw_label_overlay(frame, current_labels)
                jpeg_chunk = frame_to_jpeg_bytes(overlay_frame)
                yield (
                    b"--" + MJPEG_BOUNDARY.encode() + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg_chunk)).encode() + b"\r\n\r\n" + jpeg_chunk + b"\r\n"
                )
                frame_counter += 1
    except VideoStreamError as exc:
        logger.error("video-feed: video kaynagi hatasi: %s", exc)
    finally:
        if persist_db:
            persist_db.close()
        logger.info("video-feed akisi sonlandi: %s", video_url)


@router.get("/video-feed")
def video_feed(
    video_url: str = Query(..., description="MJPEG olarak yayinlanacak video URL'si (HTTP(S)/RTSP/HLS)"),
    stream_id: uuid.UUID | None = Query(None, description="Sonuclarin kaydedilecegi mevcut stream id'si"),
    frame_skip: int = Query(1, ge=1, le=60, description="Goruntude her N frame'den birini gosterir"),
    analysis_interval: int = Query(
        15, ge=1, le=300, description="Goruntulenen her N frame'de bir Rekognition cagrisi yapar"
    ),
) -> StreamingResponse:
    return StreamingResponse(
        _mjpeg_generator(video_url, frame_skip, analysis_interval, stream_id),
        media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}",
    )
