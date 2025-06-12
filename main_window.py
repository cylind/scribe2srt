import sys
import os
import json
import ctypes
import subprocess
import shutil
from ctypes import wintypes
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QFileDialog, QMessageBox, QComboBox,
    QCheckBox, QSpinBox, QProgressBar, QDialog, QFormLayout, QDialogButtonBox,
    QDoubleSpinBox
)
from PySide6.QtCore import (
    QThread, QObject, Signal, Qt, QThreadPool, QRect, QPoint, QSize
)
from PySide6.QtGui import QPainter, QColor, QPen, QPolygon, QBrush, QFontMetrics

from api_client import ElevenLabsSTTClient, Uploader
from srt_processor import create_srt_from_json, PAUSE_THRESHOLD, MAX_SUBTITLE_DURATION


SETTINGS_FILE = "settings.json"

STYLESHEET = """
QWidget {
    background-color: #2E2E2E;
    color: #F0F0F0;
    font-family: "Microsoft YaHei UI", "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}
QMainWindow {
    background-color: #252525;
}
QLabel {
    padding: 5px;
}
QPushButton {
    background-color: #555555;
    color: #FFFFFF;
    border: 1px solid #666666;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #666666;
}
QPushButton:pressed {
    background-color: #444444;
}
QPushButton:disabled {
    background-color: #404040;
    color: #888888;
    border-color: #555555;
}
QTextEdit {
    background-color: #333333;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 5px;
    font-family: "Consolas", "Courier New", monospace;
}
QComboBox {
    border: 1px solid #888;
    border-radius: 4px;
    padding: 5px;
    min-width: 6em;
    background-color: #3C3C3C;
}
QComboBox:hover {
    background-color: #454545;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left-width: 1px;
    border-left-color: #888;
    border-left-style: solid;
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
}
QComboBox QAbstractItemView {
    border: 1px solid #888;
    selection-background-color: #0078D7;
    background-color: #3C3C3C;
    outline: 0px;
}
QMessageBox {
    background-color: #333333;
}
QProgressBar {
    border: 1px solid #555;
    border-radius: 4px;
    text-align: center;
    background-color: #3C3C3C;
    height: 8px;
}
QProgressBar::chunk {
    background-color: #0078D7;
    border-radius: 3px;
}
#FileDropLabel {
    border: 2px dashed #555555;
    border-radius: 10px;
    background-color: #333333;
    color: #AAAAAA;
    font-size: 12pt;
    font-style: italic;
}
#StartButton {
    background-color: #0078D7;
    font-size: 14pt;
    padding: 12px;
}
#StartButton:hover {
    background-color: #008CFF;
}
#StartButton:disabled {
    background-color: #405A79;
    color: #888888;
}
"""

class CustomCheckBox(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(22)

    def sizeHint(self) -> QSize:
        """Provide a size hint to the layout system."""
        fm = QFontMetrics(self.font())
        # Use horizontalAdvance for accurate string width calculation
        text_width = fm.horizontalAdvance(self.text())
        spacing = 10
        box_size = 20
        # Add some horizontal padding for better spacing
        h_padding = 5
        
        width = box_size + spacing + text_width + h_padding
        height = max(box_size, fm.height())
        
        return QSize(width, height)

    def paintEvent(self, event):
        """Custom paint event to draw the checkbox."""
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)

            is_checked = self.isChecked()
            is_enabled = self.isEnabled()
            is_hovered = self.underMouse()

            border_color_unchecked = QColor("#AAAAAA")
            border_color_unchecked_hover = QColor("#CCCCCC")
            bg_color_checked = QColor("#0078D7")
            bg_color_checked_hover = QColor("#008CFF")
            border_color_disabled = QColor("#555555")
            bg_color_disabled = QColor("#444444")
            text_color = QColor("#F0F0F0")
            text_color_disabled = QColor("#888888")
            checkmark_color = QColor(Qt.white)

            spacing = 10
            box_size = 20
            rect = self.rect()
            box_rect = QRect(0, int((rect.height() - box_size) / 2), box_size, box_size)

            painter.save()

            painter.setPen(Qt.NoPen)
            if not is_enabled:
                painter.setBrush(bg_color_disabled)
                painter.setPen(QPen(border_color_disabled, 1))
            elif is_checked:
                painter.setBrush(bg_color_checked_hover if is_hovered else bg_color_checked)
            else: 
                painter.setBrush(Qt.transparent)
                painter.setPen(QPen(border_color_unchecked_hover if is_hovered else border_color_unchecked, 1))
            
            painter.drawRoundedRect(box_rect, 4, 4)

            if is_checked:
                painter.setPen(QPen(checkmark_color, 2))
                points = QPolygon([
                    QPoint(box_rect.left() + 5, box_rect.top() + 10),
                    QPoint(box_rect.left() + 9, box_rect.top() + 14),
                    QPoint(box_rect.left() + 15, box_rect.top() + 6)
                ])
                painter.drawPolyline(points)

            text_rect = QRect(box_rect.right() + spacing, 0, rect.width() - box_size - spacing, rect.height())
            painter.setPen(text_color_disabled if not is_enabled else text_color)
            painter.drawText(text_rect, Qt.AlignVCenter, self.text())
            
            painter.restore()
        finally:
            # Ensure the painter is always ended, even if errors occur
            painter.end()


class Worker(QObject):
    """
    Coordinates the transcription task, managing the Uploader thread and post-processing.
    """
    finished = Signal(str)
    error = Signal(str)
    log_message = Signal(str)
    progress_updated = Signal(int, int)

    def __init__(self, file_path: str, language_code: str, tag_audio_events: bool,
                 pause_threshold: float, max_subtitle_duration: float,
                 original_file_path: Optional[str] = None):
        super().__init__()
        self.file_path = file_path
        self.original_file_path = original_file_path if original_file_path else file_path
        self.is_temp_file = (file_path != self.original_file_path)
        self.language_code = language_code
        self.tag_audio_events = tag_audio_events
        self.pause_threshold = pause_threshold
        self.max_subtitle_duration = max_subtitle_duration
        self.uploader = None
        self.client = ElevenLabsSTTClient(signals_forwarder=self)

    def run(self):
        self.log_message.emit("="*50)
        self.uploader = self.client.prepare_upload_task(
            self.file_path, self.language_code, self.tag_audio_events
        )
        if not self.uploader:
            self.error.emit("任务准备失败，请检查文件路径。")
            return

        self.uploader.signals.progress.connect(self.progress_updated)
        self.uploader.signals.finished.connect(self.on_upload_finished)
        self.uploader.signals.error.connect(self.error)
        
        QThreadPool.globalInstance().start(self.uploader)

    def on_upload_finished(self, transcript_json):
        base_path, _ = os.path.splitext(self.original_file_path)
        output_json_path = base_path + ".json"
        try:
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(transcript_json, f, ensure_ascii=False, indent=4)
            self.log_message.emit(f"转录成功！转录文本已保存到:\n{output_json_path}")
            self.log_message.emit("正在处理和生成SRT字幕文件...")
        except Exception as e:
            self.error.emit(f"保存 JSON 文件时出错: {e}")
            self._cleanup_temp_file()
            return

        srt_data = create_srt_from_json(
            transcript_json,
            pause_threshold=self.pause_threshold,
            max_subtitle_duration=self.max_subtitle_duration
        )
        if not srt_data:
            self.error.emit("从JSON生成SRT失败。")
            self._cleanup_temp_file()
            return
            
        output_srt_path = base_path + ".srt"
        try:
            with open(output_srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_data)
            self.log_message.emit(f"SRT字幕文件已保存到:\n{output_srt_path}")
            self.finished.emit("任务成功完成！")
        except Exception as e:
            self.error.emit(f"保存SRT文件时出错: {e}")
        finally:
            self._cleanup_temp_file()

    def request_cancellation(self):
        self.log_message.emit("正在取消上传...")
        if self.uploader:
            self.uploader.cancel()
        self._cleanup_temp_file()

    def _cleanup_temp_file(self):
        if self.is_temp_file and os.path.exists(self.file_path):
            try:
                os.remove(self.file_path)
                self.log_message.emit(f"已清理临时文件: {os.path.basename(self.file_path)}")
            except OSError as e:
                self.log_message.emit(f"清理临时文件失败: {e}")

class SettingsDialog(QDialog):
    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("字幕生成设置")
        self.setMinimumWidth(350)
        
        self.pause_threshold_spin = QDoubleSpinBox()
        self.pause_threshold_spin.setDecimals(1)
        self.pause_threshold_spin.setSingleStep(0.1)
        self.pause_threshold_spin.setRange(0.1, 5.0)
        self.pause_threshold_spin.setSuffix(" 秒")
        self.pause_threshold_spin.setValue(current_settings.get("pause_threshold", PAUSE_THRESHOLD))

        self.max_duration_spin = QDoubleSpinBox()
        self.max_duration_spin.setDecimals(1)
        self.max_duration_spin.setSingleStep(0.5)
        self.max_duration_spin.setRange(2.0, 20.0)
        self.max_duration_spin.setSuffix(" 秒")
        self.max_duration_spin.setValue(current_settings.get("max_subtitle_duration", MAX_SUBTITLE_DURATION))
        
        form_layout = QFormLayout()
        form_layout.addRow("长停顿阈值:", self.pause_threshold_spin)
        form_layout.addRow("单条字幕最长持续时间:", self.max_duration_spin)

        self.button_box = QDialogButtonBox()
        self.save_button = self.button_box.addButton("保存", QDialogButtonBox.AcceptRole)
        self.reset_button = self.button_box.addButton("重置为默认值", QDialogButtonBox.ResetRole)
        self.cancel_button = self.button_box.addButton("取消", QDialogButtonBox.RejectRole)
        
        self.reset_button.clicked.connect(self.reset_to_defaults)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.button_box)
        self.setLayout(main_layout)

    def reset_to_defaults(self):
        self.pause_threshold_spin.setValue(PAUSE_THRESHOLD)
        self.max_duration_spin.setValue(MAX_SUBTITLE_DURATION)

    def get_settings(self) -> dict:
        return {
            "pause_threshold": self.pause_threshold_spin.value(),
            "max_subtitle_duration": self.max_duration_spin.value(),
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scribe -> SRT (Powered by ElevenLabs)")
        self.setGeometry(100, 100, 750, 600)
        self.setAcceptDrops(True)
        if sys.platform == "win32":
            try:
                HWND = self.winId()
                if HWND:
                    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                    value = ctypes.c_int(1)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(HWND, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
            except (AttributeError, TypeError, OSError) as e:
                print(f"Could not set dark title bar: {e}")
        self.LANGUAGES = {"韩语": "ko", "日语": "ja", "中文": "zh", "英文": "en", "自动检测": "auto"}
        self.selected_file_path = None
        self.thread = None
        self.worker = None
        self.temp_audio_file = None
        self.upload_complete_logged = False
        self.file_to_process_on_retry = None
        self.is_retrying = False
        
        self.load_settings()

        self.setup_ui()
        self.ffmpeg_available = self.is_ffmpeg_available()
        self.select_button.clicked.connect(self.select_file)
        self.start_button.clicked.connect(self.start_process)
        self.cancel_button.clicked.connect(self.cancel_process)
        self.settings_button.clicked.connect(self.open_settings_dialog)

    def setup_ui(self):
        container = QWidget()
        container.setStyleSheet(STYLESHEET) 

        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        self.file_drop_label = QLabel("将音视频或JSON文件拖拽到此处\n\n或")
        self.file_drop_label.setAlignment(Qt.AlignCenter)
        self.file_drop_label.setObjectName("FileDropLabel")
        
        self.select_button = QPushButton("点击选择文件")
        
        file_layout = QVBoxLayout()
        file_layout.addWidget(self.file_drop_label)
        file_layout.addWidget(self.select_button, 0, Qt.AlignCenter)
        main_layout.addLayout(file_layout)
        
        options_layout = QHBoxLayout()
        options_layout.setSpacing(10)
        
        self.lang_label = QLabel("源语言:")
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(self.LANGUAGES.keys())
        self.lang_combo.setCurrentText("自动检测")
        
        self.audio_events_checkbox = CustomCheckBox("识别声音事件")
        self.audio_events_checkbox.setChecked(False)
        
        options_layout.addWidget(self.lang_label)
        options_layout.addWidget(self.lang_combo)
        options_layout.addSpacing(20)
        options_layout.addWidget(self.audio_events_checkbox)
        options_layout.addStretch(1)

        self.settings_button = QPushButton("字幕设置")
        options_layout.addWidget(self.settings_button)

        main_layout.addLayout(options_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.progress_label.setAlignment(Qt.AlignCenter)
        
        main_layout.addWidget(self.progress_label)
        main_layout.addWidget(self.progress_bar)
        
        action_layout = QHBoxLayout()
        self.start_button = QPushButton("生成字幕")
        self.start_button.setObjectName("StartButton")
        self.start_button.setEnabled(False)
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setVisible(False)
        action_layout.addWidget(self.start_button)
        action_layout.addWidget(self.cancel_button)
        main_layout.addLayout(action_layout)
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("处理日志将在这里显示...")
        main_layout.addWidget(self.log_area)
        
        self.setCentralWidget(container)

    def load_settings(self):
        self.settings = {
            "pause_threshold": PAUSE_THRESHOLD,
            "max_subtitle_duration": MAX_SUBTITLE_DURATION
        }
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    self.settings.update(json.load(f))
            except (json.JSONDecodeError, TypeError):
                print(f"警告: 无法解析 {SETTINGS_FILE}。将使用默认设置。")
        self.pause_threshold = self.settings["pause_threshold"]
        self.max_subtitle_duration = self.settings["max_subtitle_duration"]

    def save_settings(self):
        self.settings["pause_threshold"] = self.pause_threshold
        self.settings["max_subtitle_duration"] = self.max_subtitle_duration
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=4)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            new_settings = dialog.get_settings()
            self.pause_threshold = new_settings["pause_threshold"]
            self.max_subtitle_duration = new_settings["max_subtitle_duration"]
            self.save_settings()
            self.log_area.append("字幕生成设置已更新。")

    def reset_file_label(self):
        self.file_drop_label.setText("将音视频或JSON文件拖拽到此处\n\n或")
        self.file_drop_label.setAlignment(Qt.AlignCenter)

    def set_file(self, file_path: Optional[str]):
        if file_path and os.path.exists(file_path):
            self.selected_file_path = file_path
            self.file_to_process_on_retry = None # Reset retry state when new file is selected
            file_name = os.path.basename(file_path)
            self.file_drop_label.setText(f"已选择:\n{file_name}")
            self.file_drop_label.setAlignment(Qt.AlignCenter)
            self.start_button.setEnabled(True)
            self.log_area.clear()
        else:
            self.selected_file_path = None
            self.reset_file_label()
            self.start_button.setEnabled(False)

    def select_file(self):
        dialog_title = "选择文件"
        dialog_filter = (
            "支持的文件 (*.mp3 *.wav *.flac *.m4a *.aac *.mp4 *.mov *.mkv *.json);;"
            "音视频文件 (*.mp3 *.wav *.flac *.m4a *.aac *.mp4 *.mov *.mkv);;"
            "JSON转录文件 (*.json);;"
            "所有文件 (*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(self, dialog_title, "", dialog_filter)
        self.set_file(file_path)

    def is_ffmpeg_available(self):
        """Check if ffmpeg is in the system's PATH."""
        if shutil.which("ffmpeg"):
            self.log_area.append("✅ FFmpeg 已找到，将启用视频文件处理。")
            return True
        else:
            self.log_area.append("⚠️ 未找到 FFmpeg。处理视频时将尝试直接上传原始文件。")
            self.log_area.append("   为获得最佳体验，推荐安装 FFmpeg 并将其添加到系统 PATH。")
            return False

    def process_json_file_directly(self, json_path: str):
        """Processes a local JSON file directly into an SRT file."""
        self.set_ui_enabled(False)
        self.log_area.clear()
        self.log_area.append("="*50)
        self.log_area.append(f"检测到JSON文件: {os.path.basename(json_path)}")
        self.log_area.append("跳过上传和转录，将直接使用当前设置生成SRT文件...")

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            self.log_area.append("正在处理和生成SRT字幕文件...")

            srt_data = create_srt_from_json(
                json_data,
                pause_threshold=self.pause_threshold,
                max_subtitle_duration=self.max_subtitle_duration
            )

            if not srt_data and not json_data.get("words"):
                self.on_task_error("从JSON生成SRT失败。文件可能为空或不包含'words'数据。")
                return

            base_path, _ = os.path.splitext(json_path)
            output_srt_path = base_path + ".srt"

            with open(output_srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_data)

            self.log_area.append(f"SRT字幕文件已保存到:\n{output_srt_path}")
            QMessageBox.information(self, "成功", "JSON文件处理成功！")
            self.reset_ui_after_task()
            self.set_file(None)
            self.log_area.append(f"\n✅ 任务已完成！")

        except json.JSONDecodeError as e:
            error_msg = f"无法解析JSON文件: {e}"
            self.log_area.append(f"\n❌ {error_msg}")
            QMessageBox.critical(self, "错误", error_msg)
            self.reset_ui_after_task()
        except Exception as e:
            error_msg = f"处理JSON文件时发生未知错误: {e}"
            self.log_area.append(f"\n❌ {error_msg}")
            QMessageBox.critical(self, "错误", error_msg)
            self.reset_ui_after_task()

    def extract_audio(self, video_path):
        """Extracts audio from a video file using ffmpeg."""
        self.log_area.append(f"检测到视频文件，正在使用 FFmpeg 提取音频...")
        self.progress_label.setText("正在提取音频...")
        try:
            output_filename = f"temp_audio_{os.path.basename(video_path)}.mp3"
            output_path = os.path.join(os.path.dirname(video_path), output_filename)
            
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            command = [
                "ffmpeg", "-i", video_path,
                "-vn",
                "-b:a", "192k",
                "-y",
                output_path
            ]
            
            subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', startupinfo=startupinfo)
            
            self.log_area.append(f"音频提取成功: {os.path.basename(output_path)}")
            self.temp_audio_file = output_path
            return output_path
        except FileNotFoundError:
            self.on_task_error("FFmpeg 未找到。请确保它已安装并位于系统的PATH中。")
            return None
        except subprocess.CalledProcessError as e:
            error_message = "FFmpeg 提取音频失败。\n"
            error_message += f"返回码: {e.returncode}\n"
            try:
                stderr_output = e.stderr.strip()
                error_message += f"FFmpeg 输出:\n{stderr_output}"
            except Exception as decode_error:
                error_message += f"(无法解码 FFmpeg 的错误输出: {decode_error})"

            self.on_task_error(error_message)
            return None
        except Exception as e:
            self.on_task_error(f"提取音频时发生未知错误: {e}")
            return None

    def start_process(self):
        if not self.selected_file_path:
            QMessageBox.warning(self, "警告", "请先选择一个文件！")
            return

        _, ext = os.path.splitext(self.selected_file_path)

        if ext.lower() == '.json':
            self.process_json_file_directly(self.selected_file_path)
            return

        self.upload_complete_logged = False
        self.set_ui_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("准备中...")
        self.progress_label.setVisible(True)
        
        file_to_process = self.selected_file_path
        original_file = self.selected_file_path
        
        video_extensions = ['.mp4', '.mkv', '.mov', '.avi', '.flv', '.webm']
        if ext.lower() in video_extensions:
            if self.ffmpeg_available:
                extracted_audio = self.extract_audio(file_to_process)
                if not extracted_audio:
                    self.reset_ui_after_task()
                    return
                file_to_process = extracted_audio
            else:
                QMessageBox.warning(self, "功能限制", "检测到视频文件，但未找到 FFmpeg。\n请安装 FFmpeg 并将其添加到系统 PATH 以处理视频。\n\n将尝试直接上传原始文件，但这可能失败。")
                self.log_area.append("警告: 正在尝试直接上传视频文件...")
        
        self._execute_transcription_task(file_to_process, original_file)

    def _execute_transcription_task(self, file_to_process, original_file):
        # This check is still valid here to prevent starting a new task if one is running.
        if self.thread and self.thread.isRunning():
            QMessageBox.warning(self, "提示", "一个任务已经在运行中。")
            return

        self.upload_complete_logged = False
        self.set_ui_enabled(False)
        self.progress_bar.setValue(0)
        self.log_area.append("开始执行转录任务...")

        self.file_to_process_on_retry = file_to_process

        selected_lang_text = self.lang_combo.currentText()
        selected_lang_code = self.LANGUAGES.get(selected_lang_text, "auto")
        tag_audio_events_enabled = self.audio_events_checkbox.isChecked()
        
        self.thread = QThread()
        self.worker = Worker(
            file_path=file_to_process,
            language_code=selected_lang_code,
            tag_audio_events=tag_audio_events_enabled,
            original_file_path=original_file,
            pause_threshold=self.pause_threshold,
            max_subtitle_duration=self.max_subtitle_duration
        )
        self.worker.moveToThread(self.thread)

        # --- Connections ---
        # Worker signals to main window slots
        self.worker.finished.connect(self.on_task_finished)
        self.worker.error.connect(self.on_task_error)
        self.worker.log_message.connect(self.log_area.append)
        self.worker.progress_updated.connect(self.update_progress)
        
        # Thread signals
        self.thread.started.connect(self.worker.run)
        # The key change: Connect thread's finished signal to a dedicated cleanup slot
        self.thread.finished.connect(self._on_thread_cleanup)
        
        self.thread.start()

    def on_task_finished(self, message: str):
        QMessageBox.information(self, "成功", message)
        self.log_area.append(f"\n✅ {message}")
        self.cleanup_temp_file()
        self.reset_ui_after_task()
        self.set_file(None)
        # Gracefully ask the thread to quit. It will then emit 'finished'.
        if self.thread:
            self.thread.quit()

    def update_progress(self, bytes_sent, total_bytes):
        if total_bytes > 0:
            percentage = int((bytes_sent / total_bytes) * 100)
            self.progress_bar.setValue(percentage)
            sent_mb = bytes_sent / (1024 * 1024)
            total_mb = total_bytes / (1024 * 1024)
            self.progress_label.setText(f"正在上传: {sent_mb:.2f} MB / {total_mb:.2f} MB")
            if percentage == 100 and not self.upload_complete_logged:
                self.log_area.append("上传成功！正在转录中...")
                self.upload_complete_logged = True
        else:
            sent_mb = bytes_sent / (1024 * 1024)
            self.progress_label.setText(f"正在上传: {sent_mb:.2f} MB")

    def on_task_error(self, message: str):
        self.log_area.append(f"\n❌ {message}")
        
        self.is_retrying = False
        if "用户取消" not in message:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("错误")
            msg_box.setText("上传或转录失败。")
            msg_box.setInformativeText(message)
            retry_button = msg_box.addButton("重试", QMessageBox.AcceptRole)
            close_button = msg_box.addButton("关闭", QMessageBox.RejectRole)
            
            msg_box.exec()

            if msg_box.clickedButton() == retry_button:
                self.is_retrying = True

        # Always quit the thread. The cleanup function will decide what to do next.
        if self.thread:
            self.thread.quit()

    def cancel_process(self):
        self.log_area.append("\n正在请求取消任务...")
        # The worker object is the source of truth for a running task.
        if self.worker:
            self.worker.request_cancellation()
        else:
            # If there's no worker, there's no active task to cancel.
            # We can clean up any stray temp files just in case.
            self.cleanup_temp_file()
            self.log_area.append("没有正在运行的任务。")

    def reset_ui_after_task(self):
        """Resets the UI to its initial state, without checking thread status."""
        self.set_ui_enabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.reset_file_label()
        
    def set_ui_enabled(self, enabled: bool):
        self.start_button.setVisible(enabled)
        self.cancel_button.setVisible(not enabled)
        self.start_button.setEnabled(enabled and self.selected_file_path is not None)
        self.select_button.setEnabled(enabled)
        self.lang_combo.setEnabled(enabled)
        self.audio_events_checkbox.setEnabled(enabled)
        self.settings_button.setEnabled(enabled)
        self.setAcceptDrops(enabled)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            self.set_file(file_path)

    def _on_thread_cleanup(self):
        """
        This is the dedicated, safe slot for cleaning up after the thread has finished.
        It now also handles the retry logic.
        """
        self.log_area.append("线程已结束，正在清理资源...")
        
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        
        if self.thread:
            self.thread.deleteLater()
            self.thread = None
            
        if self.is_retrying:
            self.is_retrying = False
            self.log_area.append("\n... 用户选择重试 ...")
            self._execute_transcription_task(self.file_to_process_on_retry, self.selected_file_path)
        else:
            self.cleanup_temp_file()
            self.reset_ui_after_task()

    def closeEvent(self, event):
        self.cancel_process()
        # Wait for our custom thread to finish if it's running
        if self.thread and self.thread.isRunning():
            self.thread.wait(3000) # Wait up to 3 seconds
        # Wait for the global pool (for uploader)
        QThreadPool.globalInstance().waitForDone(-1)
        self.cleanup_temp_file()
        event.accept()

    def cleanup_temp_file(self):
        if self.temp_audio_file and os.path.exists(self.temp_audio_file):
            try:
                os.remove(self.temp_audio_file)
                self.log_area.append(f"已清理临时文件: {os.path.basename(self.temp_audio_file)}")
                self.temp_audio_file = None
            except OSError as e:
                self.log_area.append(f"关闭时清理临时文件失败: {e}")