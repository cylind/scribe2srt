# -*- coding: utf-8 -*-

"""
分段式进度条组件
支持按文件大小比例显示多个片段的上传进度
"""

import os
from typing import List, Dict
from PySide6.QtWidgets import QWidget, QHBoxLayout, QProgressBar, QLabel, QVBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QFont


class SegmentedProgressBar(QWidget):
    """分段式进度条组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.segments: List[Dict] = []  # 存储每个片段的信息
        self.total_size = 0
        self.setup_ui()

    def setup_ui(self):
        """初始化UI"""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)

        # 进度条容器
        self.progress_container = QWidget()
        self.progress_layout = QHBoxLayout(self.progress_container)
        self.progress_layout.setContentsMargins(0, 0, 0, 0)
        self.progress_layout.setSpacing(1)

        # 标签显示总体进度
        self.total_label = QLabel("准备中...")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout.addWidget(self.total_label)
        self.layout.addWidget(self.progress_container)

    def set_segments(self, chunk_paths: List[str]):
        """设置音频片段信息"""
        self.segments.clear()
        self.total_size = 0

        # 清理旧的进度条
        for i in reversed(range(self.progress_layout.count())):
            child = self.progress_layout.itemAt(i).widget()
            if child:
                child.deleteLater()

        # 计算每个片段的大小
        for i, chunk_path in enumerate(chunk_paths):
            try:
                size = os.path.getsize(chunk_path) if os.path.exists(chunk_path) else 0
            except OSError:
                size = 0

            self.segments.append({
                'index': i,
                'path': chunk_path,
                'size': size,
                'progress': 0,
                'progress_bar': None
            })
            self.total_size += size

        # 创建分段进度条
        if self.total_size > 0:
            for segment in self.segments:
                # 计算该片段在总进度条中的宽度比例
                width_ratio = segment['size'] / self.total_size if self.total_size > 0 else 1.0 / len(self.segments)

                # 创建进度条
                progress_bar = QProgressBar()
                progress_bar.setRange(0, 100)
                progress_bar.setValue(0)
                progress_bar.setTextVisible(False)
                progress_bar.setMinimumHeight(20)

                # 设置不同颜色区分片段
                color_hue = (segment['index'] * 60) % 360  # 每个片段不同色调
                progress_bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: 1px solid #555;
                        border-radius: 3px;
                        background-color: #2b2b2b;
                    }}
                    QProgressBar::chunk {{
                        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 hsl({color_hue}, 70%, 50%),
                            stop:1 hsl({color_hue}, 70%, 60%));
                        border-radius: 2px;
                    }}
                """)

                # 设置工具提示
                segment_name = os.path.basename(segment['path'])
                size_mb = segment['size'] / (1024 * 1024)
                progress_bar.setToolTip(f"片段 {segment['index'] + 1}: {segment_name}\n大小: {size_mb:.2f} MB")

                # 按比例设置宽度
                self.progress_layout.addWidget(progress_bar, int(width_ratio * 100))
                segment['progress_bar'] = progress_bar

        self.update_total_label()

    def update_segment_progress(self, segment_index: int, bytes_sent: int, total_bytes: int):
        """更新指定片段的进度"""
        if 0 <= segment_index < len(self.segments):
            segment = self.segments[segment_index]

            if total_bytes > 0:
                progress = int((bytes_sent / total_bytes) * 100)
                segment['progress'] = progress

                if segment['progress_bar']:
                    segment['progress_bar'].setValue(progress)

            self.update_total_label()

    def update_total_label(self):
        """更新总体进度标签"""
        if not self.segments:
            self.total_label.setText("准备中...")
            return

        # 计算总体进度（按文件大小加权平均）
        total_weighted_progress = 0
        completed_segments = 0

        for segment in self.segments:
            if segment['size'] > 0:
                weight = segment['size'] / self.total_size
                total_weighted_progress += segment['progress'] * weight

            if segment['progress'] >= 100:
                completed_segments += 1

        total_progress = int(total_weighted_progress)

        # 显示进度信息
        total_mb = self.total_size / (1024 * 1024)
        if completed_segments == len(self.segments) and completed_segments > 0:
            self.total_label.setText(f"上传完成！总大小: {total_mb:.2f} MB")
        else:
            self.total_label.setText(
                f"上传进度: {total_progress}% | "
                f"已完成: {completed_segments}/{len(self.segments)} 片段 | "
                f"总大小: {total_mb:.2f} MB"
            )

    def reset(self):
        """重置进度条"""
        for segment in self.segments:
            segment['progress'] = 0
            if segment['progress_bar']:
                segment['progress_bar'].setValue(0)
        self.update_total_label()

    def set_single_file_mode(self, file_path: str = None):
        """设置为单文件模式（兼容原有进度条）"""
        self.segments.clear()

        # 清理旧的进度条
        for i in reversed(range(self.progress_layout.count())):
            child = self.progress_layout.itemAt(i).widget()
            if child:
                child.deleteLater()

        # 创建单个进度条
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(False)
        progress_bar.setMinimumHeight(20)

        # 使用默认样式
        progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 3px;
                background-color: #2b2b2b;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a9eff, stop:1 #6bb6ff);
                border-radius: 2px;
            }
        """)

        if file_path:
            file_name = os.path.basename(file_path)
            progress_bar.setToolTip(f"文件: {file_name}")

        self.progress_layout.addWidget(progress_bar)

        # 添加单文件片段信息
        self.segments.append({
            'index': 0,
            'path': file_path or '',
            'size': 0,
            'progress': 0,
            'progress_bar': progress_bar
        })

        self.total_label.setText("准备上传...")

    def update_single_progress(self, bytes_sent: int, total_bytes: int):
        """更新单文件进度（兼容模式）"""
        if self.segments and self.segments[0]['progress_bar']:
            if total_bytes > 0:
                progress = int((bytes_sent / total_bytes) * 100)
                self.segments[0]['progress_bar'].setValue(progress)

                sent_mb = bytes_sent / (1024 * 1024)
                total_mb = total_bytes / (1024 * 1024)
                self.total_label.setText(f"正在上传: {sent_mb:.2f} MB / {total_mb:.2f} MB ({progress}%)")
            else:
                sent_mb = bytes_sent / (1024 * 1024)
                self.total_label.setText(f"正在上传: {sent_mb:.2f} MB")