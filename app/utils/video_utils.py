"""OpenCV tabanli video/frame yardimci fonksiyonlari.

Gercek bir KVS donanim entegrasyonu olmadan, yerel bir video dosyasi veya
webcam uzerinden frame okuyup bunlari Rekognition'a gonderilebilecek JPEG
byte dizilerine cevirerek video akisini simule etmek icin kullanilir.
"""

from collections.abc import Generator

import cv2
import numpy as np


def frame_to_jpeg_bytes(frame: np.ndarray, quality: int = 90) -> bytes:
    """Bir OpenCV frame'ini (BGR ndarray) JPEG byte dizisine cevirir."""
    success, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not success:
        raise ValueError("Frame JPEG formatina kodlanamadi.")
    return buffer.tobytes()


def iter_video_frames(source: str | int, frame_skip: int = 1) -> Generator[np.ndarray, None, None]:
    """Bir video dosyasindan veya kameradan (source=0) frame'leri sirayla uretir.

    frame_skip: Her N frame'den birini almak icin kullanilir (ornegin Rekognition
    cagri sayisini/sismani azaltmak amaciyla).
    """
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise RuntimeError(f"Video kaynagi acilamadi: {source}")

    frame_index = 0
    try:
        while True:
            success, frame = capture.read()
            if not success:
                break
            if frame_index % frame_skip == 0:
                yield frame
            frame_index += 1
    finally:
        capture.release()


def read_single_frame(source: str | int) -> np.ndarray:
    """Bir video kaynagindan ilk frame'i okur (hizli analiz/test amacli)."""
    capture = cv2.VideoCapture(source)
    try:
        if not capture.isOpened():
            raise RuntimeError(f"Video kaynagi acilamadi: {source}")
        success, frame = capture.read()
        if not success:
            raise RuntimeError("Video kaynagindan frame okunamadi.")
        return frame
    finally:
        capture.release()
