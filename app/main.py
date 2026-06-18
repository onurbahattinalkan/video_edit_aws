import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

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
app.mount("/ui", StaticFiles(directory="app/static", html=True), name="ui")


@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok", "environment": settings.app_env}
