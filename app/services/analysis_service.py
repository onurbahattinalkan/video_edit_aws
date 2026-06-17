"""Frame analizini Rekognition ile yapip sonuclari veritabanina kaydeden orkestrasyon servisi."""

import uuid

from sqlalchemy.orm import Session

from app.models.db_models import AnalysisResult, AnalysisType
from app.services.rekognition_service import RekognitionService


class AnalysisService:
    def __init__(self, db: Session, rekognition_service: RekognitionService | None = None) -> None:
        self.db = db
        self.rekognition_service = rekognition_service or RekognitionService()

    def analyze_frame(
        self, stream_id: uuid.UUID, image_bytes: bytes, include_faces: bool = False
    ) -> list[AnalysisResult]:
        results: list[AnalysisResult] = []

        for label_data in self.rekognition_service.detect_labels(image_bytes):
            results.append(
                AnalysisResult(
                    stream_id=stream_id,
                    analysis_type=AnalysisType.LABEL,
                    label=label_data["label"],
                    confidence=label_data["confidence"],
                    raw_data=label_data["raw"],
                )
            )

        if include_faces:
            for face_data in self.rekognition_service.detect_faces(image_bytes):
                results.append(
                    AnalysisResult(
                        stream_id=stream_id,
                        analysis_type=AnalysisType.FACE,
                        label=face_data["label"],
                        confidence=face_data["confidence"],
                        raw_data=face_data["raw"],
                    )
                )

        self.db.add_all(results)
        self.db.commit()
        for result in results:
            self.db.refresh(result)

        return results
