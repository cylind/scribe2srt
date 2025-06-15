# -*- coding: utf-8 -*-

"""
这个文件定义了字幕生成设置对话框。
"""

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QDialogButtonBox, QDoubleSpinBox, QSpinBox, QVBoxLayout
)

from core.config import (
    PAUSE_THRESHOLD, MAX_SUBTITLE_DURATION, DEFAULT_SPLIT_DURATION_MIN
)

class SettingsDialog(QDialog):
    """用于调整字幕生成参数的对话框。"""
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

        self.split_duration_spin = QSpinBox()
        self.split_duration_spin.setRange(10, 240)
        self.split_duration_spin.setSingleStep(10)
        self.split_duration_spin.setSuffix(" 分钟")
        self.split_duration_spin.setValue(current_settings.get("split_duration_min", DEFAULT_SPLIT_DURATION_MIN))
        
        form_layout = QFormLayout()
        form_layout.addRow("长停顿阈值:", self.pause_threshold_spin)
        form_layout.addRow("单条字幕最长持续时间:", self.max_duration_spin)
        form_layout.addRow("长文件自动切分阈值:", self.split_duration_spin)

        self.button_box = QDialogButtonBox()
        self.save_button = self.button_box.addButton("保存", QDialogButtonBox.ButtonRole.AcceptRole)
        self.reset_button = self.button_box.addButton("重置为默认值", QDialogButtonBox.ButtonRole.ResetRole)
        self.cancel_button = self.button_box.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        
        self.reset_button.clicked.connect(self.reset_to_defaults)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.button_box)
        self.setLayout(main_layout)

    def reset_to_defaults(self):
        """将设置重置为程序默认值。"""
        self.pause_threshold_spin.setValue(PAUSE_THRESHOLD)
        self.max_duration_spin.setValue(MAX_SUBTITLE_DURATION)
        self.split_duration_spin.setValue(DEFAULT_SPLIT_DURATION_MIN)

    def get_settings(self) -> dict:
        """获取对话框中的当前设置值。"""
        return {
            "pause_threshold": self.pause_threshold_spin.value(),
            "max_subtitle_duration": self.max_duration_spin.value(),
            "split_duration_min": self.split_duration_spin.value(),
        }