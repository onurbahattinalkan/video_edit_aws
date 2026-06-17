from functools import lru_cache

import boto3

from app.core.config import settings


def _client_kwargs() -> dict:
    """boto3 istemcileri icin ortak kwarg seti.

    Access key/secret tanimli degilse boto3'un varsayilan kimlik bilgisi
    zincirine (IAM Role, ~/.aws/credentials, env var) dusulur.
    """
    kwargs = {"region_name": settings.aws_region}
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return kwargs


@lru_cache
def get_kinesis_video_client():
    """Kinesis Video Streams kontrol-plane istemcisi (stream olusturma/listeleme)."""
    return boto3.client("kinesisvideo", **_client_kwargs())


def get_kinesis_video_media_client(endpoint_url: str):
    """Belirli bir stream'in data-plane endpoint'ine baglanan istemci (PutMedia/GetMedia icin)."""
    return boto3.client("kinesis-video-media", endpoint_url=endpoint_url, **_client_kwargs())


@lru_cache
def get_rekognition_client():
    return boto3.client("rekognition", **_client_kwargs())
