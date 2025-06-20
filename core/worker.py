# -*- coding: utf-8 -*-

"""
这个文件定义了在后台线程中执行所有处理任务的 Worker 类。
"""

import os
import sys
import json
import subprocess
from typing import Optional, List, Dict, Any

from PySide6.QtCore import QObject, Signal, QThreadPool

from api.client import ElevenLabsSTTClient
from .srt_processor import create_srt_from_json
from .async_chunk_processor import AsyncChunkProcessor

class Worker(QObject):
    """
    在单独的线程中处理文件转录、切分和SRT生成任务。
    """
    finished = Signal(str)
    error = Signal(str)
    log_message = Signal(str)
    progress_updated = Signal(int, int)
    chunk_progress = Signal(str)

    def __init__(self, file_path: str, language_code: str, tag_audio_events: bool,
                 max_subtitle_duration: float, split_duration_min: int,
                 original_file_path: Optional[str] = None, ffmpeg_available: bool = False,
                 restore_state: Optional[Dict[str, Any]] = None, subtitle_settings: Optional[Dict] = None,
                 enable_async_processing: bool = True, max_concurrent_chunks: int = 3,
                 max_retries: int = 3, api_rate_limit_per_minute: int = 30):
        super().__init__()
        self.file_path = file_path
        self.original_file_path = original_file_path if original_file_path else file_path
        self.language_code = language_code
        self.tag_audio_events = tag_audio_events
        self.max_subtitle_duration = max_subtitle_duration
        self.split_duration_sec = split_duration_min * 60
        self.ffmpeg_available = ffmpeg_available
        self.restore_state = restore_state
        self.subtitle_settings = subtitle_settings
        
        self.uploader = None
        self.client = ElevenLabsSTTClient(signals_forwarder=self, ffmpeg_available=self.ffmpeg_available)

        # 异步片段处理器
        self.async_processor = None
        # 从恢复状态或使用传入参数配置异步处理
        if self.restore_state:
            self.enable_async_processing = self.restore_state.get("enable_async_processing", enable_async_processing)
            self.max_concurrent_chunks = self.restore_state.get("max_concurrent_chunks", max_concurrent_chunks)
            self.max_retries = self.restore_state.get("max_retries", max_retries)
            self.api_rate_limit_per_minute = self.restore_state.get("api_rate_limit_per_minute", api_rate_limit_per_minute)
        else:
            self.enable_async_processing = enable_async_processing
            self.max_concurrent_chunks = max_concurrent_chunks
            self.max_retries = max_retries
            self.api_rate_limit_per_minute = api_rate_limit_per_minute

        self._is_cancelled = False
        
        if self.restore_state:
            self.temp_chunks = self.restore_state.get("temp_chunks", [])
            self.owned_temp_chunks = self.restore_state.get("owned_temp_chunks", [])
            self.combined_transcript = self.restore_state.get("combined_transcript", {})
            self.current_chunk_index = self.restore_state.get("current_chunk_index", 0)
            self.total_chunks = self.restore_state.get("total_chunks", 0)
            self.time_offset = self.restore_state.get("time_offset", 0.0)
        else:
            self.temp_chunks = []
            self.owned_temp_chunks = []
            self.combined_transcript = {}
            self.current_chunk_index = 0
            self.total_chunks = 0
            self.time_offset = 0.0

    def get_state(self) -> Dict[str, Any]:
        """获取当前worker的状态，用于任务恢复。"""
        # 获取异步处理器的进度信息
        async_progress = {}
        if self.async_processor:
            async_progress = self.async_processor.get_progress_info()

        return {
            "temp_chunks": self.temp_chunks,
            "owned_temp_chunks": self.owned_temp_chunks,
            "combined_transcript": self.combined_transcript,
            "current_chunk_index": self.current_chunk_index,
            "total_chunks": self.total_chunks,
            "time_offset": self.time_offset,
            "original_file_path": self.original_file_path,
            "language_code": self.language_code,
            "tag_audio_events": self.tag_audio_events,
            "max_subtitle_duration": self.max_subtitle_duration,
            "split_duration_min": self.split_duration_sec / 60,
            "ffmpeg_available": self.ffmpeg_available,
            # 异步处理相关状态
            "enable_async_processing": self.enable_async_processing,
            "max_concurrent_chunks": self.max_concurrent_chunks,
            "max_retries": self.max_retries,
            "api_rate_limit_per_minute": self.api_rate_limit_per_minute,
            "async_progress": async_progress,
        }

    def run(self):
        """任务执行的入口点。"""
        is_restoring = self.restore_state and self.restore_state.get("temp_chunks")

        if is_restoring:
            self.log_message.emit("...从断点处恢复任务...")
            # 在恢复模式下，如果切片文件丢失，则尝试重新创建它们
            if not all(os.path.exists(p) for p in self.temp_chunks):
                self.log_message.emit("检测到临时切片文件丢失，正在重新切分...")
                if not self._split_audio(self.restore_state.get("original_file_path")):
                     self.error.emit("恢复任务失败：无法重新切分音频。")
                     return

            # 恢复模式下的处理逻辑
            self._process_restored_chunks()
            return

        self.log_message.emit("="*50)
        self.log_message.emit(f"开始处理文件: {os.path.basename(self.original_file_path)}")

        media_info = self.client.log_media_info(self.file_path)
        duration = media_info.get("duration") if media_info else 0

        if duration > self.split_duration_sec and self.ffmpeg_available:
            self.log_message.emit(f"文件时长超过 {self.split_duration_sec / 60:.0f} 分钟，将执行自动切分。")
            if self._split_audio(self.file_path):
                self._process_next_chunk()
            else:
                return
        else:
            self.log_message.emit("文件无需切分，执行单文件处理流程。")
            self.total_chunks = 1
            self.temp_chunks.append(self.file_path)
            self._process_next_chunk()

    def _split_audio(self, audio_path: str) -> bool:
        """使用 FFmpeg 切分音频文件。"""
        self.log_message.emit("正在切分音频文件...")
        self.chunk_progress.emit("正在切分音频...")
        
        base_dir = os.path.dirname(audio_path)
        base_name, _ = os.path.splitext(os.path.basename(audio_path))
        
        output_template = os.path.join(base_dir, f"{base_name}_chunk_%03d.mp3")
        
        try:
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            command = [
                "ffmpeg", "-i", audio_path,
                "-f", "segment",
                "-segment_time", str(self.split_duration_sec),
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-y",
                output_template
            ]
            
            subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', startupinfo=startupinfo)
            
            self.owned_temp_chunks = sorted([os.path.join(base_dir, f) for f in os.listdir(base_dir) if f.startswith(f"{base_name}_chunk_") and f.endswith(".mp3")])
            self.temp_chunks = self.owned_temp_chunks

            if not self.owned_temp_chunks:
                raise RuntimeError("FFmpeg 执行完毕但未找到任何切分文件。")

            self.total_chunks = len(self.temp_chunks)
            self.log_message.emit(f"成功切分为 {self.total_chunks} 个片段。")
            return True

        except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError) as e:
            error_message = f"音频切分失败: {e}"
            if hasattr(e, 'stderr'):
                error_message += f"\nFFmpeg 输出:\n{e.stderr.strip()}"
            self.error.emit(error_message)
            return False

    def _process_next_chunk(self):
        """处理下一个待处理的音频片段。"""
        if self._is_cancelled:
            self.error.emit("任务被用户取消。")
            self._cleanup_chunks()
            return

        # 检查是否使用异步处理
        if self.enable_async_processing and self.total_chunks > 1:
            self._process_chunks_async()
        else:
            # 使用原有的顺序处理逻辑（兼容性保证）
            self._process_chunks_sequential()

    def _process_chunks_async(self):
        """异步处理所有音频片段"""
        self.log_message.emit("-" * 20)
        self.log_message.emit(f"启用异步处理模式，并发处理 {self.total_chunks} 个片段...")
        self.chunk_progress.emit(f"异步处理 {self.total_chunks} 个片段")

        # 创建异步处理器
        self.async_processor = AsyncChunkProcessor(
            max_concurrent_chunks=self.max_concurrent_chunks,
            max_retries=self.max_retries
        )
        # 设置API速率限制
        self.async_processor.max_requests_per_minute = self.api_rate_limit_per_minute

        # 连接信号
        self.async_processor.chunk_started.connect(self._on_async_chunk_started)
        self.async_processor.chunk_completed.connect(self._on_async_chunk_completed)
        self.async_processor.chunk_failed.connect(self._on_async_chunk_failed)
        self.async_processor.all_chunks_completed.connect(self._on_async_all_completed)
        self.async_processor.processing_failed.connect(self._on_async_processing_failed)
        self.async_processor.progress_updated.connect(self._on_async_progress_updated)

        # 启动异步处理
        success = self.async_processor.process_chunks_async(
            chunk_paths=self.temp_chunks,
            split_duration_sec=self.split_duration_sec,
            language_code=self.language_code,
            tag_audio_events=self.tag_audio_events,
            ffmpeg_available=self.ffmpeg_available,
            log_callback=lambda msg: self.log_message.emit(msg)
        )

        if not success:
            self.error.emit("启动异步处理失败")

    def _process_chunks_sequential(self):
        """顺序处理音频片段（原有逻辑）"""
        if self.current_chunk_index < self.total_chunks:
            self.time_offset = self.current_chunk_index * self.split_duration_sec
            chunk_path = self.temp_chunks[self.current_chunk_index]

            self.log_message.emit("-" * 20)
            self.log_message.emit(f"正在处理片段 {self.current_chunk_index + 1}/{self.total_chunks}: {os.path.basename(chunk_path)}")
            self.chunk_progress.emit(f"正在处理片段 {self.current_chunk_index + 1}/{self.total_chunks}")

            self._process_single_file(chunk_path)
        else:
            self._finalize_task()

    def _process_restored_chunks(self):
        """处理恢复的任务"""
        # 计算剩余需要处理的片段
        remaining_chunks = self.temp_chunks[self.current_chunk_index:]

        if not remaining_chunks:
            # 所有片段都已完成，直接进入最终处理
            self.log_message.emit("所有片段已在之前完成，直接生成最终文件...")
            self._finalize_task()
            return

        self.log_message.emit(f"需要继续处理 {len(remaining_chunks)} 个剩余片段...")

        # 根据剩余片段数量选择处理模式
        if self.enable_async_processing and len(remaining_chunks) > 1:
            # 异步处理剩余片段
            self._process_remaining_chunks_async(remaining_chunks)
        else:
            # 顺序处理剩余片段
            self._process_chunks_sequential()

    def _process_remaining_chunks_async(self, remaining_chunks: List[str]):
        """异步处理剩余的音频片段"""
        self.log_message.emit("-" * 20)
        self.log_message.emit(f"恢复模式：异步处理剩余 {len(remaining_chunks)} 个片段...")
        self.chunk_progress.emit(f"恢复异步处理 {len(remaining_chunks)} 个片段")

        # 创建异步处理器
        self.async_processor = AsyncChunkProcessor(
            max_concurrent_chunks=self.max_concurrent_chunks,
            max_retries=self.max_retries
        )
        # 设置API速率限制
        self.async_processor.max_requests_per_minute = self.api_rate_limit_per_minute

        # 连接信号
        self.async_processor.chunk_started.connect(self._on_async_chunk_started_restored)
        self.async_processor.chunk_completed.connect(self._on_async_chunk_completed_restored)
        self.async_processor.chunk_failed.connect(self._on_async_chunk_failed)
        self.async_processor.all_chunks_completed.connect(self._on_async_all_completed_restored)
        self.async_processor.processing_failed.connect(self._on_async_processing_failed)
        self.async_processor.progress_updated.connect(self._on_async_progress_updated_restored)

        # 启动异步处理剩余片段
        success = self.async_processor.process_chunks_async(
            chunk_paths=remaining_chunks,
            split_duration_sec=self.split_duration_sec,
            language_code=self.language_code,
            tag_audio_events=self.tag_audio_events,
            ffmpeg_available=self.ffmpeg_available,
            log_callback=lambda msg: self.log_message.emit(msg)
        )

        if not success:
            self.error.emit("恢复模式：启动异步处理失败")

    def _process_single_file(self, file_path: str):
        """为单个文件准备并开始上传任务。"""
        self.uploader = self.client.prepare_upload_task(
            file_path, self.language_code, self.tag_audio_events
        )
        if not self.uploader:
            self.error.emit(f"为文件 {os.path.basename(file_path)} 准备任务失败。")
            return

        self.uploader.signals.progress.connect(self.progress_updated)
        self.uploader.signals.finished.connect(self.on_upload_finished)
        self.uploader.signals.error.connect(self.on_chunk_error)
        
        QThreadPool.globalInstance().start(self.uploader)

    # === 异步处理信号回调方法 ===
    def _on_async_chunk_started(self, chunk_index: int):
        """异步片段开始处理回调"""
        self.log_message.emit(f"开始异步处理片段 {chunk_index + 1}/{self.total_chunks}")

    def _on_async_chunk_completed(self, chunk_index: int, transcript_json: dict):
        """异步片段完成回调"""
        self.log_message.emit(f"片段 {chunk_index + 1}/{self.total_chunks} 异步转录成功")

    def _on_async_chunk_failed(self, chunk_index: int, error_message: str):
        """异步片段失败回调"""
        self.log_message.emit(f"片段 {chunk_index + 1}/{self.total_chunks} 处理失败: {error_message}")

    def _on_async_all_completed(self, combined_transcript: dict):
        """所有异步片段完成回调"""
        self.log_message.emit("所有片段异步处理完成，正在合并结果...")
        self.combined_transcript = combined_transcript

        # 确保进度显示完成
        self.chunk_progress.emit("异步处理完成，正在生成字幕文件...")

        # 调用最终处理
        self._finalize_task()

    def _on_async_processing_failed(self, error_message: str):
        """异步处理失败回调"""
        self.log_message.emit(f"异步处理失败: {error_message}")

        # 检查是否可以降级到顺序处理
        if self.async_processor:
            progress_info = self.async_processor.get_progress_info()
            completed_count = progress_info.get("completed_chunks", 0)

            if completed_count > 0:
                # 有部分片段成功，尝试降级处理
                self.log_message.emit(f"已完成 {completed_count} 个片段，尝试降级到顺序处理剩余片段...")
                self._fallback_to_sequential_processing()
            else:
                # 完全失败，报告错误
                self.error.emit(f"异步处理完全失败: {error_message}")
        else:
            self.error.emit(f"异步处理失败: {error_message}")

    def _fallback_to_sequential_processing(self):
        """降级到顺序处理模式"""
        try:
            self.log_message.emit("正在降级到顺序处理模式...")

            # 禁用异步处理
            self.enable_async_processing = False

            # 获取已完成的片段信息
            if self.async_processor:
                completed_chunks = self.async_processor.completed_chunks

                # 合并已完成的片段结果
                if completed_chunks:
                    self.log_message.emit(f"合并已完成的 {len(completed_chunks)} 个片段结果...")

                    # 按顺序合并已完成的片段
                    for chunk_index in sorted(completed_chunks.keys()):
                        transcript_json = completed_chunks[chunk_index]

                        if not self.combined_transcript:
                            self.combined_transcript = transcript_json
                        else:
                            words = transcript_json.get("words", [])
                            self.combined_transcript["words"].extend(words)
                            if self.combined_transcript["text"]:
                                self.combined_transcript["text"] += " "
                            self.combined_transcript["text"] += transcript_json.get("text", "")

                    # 更新当前处理索引
                    self.current_chunk_index = max(completed_chunks.keys()) + 1

                # 清理异步处理器
                self.async_processor = None

            # 继续顺序处理剩余片段
            if self.current_chunk_index < self.total_chunks:
                self.log_message.emit(f"继续顺序处理剩余 {self.total_chunks - self.current_chunk_index} 个片段...")
                self._process_chunks_sequential()
            else:
                # 所有片段都已完成
                self._finalize_task()

        except Exception as e:
            self.error.emit(f"降级处理失败: {e}")

    def _on_async_progress_updated(self, chunk_index: int, bytes_sent: int, total_bytes: int):
        """异步处理进度更新回调"""
        # 转发进度信号到主窗口
        self.progress_updated.emit(bytes_sent, total_bytes)

        # 更新当前处理的片段索引（用于UI显示）
        self.current_chunk_index = chunk_index

    # === 恢复模式的异步处理回调方法 ===
    def _on_async_chunk_started_restored(self, chunk_index: int):
        """恢复模式：异步片段开始处理回调"""
        # 调整索引以反映实际的全局片段位置
        actual_chunk_index = self.current_chunk_index + chunk_index
        self.log_message.emit(f"恢复模式：开始异步处理片段 {actual_chunk_index + 1}/{self.total_chunks}")

    def _on_async_chunk_completed_restored(self, chunk_index: int, transcript_json: dict):
        """恢复模式：异步片段完成回调"""
        # 调整索引以反映实际的全局片段位置
        actual_chunk_index = self.current_chunk_index + chunk_index
        self.log_message.emit(f"恢复模式：片段 {actual_chunk_index + 1}/{self.total_chunks} 异步转录成功")
        # transcript_json 在这里不需要特殊处理，由异步处理器自动合并

    def _on_async_all_completed_restored(self, remaining_transcript: dict):
        """恢复模式：所有剩余异步片段完成回调"""
        self.log_message.emit("恢复模式：所有剩余片段异步处理完成，正在合并结果...")

        # 合并已有的转录结果和新的转录结果
        if self.combined_transcript and self.combined_transcript.get("words"):
            # 已有部分转录结果，需要合并
            self.combined_transcript["words"].extend(remaining_transcript.get("words", []))
            if self.combined_transcript["text"]:
                self.combined_transcript["text"] += " "
            self.combined_transcript["text"] += remaining_transcript.get("text", "")
        else:
            # 没有已有结果，直接使用新结果
            self.combined_transcript = remaining_transcript

        self._finalize_task()

    def _on_async_progress_updated_restored(self, chunk_index: int, bytes_sent: int, total_bytes: int):
        """恢复模式：异步处理进度更新回调"""
        # 转发进度信号到主窗口
        self.progress_updated.emit(bytes_sent, total_bytes)
        # chunk_index 用于标识片段，但在恢复模式下不需要特殊处理

    def on_upload_finished(self, transcript_json):
        """当一个片段上传和转录成功时调用。"""
        self.log_message.emit(f"片段 {self.current_chunk_index + 1}/{self.total_chunks} 转录成功。")
        
        # 保存分段的 JSON 文件以供调试
        try:
            chunk_path = self.temp_chunks[self.current_chunk_index]
            base_chunk_path, _ = os.path.splitext(chunk_path)
            segment_json_path = base_chunk_path + ".json"
            with open(segment_json_path, 'w', encoding='utf-8') as f:
                json.dump(transcript_json, f, ensure_ascii=False, indent=4)
            self.log_message.emit(f"分段转录JSON已保存到: {os.path.basename(segment_json_path)}")
        except Exception as e:
            self.log_message.emit(f"警告：保存分段JSON文件失败: {e}")

        if not self.combined_transcript:
            self.combined_transcript = transcript_json
        else:
            words = transcript_json.get("words", [])
            for word in words:
                word["start"] = round(word["start"] + self.time_offset, 3)
                word["end"] = round(word["end"] + self.time_offset, 3)
            self.combined_transcript["words"].extend(words)
            self.combined_transcript["text"] += " " + transcript_json.get("text", "")
        
        self.current_chunk_index += 1
        
        if self.current_chunk_index < self.total_chunks:
            self._process_next_chunk()
        else:
            # 这是最后一个片段，直接进入最终处理阶段
            self._finalize_task()

    def on_chunk_error(self, error_message: str):
        """当处理片段出错时调用。"""
        self.error.emit(f"处理片段 {self.current_chunk_index + 1}/{self.total_chunks} 时出错: {error_message}")

    def _finalize_task(self):
        """所有片段处理完毕后，合并结果并生成最终文件。"""
        self.log_message.emit("-" * 20)
        self.log_message.emit("所有片段处理完毕，正在生成最终文件...")
        
        base_path, _ = os.path.splitext(self.original_file_path)
        output_json_path = base_path + ".json"
        try:
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(self.combined_transcript, f, ensure_ascii=False, indent=4)
            self.log_message.emit(f"合并后的转录文本已保存到:\n{output_json_path}")
        except Exception as e:
            self.error.emit(f"保存合并后的 JSON 文件时出错: {e}")
            self._cleanup_chunks()
            return

        self.log_message.emit("正在生成SRT字幕文件...")
        srt_data = create_srt_from_json(
            self.combined_transcript,
            max_subtitle_duration=self.max_subtitle_duration,
            subtitle_settings=self.subtitle_settings
        )
        if not srt_data:
            self.error.emit("从合并后的JSON生成SRT失败。")
            self._cleanup_chunks()
            return
            
        output_srt_path = base_path + ".srt"
        try:
            with open(output_srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_data)
            self.log_message.emit(f"最终SRT字幕文件已保存到:\n{output_srt_path}")
            self.finished.emit("任务成功完成！")
        except Exception as e:
            self.error.emit(f"保存最终SRT文件时出错: {e}")
        finally:
            self._cleanup_chunks()

    def request_cancellation(self):
        """请求取消当前任务。"""
        self.log_message.emit("正在取消上传...")
        self._is_cancelled = True

        # 取消异步处理器
        if self.async_processor:
            self.async_processor.cancel()

        # 取消当前上传器
        if self.uploader:
            self.uploader.cancel()

        self._cleanup_chunks()

    def _cleanup_chunks(self):
        """清理所有临时的音频片段文件。"""
        self.log_message.emit("正在清理所有临时音频片段...")

        # 清理音频片段文件
        if self.owned_temp_chunks:
            for chunk_path in self.owned_temp_chunks:
                try:
                    if os.path.exists(chunk_path):
                        os.remove(chunk_path)
                        self.log_message.emit(f"已删除临时片段: {os.path.basename(chunk_path)}")

                    # 同时删除对应的JSON文件
                    json_path = os.path.splitext(chunk_path)[0] + ".json"
                    if os.path.exists(json_path):
                        os.remove(json_path)
                        self.log_message.emit(f"已删除片段JSON: {os.path.basename(json_path)}")

                except OSError as e:
                    self.log_message.emit(f"清理文件 {os.path.basename(chunk_path)} 失败: {e}")
            self.owned_temp_chunks = []

        # 清理提取的音频文件（如果是从视频提取的）
        if (hasattr(self, 'original_file_path') and self.original_file_path and
            self.original_file_path != self.file_path):
            try:
                if os.path.exists(self.file_path):
                    os.remove(self.file_path)
                    self.log_message.emit(f"已删除提取的音频文件: {os.path.basename(self.file_path)}")
            except OSError as e:
                self.log_message.emit(f"清理提取的音频文件失败: {e}")

        self.log_message.emit("临时文件清理完成。")