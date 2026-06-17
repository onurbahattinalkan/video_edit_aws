from app.services.kinesis_service import KinesisVideoService


def test_create_and_list_stream(client, monkeypatch):
    monkeypatch.setattr(
        KinesisVideoService, "create_stream", lambda self, name, **kwargs: "arn:aws:kinesisvideo:fake"
    )

    response = client.post("/api/v1/streams", json={"name": "test-stream"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "test-stream"
    assert body["status"] == "ACTIVE"

    list_response = client.get("/api/v1/streams")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_create_duplicate_stream_fails(client, monkeypatch):
    monkeypatch.setattr(
        KinesisVideoService, "create_stream", lambda self, name, **kwargs: "arn:aws:kinesisvideo:fake"
    )

    client.post("/api/v1/streams", json={"name": "dup-stream"})
    response = client.post("/api/v1/streams", json={"name": "dup-stream"})
    assert response.status_code == 409


def test_get_missing_stream_returns_404(client):
    response = client.get("/api/v1/streams/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_stop_stream(client, monkeypatch):
    monkeypatch.setattr(
        KinesisVideoService, "create_stream", lambda self, name, **kwargs: "arn:aws:kinesisvideo:fake"
    )
    created = client.post("/api/v1/streams", json={"name": "stoppable-stream"}).json()

    response = client.post(f"/api/v1/streams/{created['id']}/stop")
    assert response.status_code == 200
    assert response.json()["status"] == "STOPPED"
