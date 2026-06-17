import numpy as np

from app.utils.video_utils import frame_to_jpeg_bytes


def test_frame_to_jpeg_bytes_returns_valid_jpeg():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    jpeg_bytes = frame_to_jpeg_bytes(frame)

    assert isinstance(jpeg_bytes, bytes)
    assert jpeg_bytes[:2] == b"\xff\xd8"  # JPEG magic bytes
