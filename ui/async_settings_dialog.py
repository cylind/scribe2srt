# -*- coding: utf-8 -*-

"""
这个文件定义了并发处理设置对话框。
"""

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QDialogButtonBox, QSpinBox, QVBoxLayout,
    QGroupBox, QLabel, QCheckBox, QHBoxLayout
)
from PySide6.QtCore import Qt

from core.config import DEFAULT_SPLIT_DURATION_MIN


class AsyncSettingsDialog(QDialog):
    """用于调整并发处理参数的对话框。"""

    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("并发处理设置")
        self.setMinimumWidth(400)
        self.setMinimumHeight(350)

        # 创建主布局
        main_layout = QVBoxLayout()

        # === 并发处理设置组 ===
        async_group = QGroupBox("并发处理设置")
        async_layout = QFormLayout()

        # 启用异步处理
        self.enable_async_checkbox = QCheckBox("启用异步并发处理")
        self.enable_async_checkbox.setChecked(current_settings.get("enable_async_processing", True))
        self.enable_async_checkbox.stateChanged.connect(self._on_async_enabled_changed)

        # 最大并发片段数
        self.max_concurrent_spin = QSpinBox()
        self.max_concurrent_spin.setRange(1, 10)
        self.max_concurrent_spin.setSingleStep(1)
        self.max_concurrent_spin.setSuffix(" 个")
        self.max_concurrent_spin.setValue(current_settings.get("max_concurrent_chunks", 3))

        # 重试次数
        self.max_retries_spin = QSpinBox()
        self.max_retries_spin.setRange(1, 10)
        self.max_retries_spin.setSingleStep(1)
        self.max_retries_spin.setSuffix(" 次")
        self.max_retries_spin.setValue(current_settings.get("max_retries", 3))

        # API速率限制
        self.rate_limit_spin = QSpinBox()
        self.rate_limit_spin.setRange(10, 100)
        self.rate_limit_spin.setSingleStep(5)
        self.rate_limit_spin.setSuffix(" 请求/分钟")
        self.rate_limit_spin.setValue(current_settings.get("api_rate_limit_per_minute", 30))

        async_layout.addRow(self.enable_async_checkbox)
        async_layout.addRow("最大并发片段数:", self.max_concurrent_spin)
        async_layout.addRow("失败重试次数:", self.max_retries_spin)
        async_layout.addRow("API速率限制:", self.rate_limit_spin)
        async_group.setLayout(async_layout)

        # === 音频切分设置组 ===
        split_group = QGroupBox("音频切分设置")
        split_layout = QFormLayout()

        # 长文件切分阈值（从字幕设置移过来）
        self.split_duration_spin = QSpinBox()
        self.split_duration_spin.setRange(10, 240)
        self.split_duration_spin.setSingleStep(10)
        self.split_duration_spin.setSuffix(" 分钟")
        self.split_duration_spin.setValue(current_settings.get("split_duration_min", DEFAULT_SPLIT_DURATION_MIN))

        split_layout.addRow("长文件自动切分阈值:", self.split_duration_spin)
        split_group.setLayout(split_layout)

        # === 说明文本 ===
        info_label = QLabel(
            "说明：\n"
            "• 异步并发处理可显著提升长音频文件的处理速度\n"
            "• 并发数越高处理越快，但会增加API请求压力\n"
            "• 建议根据网络状况和API限制调整参数\n"
            "• 如遇到问题可关闭异步处理使用顺序模式"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("QLabel { color: #666666; font-size: 9pt; }")

        # 添加所有组到主布局
        main_layout.addWidget(async_group)
        main_layout.addWidget(split_group)
        main_layout.addWidget(info_label)

        # 按钮区域
        self.button_box = QDialogButtonBox()
        self.save_button = self.button_box.addButton("保存", QDialogButtonBox.ButtonRole.AcceptRole)
        self.reset_button = self.button_box.addButton("重置为默认值", QDialogButtonBox.ButtonRole.ResetRole)
        self.cancel_button = self.button_box.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)

        self.reset_button.clicked.connect(self.reset_to_defaults)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        main_layout.addWidget(self.button_box)
        self.setLayout(main_layout)

        # 初始状态设置
        self._on_async_enabled_changed()

    def _on_async_enabled_changed(self):
        """异步处理启用状态改变时的处理"""
        enabled = self.enable_async_checkbox.isChecked()
        self.max_concurrent_spin.setEnabled(enabled)
        self.max_retries_spin.setEnabled(enabled)
        self.rate_limit_spin.setEnabled(enabled)

    def reset_to_defaults(self):
        """将设置重置为程序默认值。"""
        self.enable_async_checkbox.setChecked(True)
        self.max_concurrent_spin.setValue(3)
        self.max_retries_spin.setValue(3)
        self.rate_limit_spin.setValue(30)
        self.split_duration_spin.setValue(DEFAULT_SPLIT_DURATION_MIN)

    def get_settings(self) -> dict:
        """获取对话框中的当前设置值。"""
        return {
            "enable_async_processing": self.enable_async_checkbox.isChecked(),
            "max_concurrent_chunks": self.max_concurrent_spin.value(),
            "max_retries": self.max_retries_spin.value(),
            "api_rate_limit_per_minute": self.rate_limit_spin.value(),
            "split_duration_min": self.split_duration_spin.value(),
        }