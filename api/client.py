import os
import random
from typing import Optional, Any, Dict

import requests
import json
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from PySide6.QtCore import QObject, Signal, QRunnable

from core.ffmpeg_utils import get_media_info

# ==============================================================================
#  API Constants and Helpers
# ==============================================================================

ELEVENLABS_STT_API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_STT_PARAMS = {"allow_unauthenticated": "1"}
DEFAULT_STT_MODEL_ID = "scribe_v1"
# --- Header Configuration ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
]
ACCEPT_LANGUAGES = [
    "zh-CN,zh;q=0.9,en;q=0.8", "en-US,en;q=0.9,es;q=0.8", "en-GB,en;q=0.9",
    "ja-JP,ja;q=0.9,en;q=0.8", "ko-KR,ko;q=0.9,en;q=0.8", "de-DE,de;q=0.9,en;q=0.8",
    "fr-FR,fr;q=0.9,en;q=0.8", "en-US,en;q=0.5",
]
BASE_HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "origin": "https://elevenlabs.io",
    "referer": "https://elevenlabs.io/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}

class UploaderSignals(QObject):
    """Defines the signals available from a running Uploader thread."""
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(int, int)

class Uploader(QRunnable):
    """Runnable that handles the blocking network request."""
    def __init__(self, file_path: str, payload: Dict, headers: Dict):
        super().__init__()
        self.signals = UploaderSignals()
        self.file_path = file_path
        self.payload = payload
        self.headers = headers
        self.session = requests.Session()
        self._is_cancelled = False

    def run(self):
        """The main work of the uploader thread."""
        try:
            # *** BUG FIX: Open the file within the thread that uses it ***
            with open(self.file_path, 'rb') as f_audio:
                # Update payload with the file object
                self.payload['file'] = (os.path.basename(self.file_path), f_audio, self.payload['file'][2])

                encoder = MultipartEncoder(fields=self.payload)
                monitor = MultipartEncoderMonitor(encoder, self.progress_callback)

                self.headers['Content-Type'] = monitor.content_type

                response = self.session.post(
                    ELEVENLABS_STT_API_URL,
                    params=ELEVENLABS_STT_PARAMS,
                    headers=self.headers,
                    data=monitor,
                    timeout=1800
                )
                response.raise_for_status()
                self.signals.finished.emit(response.json())

        except Exception as e:
            if not self._is_cancelled:
                self.signals.error.emit(f"上传或转录失败: {e}")

    def progress_callback(self, monitor):
        if self._is_cancelled:
            # This will cause the session.post() to raise an exception.
            raise IOError("Upload cancelled by user.")
        self.signals.progress.emit(monitor.bytes_read, monitor.len)
        
    def cancel(self):
        """Cancels the upload."""
        self._is_cancelled = True
        self.signals.error.emit("任务被用户取消。")
        # Closing the session will interrupt the blocking post call
        self.session.close()

class ElevenLabsSTTClient:
    """Client to interact with the ElevenLabs Speech-to-Text API."""
    def __init__(self, signals_forwarder: Optional[QObject] = None, ffmpeg_available: bool = False):
        self._signals = signals_forwarder
        self.ffmpeg_available = ffmpeg_available

    def _log(self, message: str):
        if self._signals and hasattr(self._signals, 'log_message'):
            self._signals.log_message.emit(f"{message}")

    def log_media_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Logs file size and, if possible, media duration and codec."""
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            log_str = f"  文件大小: {file_size_mb:.2f} MB"

            media_info = get_media_info(file_path, self._log)
            if media_info:
                duration = media_info.get("duration")
                codec = media_info.get("codec")
                if duration:
                    minutes, seconds = divmod(duration, 60)
                    log_str += f" | 时长: {int(minutes):02d}分{int(seconds):02d}秒"
                if codec:
                    log_str += f" | 音频编码: {codec}"
            
            self._log(log_str)
            return media_info
        except Exception as e:
            self._log(f"  获取文件信息时出错: {e}")
            return None

    def prepare_upload_task(self, file_path: str, language_code: str, tag_audio_events: bool) -> Optional[Uploader]:
        """Prepares an Uploader runnable task without starting it."""
        if not os.path.exists(file_path):
            self._log(f"错误：文件 '{file_path}' 未找到。")
            return None

        self._log(f"准备处理文件: {os.path.basename(file_path)}")
        self.log_media_info(file_path)

        mime_type = "application/octet-stream"
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".mp3", ".mp4", ".m4a", ".wav", ".flac", ".ogg", ".mov", ".aac"]:
            mime_type = f"audio/{ext.replace('.', '')}" if ext not in [".mp4", ".mov"] else f"video/{ext.replace('.', '')}"

        payload = {
            "model_id": DEFAULT_STT_MODEL_ID,
            "diarize": "true",
            "tag_audio_events": str(tag_audio_events).lower(),
            # Placeholder for the file object, which will be opened in the Uploader thread
            "file": (os.path.basename(file_path), None, mime_type)
        }
        if language_code and language_code.lower() != "auto":
            payload["language_code"] = language_code

        # Assemble headers using the simple and effective final approach
        headers = BASE_HEADERS.copy()
        headers["user-agent"] = random.choice(USER_AGENTS)
        headers["accept-language"] = random.choice(ACCEPT_LANGUAGES)
        
        return Uploader(file_path, payload, headers)
