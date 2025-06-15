# -*- coding: utf-8 -*-

"""
这个文件包含了应用中使用的自定义Qt控件。
"""

from PySide6.QtWidgets import QCheckBox
from PySide6.QtCore import QSize, Qt, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QPolygon, QBrush, QFontMetrics

class CustomCheckBox(QCheckBox):
    """一个自定义绘制的复选框，以获得更好的视觉效果。"""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(22)

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        text_width = fm.horizontalAdvance(self.text())
        spacing = 10
        box_size = 20
        h_padding = 5
        
        width = box_size + spacing + text_width + h_padding
        height = max(box_size, fm.height())
        
        return QSize(width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

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
            checkmark_color = QColor(Qt.GlobalColor.white)

            spacing = 10
            box_size = 20
            rect = self.rect()
            box_rect = QRect(0, int((rect.height() - box_size) / 2), box_size, box_size)

            painter.save()

            painter.setPen(Qt.PenStyle.NoPen)
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
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, self.text())
            
            painter.restore()
        finally:
            painter.end()