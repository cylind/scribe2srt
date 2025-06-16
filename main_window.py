# -*- coding: utf-8 -*-

"""
主窗口模块，负责UI的显示、事件处理和与核心逻辑的交互。
"""

import sys
import os
import json
import ctypes
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QFileDialog, QMessageBox, QComboBox, QProgressBar
)
from PySide6.QtCore import QThread, Qt, QThreadPool, QTimer
from PySide6.QtGui import QIcon

# --- 从重构后的模块中导入 ---
from core.config import (
    LANGUAGES, SETTINGS_FILE, PAUSE_THRESHOLD, MAX_SUBTITLE_DURATION,
    DEFAULT_SPLIT_DURATION_MIN, DEFAULT_SUBTITLE_SETTINGS
)
from core.worker import Worker
from core.ffmpeg_utils import is_ffmpeg_available, extract_audio, get_media_info
from srt_processor import create_srt_from_json
from ui.widgets import CustomCheckBox
from ui.settings_dialog import SettingsDialog


# --- Codec to Container Mapping ---
CODEC_EXTENSION_MAP = {
    "aac": ".m4a",
    "ac3": ".m4a",
    "eac3": ".m4a",
    "opus": ".ogg",
    "vorbis": ".ogg",
    "mp3": ".mp3",
    "flac": ".flac",
    "pcm": ".wav"
}
DEFAULT_AUDIO_EXTENSION = ".mka"  # Matroska Audio for unknown/other codecs


class MainWindow(QMainWindow):
    """
    应用程序的主窗口。
    管理UI交互，并将处理任务委托给后台Worker。
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scribe -> SRT (Powered by ElevenLabs)")
        self.setGeometry(100, 100, 750, 600)
        self.setAcceptDrops(True)
        self._apply_dark_mode_title_bar()

        self.selected_file_path = None
        self.thread = None
        self.worker = None
        self.temp_audio_file = None
        self.upload_complete_logged = False
        
        # 用于重试逻辑的状态存储
        self._pending_retry_state: Optional[Dict[str, Any]] = None
        
        self.load_settings()
        self.setup_ui()
        
        self.ffmpeg_available = self._check_ffmpeg()
        self._connect_signals()

    def setup_ui(self):
        """初始化和布局UI控件。"""
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # --- 文件拖放区域 ---
        self.file_drop_label = QLabel("将音视频或JSON文件拖拽到此处\n\n或")
        self.file_drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_drop_label.setObjectName("FileDropLabel")
        
        self.select_button = QPushButton("点击选择文件")
        
        file_layout = QVBoxLayout()
        file_layout.addWidget(self.file_drop_label)
        file_layout.addWidget(self.select_button, 0, Qt.AlignmentFlag.AlignCenter)
        main_layout.addLayout(file_layout)
        
        # --- 选项区域 ---
        options_layout = QHBoxLayout()
        options_layout.setSpacing(10)
        
        self.lang_label = QLabel("源语言:")
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES.keys())
        self.lang_combo.setCurrentText("自动检测")
        
        self.audio_events_checkbox = CustomCheckBox("识别声音事件")
        self.audio_events_checkbox.setChecked(False)
        
        self.settings_button = QPushButton("字幕设置")

        options_layout.addWidget(self.lang_label)
        options_layout.addWidget(self.lang_combo)
        options_layout.addSpacing(20)
        options_layout.addWidget(self.audio_events_checkbox)
        options_layout.addStretch(1)
        options_layout.addWidget(self.settings_button)
        main_layout.addLayout(options_layout)
        
        # --- 进度条和标签 ---
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        
        main_layout.addWidget(self.progress_label)
        main_layout.addWidget(self.progress_bar)
        
        # --- 操作按钮 ---
        action_layout = QHBoxLayout()
        self.start_button = QPushButton("生成字幕")
        self.start_button.setObjectName("StartButton")
        self.start_button.setEnabled(False)
        
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setVisible(False)
        
        action_layout.addWidget(self.start_button)
        action_layout.addWidget(self.cancel_button)
        main_layout.addLayout(action_layout)
        
        # --- 日志区域 ---
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("处理日志将在这里显示...")
        main_layout.addWidget(self.log_area)
        
        self.setCentralWidget(container)

    def _connect_signals(self):
        """连接所有UI控件的信号到槽函数。"""
        self.select_button.clicked.connect(self.select_file)
        self.start_button.clicked.connect(self.start_process)
        self.cancel_button.clicked.connect(self.cancel_process)
        self.settings_button.clicked.connect(self.open_settings_dialog)

    def _apply_dark_mode_title_bar(self):
        """(仅Windows) 尝试设置窗口标题栏为暗色模式。"""
        if sys.platform == "win32":
            try:
                HWND = self.winId()
                if HWND:
                    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                    value = ctypes.c_int(1)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        HWND, DWMWA_USE_IMMERSIVE_DARK_MODE,
                        ctypes.byref(value), ctypes.sizeof(value)
                    )
            except (AttributeError, TypeError, OSError) as e:
                print(f"无法设置暗色标题栏: {e}")

    def _check_ffmpeg(self) -> bool:
        """检查FFmpeg是否可用并记录日志。"""
        available = is_ffmpeg_available()
        if available:
            self.log_area.append("✅ FFmpeg 已找到，将启用视频文件处理。")
        else:
            self.log_area.append("⚠️ 未找到 FFmpeg。处理视频时将尝试直接上传原始文件。")
            self.log_area.append("   为获得最佳体验，推荐安装 FFmpeg 并将其添加到系统 PATH。")
        return available

    # --- 设置管理 ---
    def load_settings(self):
        """从文件加载设置，如果文件不存在则使用默认值。"""
        # 使用新的默认设置结构
        self.settings = {
            # 基础设置
            "pause_threshold": DEFAULT_SUBTITLE_SETTINGS["pause_threshold"],
            "split_duration_min": DEFAULT_SPLIT_DURATION_MIN,

            # 专业字幕设置
            "min_subtitle_duration": DEFAULT_SUBTITLE_SETTINGS["min_subtitle_duration"],
            "max_subtitle_duration": DEFAULT_SUBTITLE_SETTINGS["max_subtitle_duration"],
            "min_subtitle_gap": DEFAULT_SUBTITLE_SETTINGS["min_subtitle_gap"],

            # CPS设置
            "cjk_cps": DEFAULT_SUBTITLE_SETTINGS["cjk_cps"],
            "latin_cps": DEFAULT_SUBTITLE_SETTINGS["latin_cps"],

            # CPL设置
            "cjk_chars_per_line": DEFAULT_SUBTITLE_SETTINGS["cjk_chars_per_line"],
            "latin_chars_per_line": DEFAULT_SUBTITLE_SETTINGS["latin_chars_per_line"],
        }

        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    self.settings.update(loaded_settings)
            except (json.JSONDecodeError, TypeError):
                print(f"警告: 无法解析 {SETTINGS_FILE}。将使用默认设置。")

        # 为了向后兼容，保留这些属性
        self.pause_threshold = self.settings["pause_threshold"]
        self.max_subtitle_duration = self.settings["max_subtitle_duration"]
        self.split_duration_min = self.settings["split_duration_min"]

    def save_settings(self):
        """保存当前设置到文件。"""
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=4)

    def open_settings_dialog(self):
        """打开设置对话框并处理结果。"""
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            new_settings = dialog.get_settings()

            # 更新所有设置
            self.settings.update(new_settings)

            # 为了向后兼容，更新这些属性
            self.pause_threshold = new_settings["pause_threshold"]
            self.max_subtitle_duration = new_settings["max_subtitle_duration"]
            self.split_duration_min = new_settings["split_duration_min"]

            self.save_settings()
            self.log_area.append("字幕生成设置已更新。")

    # --- 文件处理与UI状态 ---
    def set_file(self, file_path: Optional[str]):
        """设置当前要处理的文件并更新UI。"""
        if file_path and os.path.exists(file_path):
            self.selected_file_path = file_path
            file_name = os.path.basename(file_path)
            self.file_drop_label.setText(f"已选择:\n{file_name}")
            self.file_drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.start_button.setEnabled(True)
            self.log_area.clear()
        else:
            self.selected_file_path = None
            self.file_drop_label.setText("将音视频或JSON文件拖拽到此处\n\n或")
            self.file_drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.start_button.setEnabled(False)

    def select_file(self):
        """打开文件选择对话框。"""
        dialog_title = "选择文件"
        dialog_filter = (
            "支持的文件 (*.mp3 *.wav *.flac *.m4a *.aac *.mp4 *.mov *.mkv *.json);;"
            "所有文件 (*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(self, dialog_title, "", dialog_filter)
        self.set_file(file_path)

    def set_ui_enabled(self, enabled: bool):
        """启用或禁用UI控件以防止在处理期间进行交互。"""
        self.start_button.setVisible(enabled)
        self.cancel_button.setVisible(not enabled)
        self.start_button.setEnabled(enabled and self.selected_file_path is not None)
        self.select_button.setEnabled(enabled)
        self.lang_combo.setEnabled(enabled)
        self.audio_events_checkbox.setEnabled(enabled)
        self.settings_button.setEnabled(enabled)
        self.setAcceptDrops(enabled)

    def reset_ui_after_task(self):
        """任务完成后重置UI到初始状态。"""
        self.set_ui_enabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.set_file(None)

    # --- 核心处理流程 ---
    def start_process(self):
        """开始处理选定的文件。"""
        if not self.selected_file_path:
            QMessageBox.warning(self, "警告", "请先选择一个文件！")
            return

        _, ext = os.path.splitext(self.selected_file_path)
        if ext.lower() == '.json':
            self._process_json_file_directly(self.selected_file_path)
            return

        self.set_ui_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("准备中...")
        self.progress_label.setVisible(True)
        
        file_to_process = self.selected_file_path
        
        video_extensions = ['.mp4', '.mkv', '.mov', '.avi', '.flv', '.webm']
        if ext.lower() in video_extensions:
            if self.ffmpeg_available:
                self.log_area.append("检测到视频文件，正在分析音频流...")
                
                media_info = get_media_info(self.selected_file_path, self.log_area.append)
                codec = media_info.get("codec") if media_info else None
                
                if not codec:
                    self.on_task_error("无法检测到视频中的音频编码，无法继续提取。")
                    return

                extension = CODEC_EXTENSION_MAP.get(codec, DEFAULT_AUDIO_EXTENSION)
                self.log_area.append(f"检测到音频编码: {codec}。将使用 '{extension}' 容器进行提取。")

                base_name, _ = os.path.splitext(os.path.basename(self.selected_file_path))
                temp_audio_path = os.path.join(os.path.dirname(self.selected_file_path), f"temp_audio_{base_name}{extension}")
                
                self.log_area.append("正在提取音频...")
                if not extract_audio(self.selected_file_path, temp_audio_path, self.log_area.append):
                    self.on_task_error("音频提取失败。")
                    return
                
                self.temp_audio_file = temp_audio_path
                file_to_process = temp_audio_path
            else:
                QMessageBox.warning(self, "功能限制", "检测到视频文件但未找到 FFmpeg。\n将尝试直接上传原始文件，但这可能失败。")
                self.log_area.append("警告: 正在尝试直接上传视频文件...")
        
        self._execute_transcription_task(file_to_process, self.selected_file_path)

    def _process_json_file_directly(self, json_path: str):
        """直接从JSON文件生成SRT，不进行API调用。"""
        self.set_ui_enabled(False)
        self.log_area.clear()
        self.log_area.append("="*50)
        self.log_area.append(f"检测到JSON文件，直接生成SRT...")

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            srt_data = create_srt_from_json(
                json_data,
                pause_threshold=self.pause_threshold,
                max_subtitle_duration=self.max_subtitle_duration,
                subtitle_settings=self.settings
            )
            if not srt_data and not json_data.get("words"):
                raise ValueError("JSON文件可能为空或不包含'words'数据。")

            output_srt_path = os.path.splitext(json_path)[0] + ".srt"
            with open(output_srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_data)

            self.log_area.append(f"SRT字幕文件已保存到:\n{output_srt_path}")
            QMessageBox.information(self, "成功", "JSON文件处理成功！")
        except (Exception) as e:
            self.on_task_error(f"处理JSON文件时出错: {e}")
        finally:
            self.reset_ui_after_task()

    def _execute_transcription_task(self, file_to_process, original_file, restore_state=None):
        """创建并启动后台Worker线程来执行转录任务。"""
        if self.thread and self.thread.isRunning():
            QMessageBox.warning(self, "提示", "一个任务已经在运行中。")
            return

        self.upload_complete_logged = False
        self.set_ui_enabled(False)
        
        if not restore_state:
            self.log_area.append("开始执行转录任务...")
        
        self.thread = QThread()
        self.worker = Worker(
            file_path=file_to_process,
            language_code=LANGUAGES.get(self.lang_combo.currentText(), "auto"),
            tag_audio_events=self.audio_events_checkbox.isChecked(),
            original_file_path=original_file,
            pause_threshold=self.pause_threshold,
            max_subtitle_duration=self.max_subtitle_duration,
            split_duration_min=self.split_duration_min,
            ffmpeg_available=self.ffmpeg_available,
            restore_state=restore_state,
            subtitle_settings=self.settings
        )
        self.worker.moveToThread(self.thread)

        # 连接Worker信号
        self.worker.finished.connect(self.on_task_finished)
        self.worker.error.connect(self.on_task_error)
        self.worker.log_message.connect(self.log_area.append)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.chunk_progress.connect(self.update_chunk_progress)
        
        # 线程结束后，统一由 _handle_task_completion 处理
        self.thread.finished.connect(self._handle_task_completion)
        self.thread.started.connect(self.worker.run)
        
        self.thread.start()

    def cancel_process(self):
        """请求取消当前正在运行的任务。"""
        self.log_area.append("\n正在请求取消任务...")
        self._pending_retry_state = None # 取消时清除重试状态
        if self.worker:
            self.worker.request_cancellation()

    # --- 信号槽函数 ---
    def on_task_finished(self, message: str):
        """任务成功完成时的处理。"""
        QMessageBox.information(self, "成功", message)
        self.log_area.append(f"\n✅ {message}")
        if self.thread:
            self.thread.quit()

    def on_task_error(self, message: str):
        """任务失败时的处理，提供重试选项。"""
        self.log_area.append(f"\n❌ 任务失败: {message}")
        
        if "用户取消" in message or "cancelled" in message.lower():
            self._pending_retry_state = None
        else:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setWindowTitle("错误")
            msg_box.setText("任务执行失败。")
            msg_box.setInformativeText(message)
            retry_button = msg_box.addButton("重试", QMessageBox.ButtonRole.AcceptRole)
            msg_box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
            
            msg_box.exec()
            
            if msg_box.clickedButton() == retry_button:
                # 保存状态以供重试
                if self.worker:
                    self._pending_retry_state = self.worker.get_state()
            else:
                self._pending_retry_state = None

        if self.thread:
            self.thread.quit()

    def update_progress(self, bytes_sent, total_bytes):
        """更新上传进度条。"""
        if total_bytes > 0:
            percentage = int((bytes_sent / total_bytes) * 100)
            self.progress_bar.setValue(percentage)
            
            sent_mb = bytes_sent / (1024 * 1024)
            total_mb = total_bytes / (1024 * 1024)
            
            if self.worker and self.worker.total_chunks > 1:
                chunk_text = f"片段 {self.worker.current_chunk_index + 1}/{self.worker.total_chunks}"
                self.progress_label.setText(f"{chunk_text} - 上传中: {sent_mb:.2f}MB / {total_mb:.2f}MB")
            else:
                self.progress_label.setText(f"正在上传: {sent_mb:.2f} MB / {total_mb:.2f} MB")

            if percentage == 100 and not self.upload_complete_logged:
                self.log_area.append("上传成功！等待服务器转录...")
                self.upload_complete_logged = True
        else:
            sent_mb = bytes_sent / (1024 * 1024)
            self.progress_label.setText(f"正在上传: {sent_mb:.2f} MB")

    def update_chunk_progress(self, message: str):
        """更新多片段处理时的进度标签。"""
        self.progress_label.setText(message)
        self.progress_bar.setValue(0)

    def _handle_task_completion(self):
        """
        统一处理任务结束后的所有逻辑（成功、失败、重试）。
        这是确保线程安全和状态正确的关键。
        """
        self.log_area.append("线程已结束，正在清理资源...")

        # 将待处理的重试状态捕获到局部变量中
        retry_state = self._pending_retry_state
        self._pending_retry_state = None  # 立即清除实例变量

        # 清理旧的worker和thread
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        if self.thread:
            self.thread.deleteLater()
            self.thread = None
        
        # 检查是否有待处理的重试任务
        if retry_state:
            self.log_area.append("\n... 用户选择重试 ...")
            self.log_area.append(f"将从片段 {retry_state.get('current_chunk_index', 0) + 1} 处恢复任务。")
            
            # 使用QTimer和捕获的局部变量来安全地启动重试
            QTimer.singleShot(100, lambda state=retry_state: self._execute_transcription_task(
                state.get("original_file_path"),
                state.get("original_file_path"),
                restore_state=state
            ))
        else:
            # 如果没有重试任务，则清理所有临时文件并重置UI
            self.cleanup_temp_files()
            self.reset_ui_after_task()

    def cleanup_temp_files(self):
        """清理所有临时文件（提取的音频和分块）。"""
        if self.temp_audio_file and os.path.exists(self.temp_audio_file):
            try:
                os.remove(self.temp_audio_file)
                self.log_area.append(f"已清理临时音频文件: {os.path.basename(self.temp_audio_file)}")
                self.temp_audio_file = None
            except OSError as e:
                self.log_area.append(f"清理临时音频文件失败: {e}")
        # Worker负责清理自己的分块文件

    # --- 事件处理 ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            self.set_file(file_path)

    def closeEvent(self, event):
        """关闭窗口前确保所有后台任务都已清理。"""
        self.cancel_process()
        if self.thread and self.thread.isRunning():
            self.thread.wait(3000)
        QThreadPool.globalInstance().waitForDone(-1)
        self.cleanup_temp_files()
        event.accept()