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

from api_client import ElevenLabsSTTClient
from srt_processor import create_srt_from_json

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
                 pause_threshold: float, max_subtitle_duration: float, split_duration_min: int,
                 original_file_path: Optional[str] = None, ffmpeg_available: bool = False,
                 restore_state: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.file_path = file_path
        self.original_file_path = original_file_path if original_file_path else file_path
        self.language_code = language_code
        self.tag_audio_events = tag_audio_events
        self.pause_threshold = pause_threshold
        self.max_subtitle_duration = max_subtitle_duration
        self.split_duration_sec = split_duration_min * 60
        self.ffmpeg_available = ffmpeg_available
        self.restore_state = restore_state
        
        self.uploader = None
        self.client = ElevenLabsSTTClient(signals_forwarder=self, ffmpeg_available=self.ffmpeg_available)
        
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
            "pause_threshold": self.pause_threshold,
            "max_subtitle_duration": self.max_subtitle_duration,
            "split_duration_min": self.split_duration_sec / 60,
            "ffmpeg_available": self.ffmpeg_available,
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
            self._process_next_chunk()
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

        if self.current_chunk_index < self.total_chunks:
            self.time_offset = self.current_chunk_index * self.split_duration_sec
            chunk_path = self.temp_chunks[self.current_chunk_index]
            
            self.log_message.emit("-" * 20)
            self.log_message.emit(f"正在处理片段 {self.current_chunk_index + 1}/{self.total_chunks}: {os.path.basename(chunk_path)}")
            self.chunk_progress.emit(f"正在处理片段 {self.current_chunk_index + 1}/{self.total_chunks}")
            
            self._process_single_file(chunk_path)
        else:
            self._finalize_task()

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
            pause_threshold=self.pause_threshold,
            max_subtitle_duration=self.max_subtitle_duration
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
        if self.uploader:
            self.uploader.cancel()
        self._cleanup_chunks()

    def _cleanup_chunks(self):
        """清理所有临时的音频片段文件。"""
        if not self.owned_temp_chunks:
            return
        self.log_message.emit("正在清理所有临时音频片段...")
        for chunk_path in self.owned_temp_chunks:
            try:
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)
            except OSError as e:
                self.log_message.emit(f"清理文件 {os.path.basename(chunk_path)} 失败: {e}")
        self.owned_temp_chunks = []