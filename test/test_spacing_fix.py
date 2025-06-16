#!/usr/bin/env python3
"""
测试脚本：验证spacing字符时间问题的修复
"""

import json
from srt_processor import create_srt_from_json

def test_spacing_issue():
    """测试spacing字符导致的时间问题"""
    
    # 创建测试数据，模拟您提到的问题
    test_data = {
        "language_code": "eng",
        "words": [
            {
                "characters": None,
                "end": 144.899,
                "logprob": 0.0,
                "speaker_id": "speaker_0",
                "start": 143.72,
                "text": "anxiety...",
                "type": "word"
            },
            {
                "characters": None,
                "end": 147.399,
                "logprob": 0.0,
                "speaker_id": "speaker_0",
                "start": 144.899,
                "text": " ",
                "type": "spacing"
            },
            {
                "characters": None,
                "end": 147.519,
                "logprob": 0.0,
                "speaker_id": "speaker_0",
                "start": 147.399,
                "text": "and",
                "type": "word"
            },
            {
                "characters": None,
                "end": 147.599,
                "logprob": 0.0,
                "speaker_id": "speaker_0",
                "start": 147.519,
                "text": " ",
                "type": "spacing"
            },
            {
                "characters": None,
                "end": 148.039,
                "logprob": 0.0,
                "speaker_id": "speaker_0",
                "start": 147.599,
                "text": "edgy",
                "type": "word"
            },
            {
                "characters": None,
                "end": 148.52,
                "logprob": 0.0,
                "speaker_id": "speaker_0",
                "start": 148.039,
                "text": " ",
                "type": "spacing"
            },
            {
                "characters": None,
                "end": 149.079,
                "logprob": 0.0,
                "speaker_id": "speaker_0",
                "start": 148.52,
                "text": "energy.",
                "type": "word"
            }
        ]
    }
    
    print("测试数据:")
    print("- anxiety... (143.72s - 144.899s)")
    print("- spacing (144.899s - 147.399s) <- 这个空白字符占用了2.5秒!")
    print("- and (147.399s - 147.519s)")
    print("- spacing (147.519s - 147.599s)")
    print("- edgy (147.599s - 148.039s)")
    print("- spacing (148.039s - 148.52s)")
    print("- energy. (148.52s - 149.079s)")
    print()
    
    # 生成字幕
    srt_content = create_srt_from_json(test_data)
    
    print("修复后生成的字幕:")
    print(srt_content)
    
    # 分析时间
    lines = srt_content.strip().split('\n')
    for i, line in enumerate(lines):
        if '-->' in line:
            print(f"字幕时间: {line}")
            start_time = line.split(' --> ')[0]
            # 转换为秒数进行分析
            time_parts = start_time.split(':')
            seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + float(time_parts[2].replace(',', '.'))
            print(f"开始时间: {seconds}秒")
            
            # 检查是否使用了正确的时间（应该是147.399秒，而不是144.899秒）
            if abs(seconds - 147.399) < 0.1:
                print("✅ 修复成功！使用了'and'单词的开始时间，而不是spacing的时间")
            elif abs(seconds - 144.899) < 0.1:
                print("❌ 修复失败！仍在使用spacing的开始时间")
            else:
                print(f"⚠️  使用了其他时间: {seconds}秒")
            print()

def test_with_real_file():
    """使用真实文件测试"""
    try:
        with open('sample/白莲花度假村S03E08.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print("使用真实文件测试...")
        srt_content = create_srt_from_json(data)
        
        # 保存结果
        with open('test_output_fixed.srt', 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        print("✅ 已生成修复后的字幕文件: test_output_fixed.srt")
        
        # 显示前几个字幕
        lines = srt_content.split('\n\n')[:3]
        print("\n前3个字幕:")
        for subtitle in lines:
            if subtitle.strip():
                print(subtitle)
                print("---")
                
    except FileNotFoundError:
        print("❌ 找不到测试文件 sample/白莲花度假村S03E08.json")
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    print("=== 测试spacing字符时间问题修复 ===\n")
    
    print("1. 测试简化数据:")
    test_spacing_issue()
    
    print("\n" + "="*50 + "\n")
    
    print("2. 测试真实文件:")
    test_with_real_file()
