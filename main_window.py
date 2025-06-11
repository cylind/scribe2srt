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
    QCheckBox, QSpinBox, QProgressBar
)
from PySide6.QtCore import QThread, QObject, Signal, Qt, QThreadPool

from api_client import ElevenLabsSTTClient, Uploader
from srt_processor import create_srt_from_json

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
QCheckBox {
    spacing: 10px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #888;
    background-color: #3C3C3C;
}
QCheckBox::indicator:hover {
    border: 1px solid #aaa;
}
QCheckBox::indicator:checked {
    background-color: #0078D7;
    border-color: #0078D7;
}
QCheckBox::indicator:disabled {
    border-color: #555;
    background-color: #444;
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

class Worker(QObject):
    """
    Coordinates the transcription task, managing the Uploader thread and post-processing.
    """
    finished = Signal(str)
    error = Signal(str)
    log_message = Signal(str)
    progress_updated = Signal(int, int)

    def __init__(self, file_path: str, language_code: str, tag_audio_events: bool, original_file_path: Optional[str] = None):
        super().__init__()
        self.file_path = file_path # This might be a temporary audio file
        self.original_file_path = original_file_path if original_file_path else file_path
        self.is_temp_file = (file_path != self.original_file_path)
        self.language_code = language_code
        self.tag_audio_events = tag_audio_events
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

        # Connect signals from the uploader thread
        self.uploader.signals.progress.connect(self.progress_updated)
        self.uploader.signals.finished.connect(self.on_upload_finished)
        self.uploader.signals.error.connect(self.error)
        
        QThreadPool.globalInstance().start(self.uploader)

    def on_upload_finished(self, transcript_json):
        self.log_message.emit("上传成功！正在处理和生成SRT文件...")
        
        # Use the original file path for output files
        base_path, _ = os.path.splitext(self.original_file_path)
        output_json_path = base_path + ".json"
        try:
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(transcript_json, f, ensure_ascii=False, indent=4)
            self.log_message.emit(f"JSON 文件已保存到:\n{output_json_path}")
        except Exception as e:
            self.error.emit(f"保存 JSON 文件时出错: {e}")
            self._cleanup_temp_file()
            return

        srt_data = create_srt_from_json(transcript_json)
        if not srt_data:
            self.error.emit("从JSON生成SRT失败。")
            self._cleanup_temp_file()
            return
            
        output_srt_path = base_path + ".srt"
        try:
            with open(output_srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_data)
            self.finished.emit(f"任务成功完成！\nSRT和JSON文件已保存到源文件目录。")
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
        self.LANGUAGES = {"日语": "ja", "中文": "zh", "英文": "en", "自动检测": "auto"}
        self.selected_file_path = None
        self.thread = None
        self.worker = None
        self.temp_audio_file = None
        self.setup_ui()
        self.ffmpeg_available = self.is_ffmpeg_available()
        self.select_button.clicked.connect(self.select_file)
        self.start_button.clicked.connect(self.start_process)
        self.cancel_button.clicked.connect(self.cancel_process)

    def setup_ui(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        self.file_drop_label = QLabel("将音视频文件拖拽到此处\n\n或")
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
        self.lang_combo.setCurrentText("日语")
        self.audio_events_checkbox = QCheckBox("识别声音事件")
        self.audio_events_checkbox.setChecked(True)
        options_layout.addWidget(self.lang_label)
        options_layout.addWidget(self.lang_combo)
        options_layout.addStretch()
        options_layout.addWidget(self.audio_events_checkbox)
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

    def reset_file_label(self):
        self.file_drop_label.setText("将音视频文件拖拽到此处\n\n或")
        self.file_drop_label.setAlignment(Qt.AlignCenter)

    def set_file(self, file_path: Optional[str]):
        if file_path and os.path.exists(file_path):
            self.selected_file_path = file_path
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
        file_path, _ = QFileDialog.getOpenFileName(self, "选择一个音视频文件", "", "音视频文件 (*.mp3 *.wav *.flac *.m4a *.mp4 *.mov *.mkv);;所有文件 (*)")
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

    def extract_audio(self, video_path):
        """Extracts audio from a video file using ffmpeg."""
        self.log_area.append(f"检测到视频文件，正在使用 FFmpeg 提取音频...")
        self.progress_label.setText("正在提取音频...")
        try:
            output_filename = f"temp_audio_{os.path.basename(video_path)}.mp3"
            output_path = os.path.join(os.path.dirname(video_path), output_filename)
            
            # Use CREATE_NO_WINDOW flag on Windows to hide the console
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            command = [
                "ffmpeg", "-i", video_path,
                "-vn",         # No video
                "-b:a", "192k", # Audio bitrate 192kbps
                "-y",          # Overwrite output file if it exists
                output_path
            ]
            
            process = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', startupinfo=startupinfo)
            
            self.log_area.append(f"音频提取成功: {os.path.basename(output_path)}")
            self.temp_audio_file = output_path # Store for later cleanup
            return output_path
        except FileNotFoundError:
            self.on_task_error("FFmpeg 未找到。请确保它已安装并位于系统的PATH中。")
            return None
        except subprocess.CalledProcessError as e:
            error_message = "FFmpeg 提取音频失败。\n"
            error_message += f"返回码: {e.returncode}\n"
            # Try to decode stderr, but fall back if there are encoding issues
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

        self.set_ui_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("准备中...")
        self.progress_label.setVisible(True)
        
        file_to_process = self.selected_file_path
        original_file = self.selected_file_path
        
        # Check if it's a video file and if ffmpeg is available
        _, ext = os.path.splitext(file_to_process)
        video_extensions = ['.mp4', '.mkv', '.mov', '.avi', '.flv', '.webm']
        if ext.lower() in video_extensions:
            if self.ffmpeg_available:
                extracted_audio = self.extract_audio(file_to_process)
                if not extracted_audio:
                    self.reset_ui_after_task() # Reset UI if extraction fails
                    return
                file_to_process = extracted_audio
            else:
                QMessageBox.warning(self, "功能限制", "检测到视频文件，但未找到 FFmpeg。\n请安装 FFmpeg 并将其添加到系统 PATH 以处理视频。\n\n将尝试直接上传原始文件，但这可能失败。")
                self.log_area.append("警告: 正在尝试直接上传视频文件...")

        selected_lang_text = self.lang_combo.currentText()
        selected_lang_code = self.LANGUAGES.get(selected_lang_text, "auto")
        tag_audio_events_enabled = self.audio_events_checkbox.isChecked()
        
        self.thread = QThread()
        self.worker = Worker(file_to_process, selected_lang_code, tag_audio_events_enabled, original_file_path=original_file)
        self.worker.moveToThread(self.thread)

        self.worker.finished.connect(self.on_task_finished)
        self.worker.error.connect(self.on_task_error)
        self.worker.log_message.connect(self.log_area.append)
        self.worker.progress_updated.connect(self.update_progress)
        
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def on_task_finished(self, message: str):
        self.log_area.append(f"\n✅ {message}")
        QMessageBox.information(self, "成功", message)
        self.cleanup_temp_file()
        self.reset_ui_after_task()
        self.set_file(None)

    def update_progress(self, bytes_sent, total_bytes):
        if total_bytes > 0:
            percentage = int((bytes_sent / total_bytes) * 100)
            self.progress_bar.setValue(percentage)
            sent_mb = bytes_sent / (1024 * 1024)
            total_mb = total_bytes / (1024 * 1024)
            self.progress_label.setText(f"正在上传: {sent_mb:.2f} MB / {total_mb:.2f} MB")
        else:
            sent_mb = bytes_sent / (1024 * 1024)
            self.progress_label.setText(f"正在上传: {sent_mb:.2f} MB")

    def on_task_error(self, message: str):
        self.log_area.append(f"\n❌ {message}")
        if "用户取消" not in message:
            QMessageBox.critical(self, "错误", message)
        self.cleanup_temp_file()
        self.reset_ui_after_task()
        self.reset_file_label()
    
    def cancel_process(self):
        self.log_area.append("\n正在请求取消任务...")
        if self.worker:
            self.worker.request_cancellation()
        self.cleanup_temp_file()

    def reset_ui_after_task(self):
        self.set_ui_enabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
        
    def set_ui_enabled(self, enabled: bool):
        self.start_button.setVisible(enabled)
        self.cancel_button.setVisible(not enabled)
        self.start_button.setEnabled(enabled and self.selected_file_path is not None)
        self.select_button.setEnabled(enabled)
        self.lang_combo.setEnabled(enabled)
        self.audio_events_checkbox.setEnabled(enabled)
        self.setAcceptDrops(enabled)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            self.set_file(file_path)

    def closeEvent(self, event):
        self.cancel_process()
        QThreadPool.globalInstance().waitForDone(-1) # Wait for all threads to finish
        self.cleanup_temp_file() # Final cleanup on close
        event.accept()

    def cleanup_temp_file(self):
        if self.temp_audio_file and os.path.exists(self.temp_audio_file):
            try:
                os.remove(self.temp_audio_file)
                self.log_area.append(f"已清理临时文件: {os.path.basename(self.temp_audio_file)}")
                self.temp_audio_file = None
            except OSError as e:
                self.log_area.append(f"关闭时清理临时文件失败: {e}")