import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.db_models import AnalysisResult, Stream
from app.models.schemas import AnalysisResultRead, AnalyzeFrameResponse
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/{stream_id}/analyze-frame", response_model=AnalyzeFrameResponse)
async def analyze_frame(
    stream_id: uuid.UUID,
    file: UploadFile = File(..., description="Analiz edilecek tek bir JPEG/PNG frame goruntusu"),
    include_faces: bool = Query(False, description="Yuz/duygu analizini de calistir"),
    db: Session = Depends(get_db),
) -> AnalyzeFrameResponse:
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stream bulunamadi.")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bos goruntu dosyasi.")

    analysis_service = AnalysisService(db)
    results = analysis_service.analyze_frame(stream_id, image_bytes, include_faces=include_faces)

    return AnalyzeFrameResponse(stream_id=stream_id, results=results)


@router.get("/{stream_id}/results", response_model=list[AnalysisResultRead])
def get_results(stream_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AnalysisResult]:
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stream bulunamadi.")

    return (
        db.query(AnalysisResult)
        .filter(AnalysisResult.stream_id == stream_id)
        .order_by(AnalysisResult.created_at.desc())
        .all()
    )
