"""AWS Rekognition ile goruntu/frame analizi yapan servis katmani."""

import logging

from app.core.aws import get_rekognition_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class RekognitionService:
    def __init__(self) -> None:
        self.client = get_rekognition_client()

    def detect_labels(self, image_bytes: bytes) -> list[dict]:
        """Goruntudeki nesneleri/etiketleri tespit eder.

        Donus: [{"label": str, "confidence": float, "raw": dict}, ...]
        """
        response = self.client.detect_labels(
            Image={"Bytes": image_bytes},
            MaxLabels=settings.rekognition_max_labels,
            MinConfidence=settings.rekognition_min_confidence,
        )
        return [
            {
                "label": item["Name"],
                "confidence": item["Confidence"],
                "raw": item,
            }
            for item in response.get("Labels", [])
        ]

    def detect_faces(self, image_bytes: bytes) -> list[dict]:
        """Goruntudeki yuzleri ve oznitelliklerini (yas araligi, duygu vb.) tespit eder."""
        response = self.client.detect_faces(Image={"Bytes": image_bytes}, Attributes=["ALL"])
        results = []
        for face in response.get("FaceDetails", []):
            top_emotion = max(face.get("Emotions", []), key=lambda e: e["Confidence"], default=None)
            results.append(
                {
                    "label": top_emotion["Type"] if top_emotion else "FACE",
                    "confidence": face["Confidence"],
                    "raw": face,
                }
            )
        return results
