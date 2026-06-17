"""AWS Kinesis Video Streams (KVS) ile etkilesim icin servis katmani.

Bu modul KVS kontrol-plane islemlerini (stream olusturma, silme, endpoint
alma) kapsar. Gercek video gonderimi (PutMedia) genelde donanim/SDK tarafli
(GStreamer, AWS KVS Producer SDK) yapilir; burada API uzerinden stream
yonetimini ve simule edilmis veri akisini saglamaya odaklaniyoruz.
"""

import logging

from botocore.exceptions import ClientError

from app.core.aws import get_kinesis_video_client

logger = logging.getLogger(__name__)


class KinesisVideoService:
    def __init__(self) -> None:
        self.client = get_kinesis_video_client()

    def create_stream(self, stream_name: str, data_retention_hours: int = 24) -> str:
        """KVS uzerinde yeni bir video stream olusturur ve ARN'ini dondurur."""
        try:
            response = self.client.create_stream(
                StreamName=stream_name,
                DataRetentionInHours=data_retention_hours,
                MediaType="video/h264",
            )
            return response["StreamARN"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ResourceInUseException":
                logger.info("Stream '%s' zaten mevcut, mevcut ARN aliniyor.", stream_name)
                return self.describe_stream(stream_name)["StreamInfo"]["StreamARN"]
            raise

    def describe_stream(self, stream_name: str) -> dict:
        return self.client.describe_stream(StreamName=stream_name)

    def get_data_endpoint(self, stream_name: str, api_name: str = "PUT_MEDIA") -> str:
        """Belirtilen islem (PutMedia/GetMedia) icin data-plane endpoint'ini dondurur."""
        response = self.client.get_data_endpoint(StreamName=stream_name, APIName=api_name)
        return response["DataEndpoint"]

    def delete_stream(self, stream_name: str) -> None:
        stream_arn = self.describe_stream(stream_name)["StreamInfo"]["StreamARN"]
        self.client.delete_stream(StreamARN=stream_arn)

    def list_streams(self) -> list[dict]:
        response = self.client.list_streams()
        return response.get("StreamInfoList", [])
