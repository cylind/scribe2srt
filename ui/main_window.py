# -*- coding: utf-8 -*-

"""
主窗口模块，负责UI的显示、事件处理和与核心逻辑的交互。
"""

import sys
import os
import json
import ctypes
from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QFileDialog, QMessageBox, QComboBox, QProgressBar
)
from PySide6.QtCore import QThread, Qt, QThreadPool, QTimer
from PySide6.QtGui import QIcon

# --- 从重构后的模块中导入 ---
from core.config import (
    LANGUAGES, SETTINGS_FILE, MAX_SUBTITLE_DURATION,
    DEFAULT_SPLIT_DURATION_MIN, DEFAULT_SUBTITLE_SETTINGS,
    PROVIDERS, DEFAULT_PROVIDER
)
from core.worker import Worker
from core.ffmpeg_utils import is_ffmpeg_available, extract_audio, get_media_info
from core.srt_processor import create_srt_from_json
from .widgets import CustomCheckBox
from .settings_dialog import SettingsDialog
from .async_settings_dialog import AsyncSettingsDialog
from .segmented_progress_bar import SegmentedProgressBar


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
        self.setWindowTitle("Scribe -> SRT (Powered by ElevenLabs & 60dB)")
        self.setGeometry(100, 100, 750, 600)
        self.setAcceptDrops(True)
        self._apply_dark_mode_title_bar()

        self.selected_file_paths: List[str] = []
        self.current_processing_file: Optional[str] = None
        self.batch_queue: List[str] = []
        self.batch_results: List[Dict[str, Any]] = []
        self.current_batch_index: int = -1
        self.batch_mode: bool = False
        self.batch_cancelled: bool = False
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
        
        self.provider_label = QLabel("识别引擎:")
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(PROVIDERS.keys())
        # 根据已保存的设置选中上次使用的引擎
        saved_provider = self.settings.get("stt_provider", DEFAULT_PROVIDER)
        provider_display = next(
            (name for name, code in PROVIDERS.items() if code == saved_provider),
            next(iter(PROVIDERS.keys()))
        )
        self.provider_combo.setCurrentText(provider_display)

        self.lang_label = QLabel("源语言:")
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES.keys())
        self.lang_combo.setCurrentText("自动检测")
        
        self.audio_events_checkbox = CustomCheckBox("识别声音事件")
        self.audio_events_checkbox.setChecked(False)

        self.async_settings_button = QPushButton("并发处理设置")
        self.settings_button = QPushButton("字幕设置")

        options_layout.addWidget(self.provider_label)
        options_layout.addWidget(self.provider_combo)
        options_layout.addSpacing(20)
        options_layout.addWidget(self.lang_label)
        options_layout.addWidget(self.lang_combo)
        options_layout.addSpacing(20)
        options_layout.addWidget(self.audio_events_checkbox)
        options_layout.addStretch(1)
        options_layout.addWidget(self.async_settings_button)
        options_layout.addWidget(self.settings_button)
        main_layout.addLayout(options_layout)
        
        # --- 进度条和标签 ---
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 使用新的分段进度条
        self.segmented_progress_bar = SegmentedProgressBar()
        self.segmented_progress_bar.setVisible(False)

        main_layout.addWidget(self.progress_label)
        main_layout.addWidget(self.segmented_progress_bar)
        
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
        self.select_button.clicked.connect(self.select_files)
        self.start_button.clicked.connect(self.start_process)
        self.cancel_button.clicked.connect(self.cancel_process)
        self.async_settings_button.clicked.connect(self.open_async_settings_dialog)
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
        # 使用新的默认设置结构（移除pause_threshold）
        self.settings = {
            # 基础设置
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

            # 异步处理设置
            "enable_async_processing": True,
            "max_concurrent_chunks": 3,
            "max_retries": 3,
            "api_rate_limit_per_minute": 30,

            # STT 提供商设置
            "stt_provider": DEFAULT_PROVIDER,
            "sixtydb_api_key": "",
        }

        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    self.settings.update(loaded_settings)
            except (json.JSONDecodeError, TypeError):
                print(f"警告: 无法解析 {SETTINGS_FILE}。将使用默认设置。")

        # 为了向后兼容，保留这些属性（移除pause_threshold）
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

            # 为了向后兼容，更新这些属性（移除pause_threshold）
            self.max_subtitle_duration = new_settings["max_subtitle_duration"]
            self.split_duration_min = new_settings["split_duration_min"]

            self.save_settings()
            self.log_area.append("字幕生成设置已更新。")

    def open_async_settings_dialog(self):
        """打开并发处理设置对话框并处理结果。"""
        dialog = AsyncSettingsDialog(self.settings, self)
        if dialog.exec():
            new_settings = dialog.get_settings()

            # 更新异步处理设置
            self.settings.update(new_settings)

            # 为了向后兼容，更新这些属性
            self.split_duration_min = new_settings["split_duration_min"]

            self.save_settings()
            self.log_area.append("并发处理设置已更新。")

    # --- 文件处理与UI状态 ---
    def set_files(self, file_paths: Optional[List[str]]):
        """设置当前要处理的文件并更新UI。"""
        self.selected_file_paths = []
        self.current_processing_file = None

        if file_paths:
            valid_paths = [path for path in file_paths if path and os.path.exists(path)]
            self.selected_file_paths = valid_paths

        if self.selected_file_paths:
            if len(self.selected_file_paths) == 1:
                file_name = os.path.basename(self.selected_file_paths[0])
                self.file_drop_label.setText(f"已选择:\n{file_name}")
            else:
                first_name = os.path.basename(self.selected_file_paths[0])
                self.file_drop_label.setText(
                    f"已选择 {len(self.selected_file_paths)} 个文件\n首个: {first_name}"
                )
            self.file_drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.start_button.setEnabled(True)
            self.log_area.clear()
        else:
            self.file_drop_label.setText("将音视频或JSON文件拖拽到此处\n\n或")
            self.file_drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.start_button.setEnabled(False)

    def select_files(self):
        """打开文件选择对话框。"""
        dialog_title = "选择文件"
        dialog_filter = (
            "支持的文件 (*.mp3 *.wav *.flac *.m4a *.aac *.mp4 *.mov *.mkv *.json);;"
            "所有文件 (*)"
        )
        file_paths, _ = QFileDialog.getOpenFileNames(self, dialog_title, "", dialog_filter)
        self.set_files(file_paths)

    def set_ui_enabled(self, enabled: bool):
        """启用或禁用UI控件以防止在处理期间进行交互。"""
        self.start_button.setVisible(enabled)
        self.cancel_button.setVisible(not enabled)
        self.start_button.setEnabled(enabled and bool(self.selected_file_paths))
        self.select_button.setEnabled(enabled)
        self.provider_combo.setEnabled(enabled)
        self.lang_combo.setEnabled(enabled)
        self.audio_events_checkbox.setEnabled(enabled)
        self.async_settings_button.setEnabled(enabled)
        self.settings_button.setEnabled(enabled)
        self.setAcceptDrops(enabled)

    def reset_ui_after_task(self):
        """任务完成后重置UI到初始状态。"""
        self.set_ui_enabled(True)
        self.segmented_progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.set_files([])

    # --- 核心处理流程 ---
    def start_process(self):
        """开始处理选定的文件。"""
        if not self.selected_file_paths:
            QMessageBox.warning(self, "警告", "请先选择至少一个文件！")
            return

        # 校验所选识别引擎所需的凭据
        provider_code = PROVIDERS.get(self.provider_combo.currentText(), DEFAULT_PROVIDER)
        if provider_code == "60db" and not self.settings.get("sixtydb_api_key", "").strip():
            QMessageBox.warning(
                self, "缺少 API Key",
                "已选择 60dB 引擎，但尚未配置 API Key。\n请在「字幕设置」中填写 60dB API Key 后重试。"
            )
            return

        # 记住本次选择的引擎
        if self.settings.get("stt_provider") != provider_code:
            self.settings["stt_provider"] = provider_code
            self.save_settings()

        self.batch_queue = list(self.selected_file_paths)
        self.batch_mode = len(self.batch_queue) > 1
        self.batch_cancelled = False
        self.batch_results = []
        self.current_batch_index = -1
        self.current_processing_file = None
        self.temp_audio_file = None
        self.upload_complete_logged = False

        if self.batch_mode:
            self.log_area.append("=" * 50)
            self.log_area.append(f"开始批量处理，共 {len(self.batch_queue)} 个文件。")

        self.set_ui_enabled(False)
        self._process_next_batch_file()

    def _process_next_batch_file(self):
        """处理待处理队列中的下一个文件。"""
        self.current_batch_index += 1

        if self.current_batch_index >= len(self.batch_queue):
            self._finish_batch_processing()
            return

        file_path = self.batch_queue[self.current_batch_index]
        self.current_processing_file = file_path
        display_name = os.path.basename(file_path)

        if self.batch_mode:
            self.log_area.append("=" * 50)
            self.log_area.append(
                f"正在处理第 {self.current_batch_index + 1}/{len(self.batch_queue)} 个文件: {display_name}"
            )
            self.file_drop_label.setText(
                f"批量处理中 ({self.current_batch_index + 1}/{len(self.batch_queue)}):\n{display_name}"
            )
        else:
            self.log_area.clear()
            self.log_area.append("=" * 50)
            self.log_area.append(f"开始处理文件: {display_name}")
            self.file_drop_label.setText(f"已选择:\n{display_name}")

        self.file_drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 重置进度显示
        self.segmented_progress_bar.reset()
        self.segmented_progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.progress_label.setText("")
        self.upload_complete_logged = False
        self.temp_audio_file = None

        _, ext = os.path.splitext(file_path)
        if ext.lower() == '.json':
            self._process_json_file_directly(file_path, from_batch=self.batch_mode)
        else:
            self._begin_media_processing(file_path)

    def _begin_media_processing(self, source_file: str):
        """准备并启动音视频文件的处理流程。"""
        self.segmented_progress_bar.setVisible(True)
        self.segmented_progress_bar.set_single_file_mode(source_file)
        self.progress_label.setText("准备中...")
        self.progress_label.setVisible(True)

        file_to_process = source_file
        _, ext = os.path.splitext(source_file)

        video_extensions = ['.mp4', '.mkv', '.mov', '.avi', '.flv', '.webm']
        if ext.lower() in video_extensions:
            if self.ffmpeg_available:
                self.log_area.append("检测到视频文件，正在分析音频流...")

                media_info = get_media_info(source_file, self.log_area.append)
                codec = media_info.get("codec") if media_info else None

                if not codec:
                    error_msg = "无法检测到视频中的音频编码，无法继续提取。"
                    if self.batch_mode:
                        self.log_area.append(f"\n❌ {error_msg}")
                        self._record_batch_result("error", error_msg)
                        self._finalize_current_batch_step()
                    else:
                        self.on_task_error(error_msg)
                        self.set_ui_enabled(True)
                        self.segmented_progress_bar.setVisible(False)
                        self.progress_label.setVisible(False)
                        self.progress_label.setText("")
                    return

                extension = CODEC_EXTENSION_MAP.get(codec, DEFAULT_AUDIO_EXTENSION)
                self.log_area.append(f"检测到音频编码: {codec}。将使用 '{extension}' 容器进行提取。")

                base_name, _ = os.path.splitext(os.path.basename(source_file))
                temp_audio_path = os.path.join(os.path.dirname(source_file), f"temp_audio_{base_name}{extension}")

                self.log_area.append("正在提取音频...")
                if not extract_audio(source_file, temp_audio_path, self.log_area.append):
                    error_msg = "音频提取失败。"
                    if self.batch_mode:
                        self.log_area.append(f"\n❌ {error_msg}")
                        self._record_batch_result("error", error_msg)
                        self._finalize_current_batch_step()
                    else:
                        self.on_task_error(error_msg)
                        self.set_ui_enabled(True)
                        self.segmented_progress_bar.setVisible(False)
                        self.progress_label.setVisible(False)
                        self.progress_label.setText("")
                    return

                self.temp_audio_file = temp_audio_path
                file_to_process = temp_audio_path
            else:
                warning_msg = "检测到视频文件但未找到 FFmpeg。\n将尝试直接上传原始文件，但这可能失败。"
                if not self.batch_mode:
                    QMessageBox.warning(self, "功能限制", warning_msg)
                self.log_area.append("⚠️ 未找到 FFmpeg，尝试直接上传视频文件。")

        self._execute_transcription_task(file_to_process, source_file)

    def _process_json_file_directly(self, json_path: str, from_batch: bool = False):
        """直接从JSON文件生成SRT，不进行API调用。"""
        self.set_ui_enabled(False)
        if not from_batch:
            self.log_area.clear()
        self.log_area.append("=" * 50)
        self.log_area.append("检测到JSON文件，直接生成SRT...")

        success = False
        message = ""

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            srt_data = create_srt_from_json(
                json_data,
                max_subtitle_duration=self.max_subtitle_duration,
                subtitle_settings=self.settings
            )
            if not srt_data and not json_data.get("words"):
                raise ValueError("JSON文件可能为空或不包含'words'数据。")

            output_srt_path = os.path.splitext(json_path)[0] + ".srt"
            with open(output_srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_data)

            message = f"SRT字幕文件已保存到:\n{output_srt_path}"
            self.log_area.append(message)
            if not from_batch:
                QMessageBox.information(self, "成功", "JSON文件处理成功！")
            success = True
        except Exception as e:
            message = f"处理JSON文件时出错: {e}"
            if from_batch:
                self.log_area.append(f"\n❌ {message}")
            else:
                self.on_task_error(message)
        finally:
            if from_batch:
                status = "success" if success else "error"
                self._record_batch_result(status, message)
                self._finalize_current_batch_step()
            else:
                self.reset_ui_after_task()

    def _record_batch_result(self, status: str, message: str):
        """记录当前文件的批量处理结果。"""
        if not self.batch_mode or not self.current_processing_file:
            return

        self.batch_results.append({
            "file": self.current_processing_file,
            "status": status,
            "message": message
        })

    def _finalize_current_batch_step(self):
        """在当前文件处理完成后调度下一步。"""
        if not self.batch_mode:
            self.reset_ui_after_task()
            return

        if self.batch_cancelled:
            self._finish_batch_processing()
            return

        if self.current_batch_index < len(self.batch_queue) - 1:
            QTimer.singleShot(400, self._process_next_batch_file)
        else:
            self._finish_batch_processing()

    def _finish_batch_processing(self):
        """结束批量处理并输出总结。"""
        if not self.batch_mode:
            return

        total = len(self.batch_queue)
        success_items = [item for item in self.batch_results if item.get("status") == "success"]
        error_items = [item for item in self.batch_results if item.get("status") == "error"]
        cancelled_items = [item for item in self.batch_results if item.get("status") == "cancelled"]
        remaining = max(0, total - (self.current_batch_index + 1))

        summary_parts = []
        if success_items:
            summary_parts.append(f"成功 {len(success_items)}")
        if error_items:
            summary_parts.append(f"失败 {len(error_items)}")
        if cancelled_items:
            summary_parts.append(f"取消 {len(cancelled_items)}")
        if remaining:
            summary_parts.append(f"未处理 {remaining}")

        summary_text = "，".join(summary_parts) if summary_parts else "无任务执行"

        self.log_area.append("\n" + "=" * 50)
        self.log_area.append(f"批量处理完成（共 {total} 个文件）：{summary_text}")

        if error_items:
            self.log_area.append("失败列表：")
            for item in error_items:
                self.log_area.append(f" - {os.path.basename(item['file'])}: {item['message']}")

        if cancelled_items:
            self.log_area.append("已取消：")
            for item in cancelled_items:
                self.log_area.append(f" - {os.path.basename(item['file'])}: {item['message']}")

        if remaining:
            self.log_area.append(f"尚有 {remaining} 个文件未处理。")

        title = "批量处理完成" if not self.batch_cancelled else "批量处理已取消"
        QMessageBox.information(self, title, f"批量处理完成，共 {total} 个文件。\n{summary_text}")

        # 重置批量状态
        self.batch_mode = False
        self.batch_queue = []
        self.batch_results = []
        self.batch_cancelled = False
        self.current_batch_index = -1
        self.current_processing_file = None

        self.reset_ui_after_task()

    def _execute_transcription_task(self, file_to_process, original_file, restore_state=None):
        """创建并启动后台Worker线程来执行转录任务。"""
        if self.thread and self.thread.isRunning():
            QMessageBox.warning(self, "提示", "一个任务已经在运行中。")
            return

        # 只在非重试模式下设置UI状态（重试时已在 _setup_retry_ui 中设置）
        if not restore_state:
            self.upload_complete_logged = False
            self.set_ui_enabled(False)
            self.log_area.append("开始执行转录任务...")
        else:
            # 重试模式下，只重置上传完成标志（UI状态已在 _setup_retry_ui 中设置）
            self.upload_complete_logged = False

        self.thread = QThread()
        self.worker = Worker(
            file_path=file_to_process,
            language_code=LANGUAGES.get(self.lang_combo.currentText(), "auto"),
            tag_audio_events=self.audio_events_checkbox.isChecked(),
            original_file_path=original_file,
            # 移除pause_threshold参数
            max_subtitle_duration=self.max_subtitle_duration,
            split_duration_min=self.split_duration_min,
            ffmpeg_available=self.ffmpeg_available,
            restore_state=restore_state,
            subtitle_settings=self.settings,
            # 传递异步处理设置
            enable_async_processing=self.settings.get("enable_async_processing", True),
            max_concurrent_chunks=self.settings.get("max_concurrent_chunks", 3),
            max_retries=self.settings.get("max_retries", 3),
            api_rate_limit_per_minute=self.settings.get("api_rate_limit_per_minute", 30),
            # STT 提供商与凭据
            stt_provider=PROVIDERS.get(self.provider_combo.currentText(), DEFAULT_PROVIDER),
            api_key=self.settings.get("sixtydb_api_key", "")
        )
        self.worker.moveToThread(self.thread)

        # 连接Worker信号
        self.worker.finished.connect(self.on_task_finished)
        self.worker.error.connect(self.on_task_error)
        self.worker.log_message.connect(self.log_area.append)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.chunk_progress.connect(self.update_chunk_progress)
        self.worker.chunks_ready.connect(self.on_chunks_ready)

        # 线程结束后，统一由 _handle_task_completion 处理
        self.thread.finished.connect(self._handle_task_completion)
        self.thread.started.connect(self.worker.run)

        self.thread.start()

    def cancel_process(self):
        """请求取消当前正在运行的任务。"""
        self.log_area.append("\n正在请求取消任务...")
        self._pending_retry_state = None # 取消时清除重试状态

        if self.batch_mode:
            self.batch_cancelled = True
            self.log_area.append("批量模式：后续文件将被跳过。")

        # 取消时清理临时文件
        self._cleanup_temp_audio_file()

        if self.worker:
            self.worker.request_cancellation()

    # --- 信号槽函数 ---
    def on_task_finished(self, message: str):
        """任务成功完成时的处理。"""
        display_name = os.path.basename(self.current_processing_file) if self.current_processing_file else ""

        if self.batch_mode:
            if display_name:
                self.log_area.append(f"\n✅ {display_name}: {message}")
            else:
                self.log_area.append(f"\n✅ {message}")
            self._record_batch_result("success", message)
        else:
            QMessageBox.information(self, "成功", message)
            self.log_area.append(f"\n✅ {message}")

        # 任务成功完成，清理临时文件并清除重试状态
        self._pending_retry_state = None
        self._cleanup_temp_audio_file()

        if self.thread:
            self.thread.quit()

    def on_task_error(self, message: str):
        """任务失败时的处理，提供重试选项。"""
        display_name = os.path.basename(self.current_processing_file) if self.current_processing_file else ""
        is_cancelled = "用户取消" in message or "cancelled" in message.lower()

        if self.batch_mode:
            status = "cancelled" if is_cancelled else "error"
            if display_name:
                self.log_area.append(f"\n❌ {display_name}: {message}")
            else:
                self.log_area.append(f"\n❌ 任务失败: {message}")
            if status == "cancelled":
                self.batch_cancelled = True
            self._pending_retry_state = None
            self._record_batch_result(status, message)
            # 批量模式下不保留临时文件
            self._cleanup_temp_audio_file()
        else:
            self.log_area.append(f"\n❌ 任务失败: {message}")

            if is_cancelled:
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
        if self.worker and self.worker.total_chunks > 1:
            # 多片段模式：更新对应片段的进度
            chunk_index = getattr(self.worker, 'current_chunk_index', 0)
            self.segmented_progress_bar.update_segment_progress(chunk_index, bytes_sent, total_bytes)

            # 多片段模式：不显示重复的文字进度，分段进度条已经提供了可视化信息
            # 只在上传完成时更新状态
            if not self.upload_complete_logged and bytes_sent >= total_bytes and total_bytes > 0:
                self.upload_complete_logged = True
                self.progress_label.setText("上传完成，正在处理...")
        else:
            # 单文件模式：使用兼容的进度更新
            self.segmented_progress_bar.update_single_progress(bytes_sent, total_bytes)

            # 单文件模式：显示简洁的状态信息
            if not self.upload_complete_logged and bytes_sent >= total_bytes and total_bytes > 0:
                self.upload_complete_logged = True
                self.progress_label.setText("上传完成，正在处理...")
            elif not self.upload_complete_logged:
                # 只有在上传未完成时才显示"正在上传..."
                self.progress_label.setText("正在上传...")
            # 如果已经完成上传，保持"上传完成，正在处理..."状态

    def update_chunk_progress(self, chunk_index, status, message):
        """更新片段处理进度。"""
        self.segmented_progress_bar.update_chunk_status(chunk_index, status)
        if message:
            self.log_area.append(message)

    def on_chunks_ready(self, chunk_paths):
        """当音频切分完成，设置分段进度条。"""
        self.segmented_progress_bar.set_segments(chunk_paths)
        self.log_area.append(f"分段进度条已设置，共 {len(chunk_paths)} 个片段")

    def _handle_task_completion(self):
        """处理任务完成后的清理工作。"""
        # 只有在没有待重试状态时才清理临时音频文件
        if not self._pending_retry_state and self.temp_audio_file and os.path.exists(self.temp_audio_file):
            try:
                os.remove(self.temp_audio_file)
                self.log_area.append(f"已清理临时文件: {os.path.basename(self.temp_audio_file)}")
                self.temp_audio_file = None
            except OSError as e:
                self.log_area.append(f"清理临时文件失败: {e}")

        # 如果有待重试的状态，不要重置UI，直接执行重试
        if self._pending_retry_state:
            QTimer.singleShot(1000, self._execute_retry)
        else:
            if self.batch_mode:
                self._finalize_current_batch_step()
            else:
                self.reset_ui_after_task()

        # 清理线程对象
        if self.thread and not self.thread.isRunning():
            self.thread.deleteLater()
            self.thread = None
        self.worker = None

    def _execute_retry(self):
        """执行重试逻辑。"""
        if self._pending_retry_state:
            self.log_area.append("\n🔄 正在重试...")
            restore_state = self._pending_retry_state
            self._pending_retry_state = None

            # 重新设置UI状态以显示进度
            self._setup_retry_ui(restore_state)

            # 确定要使用的文件路径
            file_to_process = restore_state.get('file_path')
            original_file = restore_state.get('original_file_path')

            # 如果是单文件模式且有提取的音频文件，优先使用提取的音频文件
            if restore_state.get('was_single_file_mode') and restore_state.get('extracted_audio_file'):
                extracted_audio = restore_state.get('extracted_audio_file')
                if os.path.exists(extracted_audio):
                    file_to_process = extracted_audio
                    self.log_area.append(f"重试时使用已提取的音频文件: {os.path.basename(extracted_audio)}")
                else:
                    self.log_area.append("提取的音频文件不存在，将重新提取...")

            # 重新执行任务
            self._execute_transcription_task(
                file_to_process,
                original_file,
                restore_state
            )

    def _setup_retry_ui(self, restore_state):
        """设置重试时的UI状态"""
        # 禁用UI控件
        self.set_ui_enabled(False)

        # 显示进度条和标签
        self.segmented_progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_label.setText("重试中...")

        # 重置上传完成标志
        self.upload_complete_logged = False

        # 根据恢复的状态设置进度条模式
        if restore_state.get('was_single_file_mode'):
            # 单文件模式
            file_path = restore_state.get('extracted_audio_file') or restore_state.get('file_path')
            if file_path:
                self.segmented_progress_bar.set_single_file_mode(file_path)
                self.log_area.append("重试：设置单文件进度条模式")
        else:
            # 多片段模式
            temp_chunks = restore_state.get('temp_chunks', [])
            if temp_chunks:
                self.segmented_progress_bar.set_segments(temp_chunks)
                self.log_area.append(f"重试：设置多片段进度条模式，共 {len(temp_chunks)} 个片段")

    def _cleanup_temp_audio_file(self):
        """清理临时音频文件。"""
        if self.temp_audio_file and os.path.exists(self.temp_audio_file):
            try:
                os.remove(self.temp_audio_file)
                self.log_area.append(f"已清理临时文件: {os.path.basename(self.temp_audio_file)}")
            except OSError as e:
                self.log_area.append(f"清理临时文件失败: {e}")
            finally:
                self.temp_audio_file = None

    # --- 拖放功能 ---
    def dragEnterEvent(self, event):
        """处理拖拽进入事件。"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """处理文件拖放事件。"""
        urls = event.mimeData().urls()
        if not urls:
            return

        file_paths: List[str] = []
        for url in urls:
            local_path = url.toLocalFile()
            if local_path and os.path.isfile(local_path):
                file_paths.append(local_path)

        if file_paths:
            self.set_files(file_paths)
