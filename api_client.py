import os
import random
from typing import Optional, Any, Dict

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from mutagen import File as MutagenFile
from PySide6.QtCore import QObject, Signal, QRunnable

# ==============================================================================
#  API Constants and Helpers
# ==============================================================================

ELEVENLABS_STT_API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_STT_PARAMS = {"allow_unauthenticated": "1"}
DEFAULT_STT_MODEL_ID = "scribe_v1"
DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

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
    def __init__(self, signals_forwarder: Optional[QObject] = None):
        self._signals = signals_forwarder

    def _log(self, message: str):
        if self._signals and hasattr(self._signals, 'log_message'):
            self._signals.log_message.emit(f"{message}")

    def get_audio_info(self, audio_file_path: str) -> None:
        try:
            file_size_mb = os.path.getsize(audio_file_path) / (1024 * 1024)
            duration_seconds = None
            audio_info = MutagenFile(audio_file_path)
            if audio_info and hasattr(audio_info, 'info') and hasattr(audio_info.info, 'length'):
                duration_seconds = float(audio_info.info.length)
            
            log_str = f"  文件大小: {file_size_mb:.2f} MB"
            if duration_seconds:
                minutes, seconds = divmod(duration_seconds, 60)
                log_str += f" | 时长: {int(minutes):02d}分{int(seconds):02d}秒"
            self._log(log_str)
        except Exception as e:
            self._log(f"  获取音频信息时出错: {e}")

    def prepare_upload_task(self, file_path: str, language_code: str, tag_audio_events: bool) -> Optional[Uploader]:
        """Prepares an Uploader runnable task without starting it."""
        if not os.path.exists(file_path):
            self._log(f"错误：文件 '{file_path}' 未找到。")
            return None

        self._log(f"准备处理文件: {os.path.basename(file_path)}")
        self.get_audio_info(file_path)

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

        headers = {
            "accept": "application/json",
            "user-agent": random.choice(DEFAULT_USER_AGENTS),
        }
        
        return Uploader(file_path, payload, headers)