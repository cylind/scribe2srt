import os
import random
import ipaddress
from typing import Optional, Any, Dict, Callable, List

import requests
import json
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from PySide6.QtCore import QObject, Signal, QRunnable

from core.ffmpeg_utils import get_media_info

# ==============================================================================
#  Provider Identifiers
# ==============================================================================

PROVIDER_ELEVENLABS = "elevenlabs"
PROVIDER_60DB = "60db"

# ==============================================================================
#  ElevenLabs API Constants and Helpers
# ==============================================================================

ELEVENLABS_STT_API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_STT_PARAMS = {"allow_unauthenticated": "1"}
DEFAULT_STT_MODEL_ID = "scribe_v2"

# ==============================================================================
#  60dB API Constants
# ==============================================================================

SIXTYDB_STT_API_URL = "https://api.60db.ai/stt"

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

# 用于标准化语言码时判断 CJK（与 srt_processor 中保持一致）
_CJK_LANGUAGE_CODES = {"zho", "jpn", "kor", "chi", "zh", "ja", "ko"}

# 音频/视频扩展名到 MIME 类型的辅助判断
_AUDIO_VIDEO_EXTENSIONS = [".mp3", ".mp4", ".m4a", ".wav", ".flac", ".ogg", ".mov", ".aac"]


def _random_ip() -> str:
    """生成一个真正的、合法的公网 IPv4 地址（严格过滤私有/保留地址）"""
    while True:
        ip_int = random.getrandbits(32)
        ip_obj = ipaddress.IPv4Address(ip_int)
        if (ip_obj.is_private or ip_obj.is_loopback or
            ip_obj.is_multicast or ip_obj.is_link_local or
            ip_obj.is_reserved):
            continue
        return str(ip_obj)


def _guess_mime_type(file_path: str) -> str:
    """根据扩展名推断 multipart 上传所需的 MIME 类型。"""
    mime_type = "application/octet-stream"
    ext = os.path.splitext(file_path)[1].lower()
    if ext in _AUDIO_VIDEO_EXTENSIONS:
        mime_type = f"audio/{ext.replace('.', '')}" if ext not in [".mp4", ".mov"] else f"video/{ext.replace('.', '')}"
    return mime_type


def _is_cjk_language(language_code: Optional[str]) -> bool:
    """判断语言码是否属于 CJK（中日韩）。"""
    if not language_code:
        return False
    return language_code[:3] in _CJK_LANGUAGE_CODES or language_code in _CJK_LANGUAGE_CODES


def normalize_60db_response(resp: Dict[str, Any]) -> Dict[str, Any]:
    """将 60dB STT 响应规整为本项目内部使用的（ElevenLabs 风格）转录结构。

    内部结构约定（SRT 引擎所依赖的格式）::

        {
            "language_code": "en",
            "text": "...",
            "words": [
                {"type": "word", "text": "Hello ", "start": 0.0, "end": 0.5, "speaker_id": "..."},
                ...
            ]
        }

    与 60dB 的差异处理：
    - 60dB 使用 ``word`` 字段表示词文本，``language`` 表示语言码。
    - 60dB 不返回 ``spacing`` 类型条目，因此对于非 CJK 语言需要为每个词补一个尾随空格，
      否则下游 ``"".join(...)`` 会把单词粘连在一起（"Helloworld"）。
    - 60dB 词条仅在 ``return_timestamps=word`` 时携带 start/end；缺时间戳的词会被跳过。
    """
    language = resp.get("language") or resp.get("language_code") or "auto"
    text = resp.get("text", "") or ""

    # 优先使用扁平的 words 列表，否则从 segments 中展开
    raw_words: List[Dict[str, Any]] = list(resp.get("words") or [])
    if not raw_words:
        for segment in resp.get("segments", []) or []:
            raw_words.extend(segment.get("words", []) or [])

    is_cjk = _is_cjk_language(language)
    words: List[Dict[str, Any]] = []
    for w in raw_words:
        word_text = w.get("word", w.get("text", ""))
        start = w.get("start")
        end = w.get("end")
        # 没有时间戳的词无法用于字幕时间轴，跳过
        if start is None or end is None:
            continue

        # 非 CJK：为每个词补尾随空格，复刻 ElevenLabs 的 spacing 行为
        if word_text and not is_cjk and not word_text.endswith(" "):
            word_text = word_text + " "

        words.append({
            "type": "word",
            "text": word_text,
            "start": float(start),
            "end": float(end),
            "speaker_id": w.get("speaker") or w.get("speaker_id"),
        })

    return {
        "language_code": language,
        "text": text,
        "words": words,
    }


class UploaderSignals(QObject):
    """Defines the signals available from a running Uploader thread."""
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(int, int)

class Uploader(QRunnable):
    """Runnable that handles the blocking network request.

    通过 ``url`` / ``params`` / ``response_transform`` 参数实现 provider 无关：
    ElevenLabs 与 60dB 共用同一套上传、进度、取消逻辑，仅在端点、查询参数与响应
    转换上有所不同。``response_transform`` 用于把各 provider 的原始响应规整为内部结构。
    """
    def __init__(self, file_path: str, payload: Dict, headers: Dict,
                 url: str = ELEVENLABS_STT_API_URL,
                 params: Optional[Dict] = None,
                 response_transform: Optional[Callable[[Dict], Dict]] = None):
        super().__init__()
        self.signals = UploaderSignals()
        self.file_path = file_path
        self.payload = payload
        self.headers = headers
        self.url = url
        self.params = params if params is not None else ELEVENLABS_STT_PARAMS
        self.response_transform = response_transform
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
                    self.url,
                    params=self.params,
                    headers=self.headers,
                    data=monitor,
                    timeout=1800
                )
                response.raise_for_status()
                data = response.json()
                if self.response_transform is not None:
                    data = self.response_transform(data)
                self.signals.finished.emit(data)

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


class BaseSTTClient:
    """STT provider 客户端的公共基类，封装日志与媒体信息探测。"""

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
        raise NotImplementedError


class ElevenLabsSTTClient(BaseSTTClient):
    """Client to interact with the ElevenLabs Speech-to-Text API."""

    def prepare_upload_task(self, file_path: str, language_code: str, tag_audio_events: bool) -> Optional[Uploader]:
        """Prepares an Uploader runnable task without starting it."""
        if not os.path.exists(file_path):
            self._log(f"错误：文件 '{file_path}' 未找到。")
            return None

        self._log(f"准备处理文件: {os.path.basename(file_path)}")
        self.log_media_info(file_path)

        mime_type = _guess_mime_type(file_path)

        payload = {
            "model_id": DEFAULT_STT_MODEL_ID,
            "diarize": "true",
            "tag_audio_events": str(tag_audio_events).lower(),
            # Placeholder for the file object, which will be opened in the Uploader thread
            "file": (os.path.basename(file_path), None, mime_type)
        }
        if language_code and language_code.lower() != "auto":
            payload["language_code"] = language_code

        # Assemble headers with high-fidelity IP spoofing for bypassing IP restrictions
        headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "origin": "https://elevenlabs.io",
            "referer": "https://elevenlabs.io/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }
        headers["user-agent"] = random.choice(USER_AGENTS)
        headers["accept-language"] = random.choice(ACCEPT_LANGUAGES)

        fake_ip = _random_ip()
        forward_headers = {
            "Forwarded": f"for={fake_ip}",
            "X-Forwarded-For": fake_ip,
            "X-Real-IP": fake_ip,
            "CF-Connecting-IP": fake_ip,
            "True-Client-IP": fake_ip,
        }
        headers.update(forward_headers)

        return Uploader(
            file_path, payload, headers,
            url=ELEVENLABS_STT_API_URL,
            params=ELEVENLABS_STT_PARAMS,
            response_transform=None,
        )


class SixtyDBSTTClient(BaseSTTClient):
    """Client to interact with the 60dB Speech-to-Text API.

    与 ElevenLabs 不同，60dB 需要真实的 ``Authorization: Bearer`` API Key，
    并通过 ``return_timestamps=word`` 才会返回逐词时间戳。响应经
    :func:`normalize_60db_response` 规整为内部结构后再交给下游 SRT 引擎，
    从而保证两个 provider 的行为完全一致。
    """

    def __init__(self, signals_forwarder: Optional[QObject] = None,
                 ffmpeg_available: bool = False, api_key: Optional[str] = None):
        super().__init__(signals_forwarder=signals_forwarder, ffmpeg_available=ffmpeg_available)
        self.api_key = (api_key or "").strip()

    def prepare_upload_task(self, file_path: str, language_code: str, tag_audio_events: bool) -> Optional[Uploader]:
        if not os.path.exists(file_path):
            self._log(f"错误：文件 '{file_path}' 未找到。")
            return None

        if not self.api_key:
            self._log("错误：未配置 60dB API Key。请在「字幕设置」中填写后重试。")
            return None

        self._log(f"准备处理文件 (60dB): {os.path.basename(file_path)}")
        self.log_media_info(file_path)

        mime_type = _guess_mime_type(file_path)

        # 注意：60dB 没有 tag_audio_events（音频事件标记）这一能力，该选项对 60dB 无效。
        payload = {
            # return_timestamps=word 是获取逐词时间戳的必要参数，字幕时间轴依赖它
            "return_timestamps": "word",
            "diarize": "true",
            # Placeholder for the file object, which will be opened in the Uploader thread
            "file": (os.path.basename(file_path), None, mime_type),
        }
        if language_code and language_code.lower() != "auto":
            payload["language"] = language_code

        headers = {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br",
            "user-agent": "Scribe2SRT/1.0",
            "Authorization": f"Bearer {self.api_key}",
        }

        return Uploader(
            file_path, payload, headers,
            url=SIXTYDB_STT_API_URL,
            params={},
            response_transform=normalize_60db_response,
        )


def create_stt_client(provider: str,
                      signals_forwarder: Optional[QObject] = None,
                      ffmpeg_available: bool = False,
                      api_key: Optional[str] = None) -> BaseSTTClient:
    """根据 provider 标识创建对应的 STT 客户端。

    所有客户端都暴露相同的 ``prepare_upload_task(file_path, language_code, tag_audio_events)``
    接口并产出统一的内部转录结构，因此 Worker / 异步处理器无需关心具体 provider。
    """
    if provider == PROVIDER_60DB:
        return SixtyDBSTTClient(
            signals_forwarder=signals_forwarder,
            ffmpeg_available=ffmpeg_available,
            api_key=api_key,
        )
    # 默认回退到 ElevenLabs，保证向后兼容
    return ElevenLabsSTTClient(
        signals_forwarder=signals_forwarder,
        ffmpeg_available=ffmpeg_available,
    )
