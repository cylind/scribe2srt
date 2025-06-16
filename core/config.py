# -*- coding: utf-8 -*-

"""
这个文件包含了应用的所有配置和常量。
"""

# --- 文件和设置 ---
SETTINGS_FILE = "settings.json"
LANGUAGES = {"韩语": "ko", "日语": "ja", "中文": "zh", "英文": "en", "自动检测": "auto"}

# --- 字幕生成规则 ---
MAX_LINES_PER_SUBTITLE = 2

# CPS（每秒字符数）- 根据语言动态调整
CPS_SETTINGS = {
    "cjk": 11,      # 中文、日文、韩文：9-11字符/秒（取上限）
    "latin": 15,    # 拉丁语言（英文等）：12-15字符/秒（取上限）
    "default": 14   # 默认值，向后兼容
}
MAX_CPS = CPS_SETTINGS["default"]  # 保持向后兼容

# 时长控制（遵循Netflix等专业标准）
MIN_SUBTITLE_DURATION = 0.83  # 字幕最短显示时间（秒）- Netflix标准：5/6秒
MAX_SUBTITLE_DURATION = 7.0   # 字幕最长显示时间（秒）
MIN_SUBTITLE_GAP = 0.083      # 字幕间最小间隔（秒）- 约2帧@24fps
PAUSE_THRESHOLD = 0.7         # 判定为长停顿的阈值（秒）

# 每行字符数限制（CPL）
CPL_SETTINGS = {
    "cjk": 25,      # 中文、日文、韩文每行字符数（增加到25）
    "latin": 42,    # 拉丁语言每行字符数
}

# 用户可配置的字幕设置（GUI中显示）
DEFAULT_SUBTITLE_SETTINGS = {
    "min_subtitle_duration": MIN_SUBTITLE_DURATION,
    "max_subtitle_duration": MAX_SUBTITLE_DURATION,
    "min_subtitle_gap": MIN_SUBTITLE_GAP,
    "pause_threshold": PAUSE_THRESHOLD,
    "cjk_cps": CPS_SETTINGS["cjk"],
    "latin_cps": CPS_SETTINGS["latin"],
    "cjk_chars_per_line": CPL_SETTINGS["cjk"],
    "latin_chars_per_line": CPL_SETTINGS["latin"],
}

# 其他设置
DEFAULT_SPLIT_DURATION_MIN = 90  # 长文件自动切分的默认阈值（分钟）

# --- UI 样式表 ---
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