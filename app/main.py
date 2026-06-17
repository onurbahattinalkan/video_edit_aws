from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings

app = FastAPI(
    title="AWS Video Akisi ve Isleme Uygulamasi",
    description=(
        "AWS Kinesis Video Streams ve AWS Rekognition kullanarak gercek "
        "zamanli video akisi yonetimi ve yapay zeka tabanli video analizi "
        "saglayan backend servisi."
    ),
    version="1.0.0",
)

app.include_router(api_router)


@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok", "environment": settings.app_env}
