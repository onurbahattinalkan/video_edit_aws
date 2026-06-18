"""Kamera indeksi veya uzak bir video URL'si (HTTP(S)/RTSP/HLS) uzerinden
frame okuyan, ag kopmalarina ve gecersiz baglantilara karsi toleransli
video akis yardimcisi.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from types import TracebackType
from urllib.parse import urlparse

import cv2
import numpy as np

logger = logging.getLogger(__name__)

YOUTUBE_HOSTS = {"www.youtube.com", "youtube.com", "youtu.be", "m.youtube.com"}


class VideoStreamError(RuntimeError):
    """Video kaynagi acilamadi veya akis sirasinda kurtarilamaz bir hata olustu."""


def is_youtube_url(url: str) -> bool:
    return urlparse(url).netloc.lower() in YOUTUBE_HOSTS


def resolve_stream_url(url: str) -> str:
    """YouTube linklerini OpenCV'nin acabilecegi dogrudan video stream URL'sine cozer.

    YouTube disindaki linkler (dogrudan mp4/mkv dosyasi veya RTSP/HLS akisi)
    degistirilmeden geri dondurulur.
    """
    if not is_youtube_url(url):
        return url

    try:
        import yt_dlp
    except ImportError as exc:
        raise VideoStreamError(
            "YouTube linklerini cozmek icin 'yt-dlp' kutuphanesi gerekli ama yuklu degil."
        ) from exc

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best[ext=mp4][protocol^=https]/best[ext=mp4]/best",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise VideoStreamError(f"YouTube linki cozulemedi: {url} ({exc})") from exc

    stream_url = info.get("url") if info else None
    if not stream_url and info and info.get("formats"):
        stream_url = info["formats"][-1].get("url")
    if not stream_url:
        raise VideoStreamError(f"YouTube videosu icin oynatilabilir bir akis bulunamadi: {url}")

    logger.info("YouTube linki cozuldu: %s", url)
    return stream_url


class VideoStreamSimulator:
    """Kamera indeksi (int) veya video URL'si (str) kabul eden hata toleransli video kaynagi.

    - buffer_size: cv2.CAP_PROP_BUFFERSIZE; ag uzerindeki akislarda kare
      birikmesini/gecikmeyi azaltmak icin dusuk tutulur (varsayilan 1).
    - max_consecutive_failures: ust uste okunamayan frame sayisi bu degeri
      asarsa (ag kopmasi/timeout senaryosu) VideoStreamError firlatilir.
    """

    def __init__(
        self,
        source: int | str,
        frame_skip: int = 1,
        buffer_size: int = 1,
        max_consecutive_failures: int = 20,
    ) -> None:
        self.source = source
        self.frame_skip = max(1, frame_skip)
        self.max_consecutive_failures = max_consecutive_failures
        self._capture = self._open_capture(source, buffer_size)

    @staticmethod
    def _open_capture(source: int | str, buffer_size: int) -> cv2.VideoCapture:
        try:
            capture = cv2.VideoCapture(source)
        except cv2.error as exc:
            raise VideoStreamError(f"Video kaynagi acilirken OpenCV hatasi: {exc}") from exc

        if not capture.isOpened():
            raise VideoStreamError(
                f"Video kaynagi acilamadi (gecersiz URL, erisilemeyen kamera veya ag zaman asimi): {source}"
            )

        capture.set(cv2.CAP_PROP_BUFFERSIZE, buffer_size)
        logger.info("Video kaynagi acildi: %s", source)
        return capture

    def frames(self) -> Generator[np.ndarray, None, None]:
        """Kaynaktan sirayla frame uretir.

        Sonlu kaynaklarda (dosya/mp4) doga akisin sonuna gelindiginde sessizce
        durur; ag tabanli kaynaklarda (RTSP/HLS) ust uste okuma hatasi
        max_consecutive_failures'i asarsa VideoStreamError firlatir.
        """
        frame_index = 0
        consecutive_failures = 0
        total_frames = self._capture.get(cv2.CAP_PROP_FRAME_COUNT)
        logger.info("Video akisi baslatildi: %s", self.source)

        try:
            while True:
                try:
                    success, frame = self._capture.read()
                except cv2.error as exc:
                    logger.warning("Frame okuma sirasinda OpenCV hatasi: %s", exc)
                    success, frame = False, None

                if not success or frame is None:
                    if total_frames > 0 and self._capture.get(cv2.CAP_PROP_POS_FRAMES) >= total_frames:
                        logger.info("Video kaynagi sonuna ulasildi: %s", self.source)
                        break

                    consecutive_failures += 1
                    logger.warning(
                        "Frame okunamadi (ust uste hata: %s/%s) - kaynak: %s",
                        consecutive_failures,
                        self.max_consecutive_failures,
                        self.source,
                    )
                    if consecutive_failures >= self.max_consecutive_failures:
                        raise VideoStreamError(
                            f"Video kaynagindan {self.max_consecutive_failures} kez ust uste frame "
                            f"okunamadi (ag kopmasi veya bozuk baglanti olabilir): {self.source}"
                        )
                    time.sleep(0.5)
                    continue

                consecutive_failures = 0
                if frame_index % self.frame_skip == 0:
                    yield frame
                frame_index += 1
        finally:
            self.release()
            logger.info("Video akisi sonlandi (toplam %s frame islendi): %s", frame_index, self.source)

    def release(self) -> None:
        if self._capture is not None and self._capture.isOpened():
            self._capture.release()

    def __enter__(self) -> "VideoStreamSimulator":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()
