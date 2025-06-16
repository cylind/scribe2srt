#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试标点符号分割改进效果的脚本
"""

import json
from srt_processor import create_srt_from_json
from debug_srt_processor import debug_create_srt_from_json

# 创建测试数据 - 模拟您提供的问题场景
test_data = {
    "language_code": "zh",
    "words": [
        {"start": 61.159, "end": 61.199, "text": "，", "type": "word"},
        {"start": 61.199, "end": 61.34, "text": "我", "type": "word"},
        {"start": 61.34, "end": 61.439, "text": "们", "type": "word"},
        {"start": 61.439, "end": 61.539, "text": "可", "type": "word"},
        {"start": 61.539, "end": 61.68, "text": "能", "type": "word"},
        {"start": 61.68, "end": 61.879, "text": "会", "type": "word"},
        {"start": 61.879, "end": 62.059, "text": "采", "type": "word"},
        {"start": 62.059, "end": 62.219, "text": "取", "type": "word"},
        {"start": 62.219, "end": 62.359, "text": "暗", "type": "word"},
        {"start": 62.359, "end": 62.52, "text": "访", "type": "word"},
        {"start": 62.52, "end": 62.68, "text": "的", "type": "word"},
        {"start": 62.68, "end": 62.939, "text": "形", "type": "word"},
        {"start": 62.939, "end": 63.0, "text": "式", "type": "word"},
        {"start": 63.0, "end": 63.5, "text": "，", "type": "word"},
        {"start": 63.5, "end": 63.879, "text": "额", "type": "word"},
        {"start": 63.879, "end": 63.959, "text": "之", "type": "word"},
        {"start": 63.959, "end": 64.099, "text": "前", "type": "word"},
        {"start": 64.099, "end": 64.199, "text": "我", "type": "word"},
        {"start": 64.199, "end": 64.339, "text": "们", "type": "word"},
        {"start": 64.339, "end": 64.479, "text": "生", "type": "word"},
        {"start": 64.479, "end": 64.619, "text": "活", "type": "word"},
        {"start": 64.619, "end": 64.68, "text": "饮", "type": "word"},
        {"start": 64.68, "end": 64.839, "text": "用", "type": "word"},
        {"start": 64.839, "end": 65.019, "text": "水", "type": "word"},
        {"start": 65.019, "end": 65.22, "text": "都", "type": "word"},
        {"start": 65.22, "end": 65.819, "text": "是", "type": "word"},
        {"start": 65.819, "end": 66.0, "text": "明", "type": "word"},
        {"start": 66.0, "end": 66.239, "text": "查", "type": "word"},
        {"start": 66.239, "end": 66.659, "text": "，", "type": "word"},
        {"start": 66.659, "end": 66.76, "text": "因", "type": "word"},
        {"start": 66.76, "end": 67.04, "text": "为", "type": "word"},
        {"start": 67.04, "end": 67.199, "text": "进", "type": "word"},
        {"start": 67.199, "end": 67.379, "text": "单", "type": "word"},
        {"start": 67.379, "end": 67.54, "text": "位", "type": "word"},
        {"start": 67.54, "end": 67.68, "text": "可", "type": "word"},
        {"start": 67.68, "end": 68.04, "text": "能", "type": "word"},
        {"start": 68.04, "end": 68.239, "text": "困", "type": "word"},
        {"start": 68.239, "end": 68.339, "text": "难", "type": "word"},
        {"start": 68.339, "end": 68.459, "text": "一", "type": "word"},
        {"start": 68.459, "end": 68.599, "text": "些", "type": "word"},
        {"start": 68.599, "end": 68.639, "text": "，", "type": "word"},
    ]
}

def test_punctuation_splitting():
    """测试标点符号分割效果"""
    print("=== 测试标点符号分割改进效果 ===\n")

    # 先分析一下文本长度
    full_text = "".join([w['text'] for w in test_data['words']])
    print(f"完整文本: {full_text}")
    print(f"文本长度: {len(full_text)} 字符")
    print(f"预期的每行最大字符数: 25 (CJK)")
    print(f"预期的两行最大字符数: 50")
    print()

    # 手动分析标点符号位置
    punctuation_positions = []
    current_pos = 0
    for word in test_data['words']:
        if word['text'] in ['，', '。', '！', '？', '；', '：', '、']:
            punctuation_positions.append((current_pos + len(word['text']), word['text']))
        current_pos += len(word['text'])

    print("标点符号位置:")
    for pos, punct in punctuation_positions:
        print(f"  位置 {pos}: '{punct}' - 前面文本: '{full_text[:pos]}'")
    print()

    # 生成字幕 - 使用调试版本
    print("=== 调试信息 ===")
    srt_content = debug_create_srt_from_json(test_data)
    print("=== 调试信息结束 ===\n")

    print("生成的字幕内容：")
    print(srt_content)
    
    # 分析分割效果
    lines = srt_content.strip().split('\n')
    subtitle_texts = []
    
    for i, line in enumerate(lines):
        if line.strip() and not line.strip().isdigit() and '-->' not in line:
            subtitle_texts.append(line.strip())
    
    print("\n=== 分割效果分析 ===")
    for i, text in enumerate(subtitle_texts, 1):
        print(f"字幕 {i}: {text}")
        
        # 检查是否在标点符号处分割
        if text.endswith(('，', '。', '！', '？', '；', '：', '、')):
            print(f"  ✓ 在标点符号处结束")
        else:
            print(f"  ✗ 未在标点符号处结束")
    
    # 检查是否有在词语中间分割的情况
    full_text = "".join([w['text'] for w in test_data['words']])
    reconstructed_text = "".join(subtitle_texts).replace('\n', '')
    
    print(f"\n原始文本: {full_text}")
    print(f"重构文本: {reconstructed_text}")
    print(f"文本完整性: {'✓ 完整' if full_text == reconstructed_text else '✗ 有缺失'}")

if __name__ == "__main__":
    test_punctuation_splitting()
