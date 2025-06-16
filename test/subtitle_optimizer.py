#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
字幕优化器 - 基于分析结果的具体改进实现
"""

import sys
import os
import re
from typing import List, Dict, Tuple

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import (
    MIN_SUBTITLE_DURATION, MAX_SUBTITLE_DURATION, MIN_SUBTITLE_GAP,
    CPS_SETTINGS, CPL_SETTINGS
)

class SubtitleOptimizer:
    """字幕优化器"""
    
    def __init__(self):
        self.tolerance = 1e-3  # 1毫秒容差
        
    def get_dynamic_cps_limit(self, text: str, language: str) -> float:
        """根据文本长度动态调整CPS限制"""
        base_cps = CPS_SETTINGS.get(language, CPS_SETTINGS["latin"])
        text_length = len(re.sub(r'\s', '', text))  # 去除空白字符的长度
        
        # 对于极短文本，允许更高的CPS
        if text_length <= 3:
            return base_cps * 3.0  # 极短文本（如"啊"）允许3倍CPS
        elif text_length <= 5:
            return base_cps * 2.0  # 短文本允许2倍CPS
        elif text_length <= 10:
            return base_cps * 1.5  # 中短文本允许1.5倍CPS
        else:
            return base_cps
    
    def get_enhanced_punctuation_chars(self) -> set:
        """扩展标点符号集合"""
        return {
            # 英文标点
            '.', '!', '?', ',', ';', ':', '"', "'", ')', ']', '}',
            # 中文标点
            '。', '！', '？', '，', '；', '：', '"', '"', ''', ''', '）', '】', '』', '》',
            # 日文标点
            '。', '！', '？', '、', '」', '』', '》', '）',
            # 新增：日文语气词结尾
            'ね', 'よ', 'な', 'か', 'わ', 'ぞ', 'ぜ', 'さ', 'だ', 'の',
            # 新增：中文语气词
            '呢', '吧', '啊', '哦', '嗯', '哼', '呀', '哟', '咯', '嘛',
            # 新增：常见结尾词
            '了', '的', '着', '过', '得', '地', '们'
        }
    
    def detect_language(self, text: str) -> str:
        """检测文本语言"""
        # 检测中日韩字符
        cjk_chars = len(re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', text))
        total_chars = len(re.sub(r'\s', '', text))
        
        if total_chars == 0:
            return 'unknown'
        
        cjk_ratio = cjk_chars / total_chars
        return 'cjk' if cjk_ratio > 0.3 else 'latin'
    
    def should_merge_short_subtitles(self, current: Dict, next_subtitle: Dict) -> bool:
        """判断是否应该合并短字幕"""
        current_duration = current.get('duration', 0)
        gap = next_subtitle.get('start', 0) - current.get('end', 0)
        
        # 如果当前字幕过短且间隔很小，考虑合并
        if (current_duration < MIN_SUBTITLE_DURATION - self.tolerance and 
            gap < 0.5):  # 500ms内的间隔
            
            # 检查合并后的文本长度是否合理
            combined_text = current.get('text', '') + ' ' + next_subtitle.get('text', '')
            if len(combined_text) <= 100:  # 合并后不超过100字符
                return True
        
        return False
    
    def optimize_cps_violations(self, subtitle: Dict) -> Dict:
        """优化CPS违规的字幕"""
        text = subtitle.get('text', '')
        duration = subtitle.get('duration', 0)
        language = self.detect_language(text)
        
        if duration <= 0:
            return subtitle
        
        current_cps = len(re.sub(r'\s', '', text)) / duration
        max_cps = self.get_dynamic_cps_limit(text, language)
        
        if current_cps > max_cps:
            # 计算需要的最小时长
            required_duration = len(re.sub(r'\s', '', text)) / max_cps
            
            # 如果需要延长时间
            if required_duration > duration:
                subtitle['optimized_duration'] = required_duration
                subtitle['optimization_reason'] = f'CPS优化: {current_cps:.1f} -> {max_cps}'
        
        return subtitle
    
    def check_punctuation_ending(self, text: str) -> Tuple[bool, str]:
        """检查标点符号结尾，返回是否符合和建议"""
        if not text:
            return False, "空文本"
        
        punctuation_chars = self.get_enhanced_punctuation_chars()
        last_char = text.strip()[-1]
        
        if last_char in punctuation_chars:
            return True, "符合标点规则"
        
        # 分析可能的问题类型
        if last_char.isalpha():
            if text.strip().endswith(('and', 'the', 'of', 'to', 'in', 'with', 'for')):
                return False, "英文单词被截断"
            else:
                return False, "缺少标点符号"
        elif last_char in 'あいうえおんてでばがやわすクパイふれまそいー':
            return False, "日文语气词（可接受）"
        elif len(text.strip()) <= 3:
            return False, "单字符/短文本"
        else:
            return False, "其他标点问题"
    
    def generate_optimization_report(self, subtitles: List[Dict]) -> Dict:
        """生成优化报告"""
        report = {
            'total_subtitles': len(subtitles),
            'optimizations': {
                'cps_optimized': 0,
                'duration_extended': 0,
                'merge_suggested': 0,
                'punctuation_issues': 0
            },
            'suggestions': []
        }
        
        for i, subtitle in enumerate(subtitles):
            # CPS优化
            optimized = self.optimize_cps_violations(subtitle)
            if 'optimized_duration' in optimized:
                report['optimizations']['cps_optimized'] += 1
                report['suggestions'].append({
                    'type': 'cps_optimization',
                    'subtitle_index': i,
                    'original_duration': subtitle.get('duration'),
                    'suggested_duration': optimized['optimized_duration'],
                    'reason': optimized['optimization_reason']
                })
            
            # 标点符号检查
            is_valid, reason = self.check_punctuation_ending(subtitle.get('text', ''))
            if not is_valid and "可接受" not in reason:
                report['optimizations']['punctuation_issues'] += 1
                report['suggestions'].append({
                    'type': 'punctuation_issue',
                    'subtitle_index': i,
                    'text': subtitle.get('text', ''),
                    'issue': reason
                })
            
            # 合并建议
            if i < len(subtitles) - 1:
                if self.should_merge_short_subtitles(subtitle, subtitles[i + 1]):
                    report['optimizations']['merge_suggested'] += 1
                    report['suggestions'].append({
                        'type': 'merge_suggestion',
                        'subtitle_indices': [i, i + 1],
                        'reason': '短字幕合并建议'
                    })
        
        return report

def main():
    """测试优化器"""
    print("字幕优化器测试")
    print("=" * 50)
    
    # 测试用例
    test_subtitles = [
        {'text': 'Hello', 'duration': 0.1, 'start': 0, 'end': 0.1},
        {'text': 'World!', 'duration': 0.2, 'start': 0.15, 'end': 0.35},
        {'text': 'This is a very long sentence with many words', 'duration': 1.0, 'start': 1, 'end': 2},
        {'text': 'あ', 'duration': 0.5, 'start': 3, 'end': 3.5},
        {'text': '你好呢', 'duration': 1.0, 'start': 4, 'end': 5}
    ]
    
    optimizer = SubtitleOptimizer()
    report = optimizer.generate_optimization_report(test_subtitles)
    
    print(f"总字幕数: {report['total_subtitles']}")
    print(f"CPS优化: {report['optimizations']['cps_optimized']}")
    print(f"合并建议: {report['optimizations']['merge_suggested']}")
    print(f"标点问题: {report['optimizations']['punctuation_issues']}")
    
    print("\n优化建议:")
    for suggestion in report['suggestions']:
        print(f"- {suggestion['type']}: {suggestion.get('reason', 'N/A')}")

if __name__ == "__main__":
    main()
