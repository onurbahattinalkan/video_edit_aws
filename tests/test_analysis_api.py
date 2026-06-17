import io

from app.services.kinesis_service import KinesisVideoService
from app.services.rekognition_service import RekognitionService


def _create_stream(client, monkeypatch, name="analysis-stream"):
    monkeypatch.setattr(
        KinesisVideoService, "create_stream", lambda self, n, **kwargs: "arn:aws:kinesisvideo:fake"
    )
    return client.post("/api/v1/streams", json={"name": name}).json()


def test_analyze_frame_returns_labels(client, monkeypatch):
    stream = _create_stream(client, monkeypatch)

    monkeypatch.setattr(
        RekognitionService,
        "detect_labels",
        lambda self, image_bytes: [{"label": "Car", "confidence": 98.5, "raw": {"Name": "Car"}}],
    )
    monkeypatch.setattr(RekognitionService, "detect_faces", lambda self, image_bytes: [])

    fake_image = io.BytesIO(b"fake-jpeg-bytes")
    response = client.post(
        f"/api/v1/analysis/{stream['id']}/analyze-frame",
        files={"file": ("frame.jpg", fake_image, "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["label"] == "Car"

    results_response = client.get(f"/api/v1/analysis/{stream['id']}/results")
    assert results_response.status_code == 200
    assert len(results_response.json()) == 1


def test_analyze_frame_missing_stream_returns_404(client):
    fake_image = io.BytesIO(b"fake-jpeg-bytes")
    response = client.post(
        "/api/v1/analysis/00000000-0000-0000-0000-000000000000/analyze-frame",
        files={"file": ("frame.jpg", fake_image, "image/jpeg")},
    )
    assert response.status_code == 404
