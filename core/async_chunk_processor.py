# -*- coding: utf-8 -*-

"""
异步音频片段处理器
实现音频片段的并发上传和转录处理
"""

import os
import json
import time
from typing import List, Dict, Any, Optional, Callable
from PySide6.QtCore import QObject, Signal, QMutex, QMutexLocker, QSemaphore, QRunnable, QEventLoop, QTimer

from api_client import ElevenLabsSTTClient


class ChunkProcessorSignals(QObject):
    """片段处理任务的信号"""
    chunk_completed = Signal(int, dict)  # chunk_index, transcript_json
    chunk_failed = Signal(int, str)  # chunk_index, error_message
    progress_updated = Signal(int, int)  # bytes_sent, total_bytes


class ChunkProcessorTask(QRunnable):
    """单个音频片段处理任务"""

    def __init__(self, chunk_index: int, chunk_path: str, time_offset: float,
                 language_code: str, tag_audio_events: bool, ffmpeg_available: bool,
                 max_retries: int, parent_processor):
        super().__init__()
        self.signals = ChunkProcessorSignals()
        self.chunk_index = chunk_index
        self.chunk_path = chunk_path
        self.time_offset = time_offset
        self.language_code = language_code
        self.tag_audio_events = tag_audio_events
        self.ffmpeg_available = ffmpeg_available
        self.max_retries = max_retries
        self.parent_processor = parent_processor

    def run(self):
        """执行片段处理"""
        try:
            # 获取信号量（限制并发数）
            self.parent_processor.semaphore.acquire()

            # 速率限制检查
            self.parent_processor._wait_for_rate_limit()

            if self.parent_processor.is_cancelled:
                raise Exception("任务被取消")

            # 标记开始处理
            with QMutexLocker(self.parent_processor.mutex):
                self.parent_processor.processing_chunks.add(self.chunk_index)

            # 创建API客户端
            client = ElevenLabsSTTClient(ffmpeg_available=self.ffmpeg_available)

            # 重试机制
            last_error = None
            for attempt in range(self.max_retries):
                if self.parent_processor.is_cancelled:
                    raise Exception("任务被取消")

                try:
                    # 准备上传任务
                    uploader = client.prepare_upload_task(
                        self.chunk_path, self.language_code, self.tag_audio_events
                    )

                    if not uploader:
                        raise Exception(f"无法为片段 {self.chunk_index} 准备上传任务")

                    # 连接进度信号
                    uploader.signals.progress.connect(self.signals.progress_updated)

                    # 执行上传（同步等待）
                    transcript_json = self._execute_upload_sync(uploader)

                    # 调整时间偏移
                    words = transcript_json.get("words", [])
                    for word in words:
                        word["start"] = round(word["start"] + self.time_offset, 3)
                        word["end"] = round(word["end"] + self.time_offset, 3)

                    # 保存分段JSON文件
                    self._save_chunk_json(transcript_json)

                    # 发送完成信号
                    self.signals.chunk_completed.emit(self.chunk_index, transcript_json)
                    return

                except Exception as e:
                    last_error = e
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt  # 指数退避
                        time.sleep(wait_time)

            # 所有重试都失败
            raise last_error or Exception("未知错误")

        except Exception as e:
            self.signals.chunk_failed.emit(self.chunk_index, str(e))
        finally:
            # 清理状态
            with QMutexLocker(self.parent_processor.mutex):
                self.parent_processor.processing_chunks.discard(self.chunk_index)

            self.parent_processor.semaphore.release()

    def _execute_upload_sync(self, uploader) -> dict:
        """同步执行上传任务"""

        result = {}
        error = {}
        loop = QEventLoop()

        def on_finished(transcript_json):
            result['data'] = transcript_json
            loop.quit()

        def on_error(error_message):
            error['message'] = error_message
            loop.quit()

        # 连接信号
        uploader.signals.finished.connect(on_finished)
        uploader.signals.error.connect(on_error)

        # 设置超时定时器
        timeout_timer = QTimer()
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(loop.quit)
        timeout_timer.start(1800000)  # 30分钟超时

        # 启动上传
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(uploader)

        # 等待完成
        loop.exec()

        timeout_timer.stop()

        if 'data' in result:
            return result['data']
        elif 'message' in error:
            raise Exception(error['message'])
        else:
            raise Exception("上传超时或被取消")

    def _save_chunk_json(self, transcript_json: dict):
        """保存分段JSON文件"""
        try:
            base_chunk_path, _ = os.path.splitext(self.chunk_path)
            segment_json_path = base_chunk_path + ".json"
            with open(segment_json_path, 'w', encoding='utf-8') as f:
                json.dump(transcript_json, f, ensure_ascii=False, indent=4)
        except Exception:
            pass  # 忽略保存错误


class AsyncChunkProcessor(QObject):
    """异步音频片段处理器"""

    # 信号定义
    chunk_started = Signal(int)  # chunk_index
    chunk_completed = Signal(int, dict)  # chunk_index, transcript_json
    chunk_failed = Signal(int, str)  # chunk_index, error_message
    all_chunks_completed = Signal(dict)  # combined_transcript
    processing_failed = Signal(str)  # error_message
    progress_updated = Signal(int, int, int)  # chunk_index, bytes_sent, total_bytes

    def __init__(self, max_concurrent_chunks: int = 3, max_retries: int = 3):
        super().__init__()
        self.max_concurrent_chunks = max_concurrent_chunks
        self.max_retries = max_retries

        # 状态管理
        self.completed_chunks: Dict[int, dict] = {}
        self.failed_chunks: Dict[int, str] = {}
        self.processing_chunks: set = set()
        self.total_chunks = 0
        self.is_cancelled = False

        # 线程安全
        self.mutex = QMutex()
        self.semaphore = QSemaphore(max_concurrent_chunks)

        # 速率限制
        self.request_times: List[float] = []
        self.max_requests_per_minute = 30

    def process_chunks_async(self, chunk_paths: List[str],
                           split_duration_sec: float,
                           language_code: str,
                           tag_audio_events: bool,
                           ffmpeg_available: bool,
                           log_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        异步处理所有音频片段

        Args:
            chunk_paths: 音频片段文件路径列表
            split_duration_sec: 每个片段的时长（秒）
            language_code: 语言代码
            tag_audio_events: 是否标记音频事件
            ffmpeg_available: FFmpeg是否可用
            log_callback: 日志回调函数

        Returns:
            bool: 是否成功启动处理
        """
        if not chunk_paths:
            return False

        self.total_chunks = len(chunk_paths)
        self.completed_chunks.clear()
        self.failed_chunks.clear()
        self.processing_chunks.clear()
        self.is_cancelled = False

        if log_callback:
            log_callback(f"开始异步处理 {self.total_chunks} 个音频片段...")

        # 预计算时间偏移
        time_offsets = {
            i: i * split_duration_sec
            for i in range(self.total_chunks)
        }

        # 使用Qt的线程池而不是Python的ThreadPoolExecutor
        # 这样可以更好地与Qt信号系统集成
        try:
            # 启动所有片段的处理任务
            for i, chunk_path in enumerate(chunk_paths):
                if self.is_cancelled:
                    break

                # 创建处理任务
                processor = ChunkProcessorTask(
                    chunk_index=i,
                    chunk_path=chunk_path,
                    time_offset=time_offsets[i],
                    language_code=language_code,
                    tag_audio_events=tag_audio_events,
                    ffmpeg_available=ffmpeg_available,
                    max_retries=self.max_retries,
                    parent_processor=self
                )

                # 连接信号
                processor.signals.chunk_completed.connect(self._on_chunk_completed)
                processor.signals.chunk_failed.connect(self._on_chunk_failed)
                processor.signals.progress_updated.connect(
                    lambda sent, total, chunk_idx=i:
                    self.progress_updated.emit(chunk_idx, sent, total)
                )

                # 启动任务
                from PySide6.QtCore import QThreadPool
                QThreadPool.globalInstance().start(processor)

                # 发送开始信号
                self.chunk_started.emit(i)

            return True

        except Exception as e:
            if log_callback:
                log_callback(f"启动异步处理失败: {e}")
            return False



    def _wait_for_rate_limit(self):
        """等待速率限制"""
        with QMutexLocker(self.mutex):
            now = time.time()

            # 清理超过1分钟的请求记录
            self.request_times = [
                t for t in self.request_times
                if now - t < 60
            ]

            # 检查是否需要等待
            if len(self.request_times) >= self.max_requests_per_minute:
                oldest_request = min(self.request_times)
                wait_time = 60 - (now - oldest_request)
                if wait_time > 0:
                    time.sleep(wait_time)

            # 记录新请求
            self.request_times.append(now)

    def _on_chunk_completed(self, chunk_index: int, transcript_json: dict):
        """片段完成回调"""
        with QMutexLocker(self.mutex):
            self.completed_chunks[chunk_index] = transcript_json
            self.chunk_completed.emit(chunk_index, transcript_json)

            # 检查是否所有片段都完成
            total_processed = len(self.completed_chunks) + len(self.failed_chunks)
            if total_processed == self.total_chunks:
                if not self.failed_chunks:
                    # 所有片段都成功，合并结果
                    combined = self._merge_transcripts()
                    self.all_chunks_completed.emit(combined)
                else:
                    # 有失败的片段
                    failed_list = list(self.failed_chunks.keys())
                    error_msg = f"以下片段处理失败: {failed_list}"
                    self.processing_failed.emit(error_msg)

    def _on_chunk_failed(self, chunk_index: int, error_message: str):
        """片段失败回调"""
        with QMutexLocker(self.mutex):
            self.failed_chunks[chunk_index] = error_message
            self.chunk_failed.emit(chunk_index, error_message)

            # 检查是否所有片段都完成
            total_processed = len(self.completed_chunks) + len(self.failed_chunks)
            if total_processed == self.total_chunks:
                failed_list = list(self.failed_chunks.keys())
                error_msg = f"以下片段处理失败: {failed_list}"
                self.processing_failed.emit(error_msg)

    def _merge_transcripts(self) -> dict:
        """按顺序合并所有转录结果"""
        combined_transcript = {"words": [], "text": ""}

        # 按片段索引顺序合并
        for i in sorted(self.completed_chunks.keys()):
            transcript = self.completed_chunks[i]
            combined_transcript["words"].extend(transcript.get("words", []))

            if combined_transcript["text"]:
                combined_transcript["text"] += " "
            combined_transcript["text"] += transcript.get("text", "")

        return combined_transcript

    def cancel(self):
        """取消所有处理"""
        with QMutexLocker(self.mutex):
            self.is_cancelled = True
            # 发送取消信号，让正在等待的任务能够及时退出
            self.processing_failed.emit("用户取消了任务")

    def get_progress_info(self) -> Dict[str, Any]:
        """获取处理进度信息"""
        with QMutexLocker(self.mutex):
            return {
                "total_chunks": self.total_chunks,
                "completed_chunks": len(self.completed_chunks),
                "failed_chunks": len(self.failed_chunks),
                "processing_chunks": len(self.processing_chunks),
                "is_cancelled": self.is_cancelled
            }