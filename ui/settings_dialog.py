# -*- coding: utf-8 -*-

"""
这个文件定义了字幕生成设置对话框。
"""

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QDialogButtonBox, QDoubleSpinBox, QSpinBox, QVBoxLayout,
    QGroupBox, QHBoxLayout, QLabel
)

from core.config import (
    PAUSE_THRESHOLD, MAX_SUBTITLE_DURATION, DEFAULT_SPLIT_DURATION_MIN,
    DEFAULT_SUBTITLE_SETTINGS
)

class SettingsDialog(QDialog):
    """用于调整字幕生成参数的对话框。"""
    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("字幕生成设置")
        self.setMinimumWidth(450)
        self.setMinimumHeight(500)

        # 创建主布局
        main_layout = QVBoxLayout()

        # === 基础设置组 ===
        basic_group = QGroupBox("基础设置")
        basic_layout = QFormLayout()

        # 长停顿阈值
        self.pause_threshold_spin = QDoubleSpinBox()
        self.pause_threshold_spin.setDecimals(2)
        self.pause_threshold_spin.setSingleStep(0.1)
        self.pause_threshold_spin.setRange(0.1, 5.0)
        self.pause_threshold_spin.setSuffix(" 秒")
        self.pause_threshold_spin.setValue(current_settings.get("pause_threshold", DEFAULT_SUBTITLE_SETTINGS["pause_threshold"]))

        # 长文件切分阈值
        self.split_duration_spin = QSpinBox()
        self.split_duration_spin.setRange(10, 240)
        self.split_duration_spin.setSingleStep(10)
        self.split_duration_spin.setSuffix(" 分钟")
        self.split_duration_spin.setValue(current_settings.get("split_duration_min", DEFAULT_SPLIT_DURATION_MIN))

        basic_layout.addRow("长停顿阈值:", self.pause_threshold_spin)
        basic_layout.addRow("长文件自动切分阈值:", self.split_duration_spin)
        basic_group.setLayout(basic_layout)

        # === 专业字幕设置组 ===
        subtitle_group = QGroupBox("专业字幕设置")
        subtitle_layout = QFormLayout()

        # 最短显示时间
        self.min_duration_spin = QDoubleSpinBox()
        self.min_duration_spin.setDecimals(2)
        self.min_duration_spin.setSingleStep(0.05)
        self.min_duration_spin.setRange(0.5, 3.0)
        self.min_duration_spin.setSuffix(" 秒")
        self.min_duration_spin.setValue(current_settings.get("min_subtitle_duration", DEFAULT_SUBTITLE_SETTINGS["min_subtitle_duration"]))

        # 最长显示时间
        self.max_duration_spin = QDoubleSpinBox()
        self.max_duration_spin.setDecimals(1)
        self.max_duration_spin.setSingleStep(0.5)
        self.max_duration_spin.setRange(2.0, 20.0)
        self.max_duration_spin.setSuffix(" 秒")
        self.max_duration_spin.setValue(current_settings.get("max_subtitle_duration", DEFAULT_SUBTITLE_SETTINGS["max_subtitle_duration"]))

        # 字幕间最小间隔
        self.min_gap_spin = QDoubleSpinBox()
        self.min_gap_spin.setDecimals(3)
        self.min_gap_spin.setSingleStep(0.01)
        self.min_gap_spin.setRange(0.01, 1.0)
        self.min_gap_spin.setSuffix(" 秒")
        self.min_gap_spin.setValue(current_settings.get("min_subtitle_gap", DEFAULT_SUBTITLE_SETTINGS["min_subtitle_gap"]))

        subtitle_layout.addRow("字幕最短显示时间:", self.min_duration_spin)
        subtitle_layout.addRow("字幕最长显示时间:", self.max_duration_spin)
        subtitle_layout.addRow("字幕间最小间隔:", self.min_gap_spin)
        subtitle_group.setLayout(subtitle_layout)

        # === CPS设置组（每秒字符数）===
        cps_group = QGroupBox("阅读速度控制 (CPS - 每秒字符数)")
        cps_layout = QFormLayout()

        # 中文/日文/韩文 CPS
        self.cjk_cps_spin = QSpinBox()
        self.cjk_cps_spin.setRange(8, 20)
        self.cjk_cps_spin.setSingleStep(1)
        self.cjk_cps_spin.setSuffix(" 字符/秒")
        self.cjk_cps_spin.setValue(current_settings.get("cjk_cps", DEFAULT_SUBTITLE_SETTINGS["cjk_cps"]))

        # 英文等拉丁语言 CPS
        self.latin_cps_spin = QSpinBox()
        self.latin_cps_spin.setRange(10, 25)
        self.latin_cps_spin.setSingleStep(1)
        self.latin_cps_spin.setSuffix(" 字符/秒")
        self.latin_cps_spin.setValue(current_settings.get("latin_cps", DEFAULT_SUBTITLE_SETTINGS["latin_cps"]))

        cps_layout.addRow("中文/日文/韩文:", self.cjk_cps_spin)
        cps_layout.addRow("英文等拉丁语言:", self.latin_cps_spin)
        cps_group.setLayout(cps_layout)

        # === 每行字符数设置组 ===
        cpl_group = QGroupBox("每行字符数限制 (CPL)")
        cpl_layout = QFormLayout()

        # 中文/日文/韩文每行字符数
        self.cjk_cpl_spin = QSpinBox()
        self.cjk_cpl_spin.setRange(12, 30)
        self.cjk_cpl_spin.setSingleStep(1)
        self.cjk_cpl_spin.setSuffix(" 字符")
        self.cjk_cpl_spin.setValue(current_settings.get("cjk_chars_per_line", DEFAULT_SUBTITLE_SETTINGS["cjk_chars_per_line"]))

        # 英文等拉丁语言每行字符数
        self.latin_cpl_spin = QSpinBox()
        self.latin_cpl_spin.setRange(30, 60)
        self.latin_cpl_spin.setSingleStep(2)
        self.latin_cpl_spin.setSuffix(" 字符")
        self.latin_cpl_spin.setValue(current_settings.get("latin_chars_per_line", DEFAULT_SUBTITLE_SETTINGS["latin_chars_per_line"]))

        cpl_layout.addRow("中文/日文/韩文:", self.cjk_cpl_spin)
        cpl_layout.addRow("英文等拉丁语言:", self.latin_cpl_spin)
        cpl_group.setLayout(cpl_layout)

        # 添加所有组到主布局
        main_layout.addWidget(basic_group)
        main_layout.addWidget(subtitle_group)
        main_layout.addWidget(cps_group)
        main_layout.addWidget(cpl_group)

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

    def reset_to_defaults(self):
        """将设置重置为程序默认值。"""
        # 基础设置
        self.pause_threshold_spin.setValue(DEFAULT_SUBTITLE_SETTINGS["pause_threshold"])
        self.split_duration_spin.setValue(DEFAULT_SPLIT_DURATION_MIN)

        # 专业字幕设置
        self.min_duration_spin.setValue(DEFAULT_SUBTITLE_SETTINGS["min_subtitle_duration"])
        self.max_duration_spin.setValue(DEFAULT_SUBTITLE_SETTINGS["max_subtitle_duration"])
        self.min_gap_spin.setValue(DEFAULT_SUBTITLE_SETTINGS["min_subtitle_gap"])

        # CPS设置
        self.cjk_cps_spin.setValue(DEFAULT_SUBTITLE_SETTINGS["cjk_cps"])
        self.latin_cps_spin.setValue(DEFAULT_SUBTITLE_SETTINGS["latin_cps"])

        # CPL设置
        self.cjk_cpl_spin.setValue(DEFAULT_SUBTITLE_SETTINGS["cjk_chars_per_line"])
        self.latin_cpl_spin.setValue(DEFAULT_SUBTITLE_SETTINGS["latin_chars_per_line"])

    def get_settings(self) -> dict:
        """获取对话框中的当前设置值。"""
        return {
            # 基础设置
            "pause_threshold": self.pause_threshold_spin.value(),
            "split_duration_min": self.split_duration_spin.value(),

            # 专业字幕设置
            "min_subtitle_duration": self.min_duration_spin.value(),
            "max_subtitle_duration": self.max_duration_spin.value(),
            "min_subtitle_gap": self.min_gap_spin.value(),

            # CPS设置
            "cjk_cps": self.cjk_cps_spin.value(),
            "latin_cps": self.latin_cps_spin.value(),

            # CPL设置
            "cjk_chars_per_line": self.cjk_cpl_spin.value(),
            "latin_chars_per_line": self.latin_cpl_spin.value(),
        }