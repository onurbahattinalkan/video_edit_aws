from fastapi import APIRouter

from app.api.v1 import analysis, streams

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(streams.router)
api_router.include_router(analysis.router)
