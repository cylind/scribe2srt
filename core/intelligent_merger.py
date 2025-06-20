#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
智能合并算法模块
基于CPS、CPL、显示时间等规则的智能合并机制
"""

from typing import Dict, List, Tuple
import re
from .config import MIN_SUBTITLE_DURATION, MIN_SUBTITLE_GAP, CPS_SETTINGS, CPL_SETTINGS


class IntelligentMerger:
    """
    智能合并器类
    
    核心功能：
    1. 基于多种规则约束进行智能合并
    2. 优化显示时间和字符密度
    3. 保持语义完整性
    4. 支持多语言优化
    """
    
    def __init__(self, language_code: str = "eng", subtitle_settings: Dict = None):
        self.language = language_code[:3]
        self.is_cjk = self._is_cjk_language()
        
        # 初始化规则参数
        if subtitle_settings:
            self.min_subtitle_duration = subtitle_settings.get("min_subtitle_duration", MIN_SUBTITLE_DURATION)
            self.min_subtitle_gap = subtitle_settings.get("min_subtitle_gap", MIN_SUBTITLE_GAP)
            self.max_subtitle_duration = subtitle_settings.get("max_subtitle_duration", 7.0)
            
            if self.is_cjk:
                self.max_cps = subtitle_settings.get("cjk_cps", CPS_SETTINGS["cjk"])
                self.max_chars_per_line = subtitle_settings.get("cjk_chars_per_line", CPL_SETTINGS["cjk"])
            else:
                self.max_cps = subtitle_settings.get("latin_cps", CPS_SETTINGS["latin"])
                self.max_chars_per_line = subtitle_settings.get("latin_chars_per_line", CPL_SETTINGS["latin"])
        else:
            # 使用默认值
            self.min_subtitle_duration = MIN_SUBTITLE_DURATION
            self.min_subtitle_gap = MIN_SUBTITLE_GAP
            self.max_subtitle_duration = 7.0
            
            if self.is_cjk:
                self.max_cps = CPS_SETTINGS["cjk"]
                self.max_chars_per_line = CPL_SETTINGS["cjk"]
            else:
                self.max_cps = CPS_SETTINGS["latin"]
                self.max_chars_per_line = CPL_SETTINGS["latin"]
    
    def _is_cjk_language(self) -> bool:
        """检查是否为CJK语言"""
        return self.language in ["zho", "jpn", "kor", "chi", "zh", "ja", "ko"]
    
    def _calculate_cps(self, text: str, duration: float) -> float:
        """计算CPS（每秒字符数）"""
        if duration <= 0:
            return float('inf')
        
        # 去除空白字符计算实际字符数
        char_count = len(re.sub(r'\s+', '', text))
        return char_count / duration
    
    def _calculate_display_lines(self, text: str) -> int:
        """计算文本需要的显示行数"""
        if not text:
            return 0
        
        # 简单估算：按最大字符数分行
        lines = []
        remaining_text = text.strip()
        
        while remaining_text:
            if len(remaining_text) <= self.max_chars_per_line:
                lines.append(remaining_text)
                break
            else:
                # 寻找合适的分割点
                split_pos = self._find_line_split_position(remaining_text)
                lines.append(remaining_text[:split_pos].strip())
                remaining_text = remaining_text[split_pos:].strip()
        
        return len(lines)
    
    def _find_line_split_position(self, text: str) -> int:
        """寻找行内分割位置"""
        if len(text) <= self.max_chars_per_line:
            return len(text)
        
        # 优先在标点符号处分割
        split_chars = "。？！、，；： .,;:!?()-" if self.is_cjk else " .,;:!?()-"
        
        # 从最大长度向前搜索分割点
        for i in range(min(self.max_chars_per_line, len(text)), 0, -1):
            if text[i-1] in split_chars:
                return i
        
        # 如果没找到合适的分割点，强制在最大长度处分割
        return min(self.max_chars_per_line, len(text))
    
    def _can_merge_entries(self, entry1: Dict, entry2: Dict) -> Tuple[bool, str]:
        """
        检查两个条目是否可以合并
        
        Args:
            entry1: 第一个条目
            entry2: 第二个条目
            
        Returns:
            (是否可以合并, 不能合并的原因)
        """
        # 音频事件不参与合并
        if entry1.get('is_audio_event', False) or entry2.get('is_audio_event', False):
            return False, "音频事件不参与合并"
        
        # 计算时间间隔
        gap = entry2['start'] - entry1['end']
        
        # 检查时间间隔约束 - 更严格的检查
        if gap < self.min_subtitle_gap:
            return False, f"时间间隔过小: {gap:.3f}s < {self.min_subtitle_gap:.3f}s"
        
        # 如果间隔太大，不适合合并
        if gap > 2.0:  # 间隔超过2秒不合并
            return False, f"时间间隔过大: {gap:.3f}s > 2.0s"
        
        # 计算合并后的属性
        merged_text = entry1['text'] + ' ' + entry2['text']  # 添加空格分隔
        merged_start = entry1['start']
        merged_end = entry2['end']
        merged_duration = merged_end - merged_start
        
        # 检查最大时长约束 - 更保守的限制
        max_allowed_duration = min(self.max_subtitle_duration, 6.0)  # 最多6秒
        if merged_duration > max_allowed_duration:
            return False, f"合并后时长过长: {merged_duration:.1f}s > {max_allowed_duration:.1f}s"
        
        # 检查CPS约束
        merged_cps = self._calculate_cps(merged_text, merged_duration)
        dynamic_cps_limit = self._get_dynamic_cps_limit(merged_text)
        
        if merged_cps > dynamic_cps_limit:
            return False, f"合并后CPS过高: {merged_cps:.1f} > {dynamic_cps_limit:.1f}"
        
        # 检查显示行数约束
        merged_lines = self._calculate_display_lines(merged_text)
        if merged_lines > 2:
            return False, f"合并后行数过多: {merged_lines} > 2"
        
        # 检查单行长度约束
        if merged_lines == 1 and len(merged_text) > self.max_chars_per_line:
            return False, f"单行长度超限: {len(merged_text)} > {self.max_chars_per_line}"
        
        return True, ""
    
    def _get_dynamic_cps_limit(self, text: str) -> float:
        """根据文本长度动态调整CPS限制"""
        base_cps = self.max_cps
        text_length = len(re.sub(r'\s+', '', text))
        
        # 对于极短文本，允许更高的CPS
        if text_length <= 3:
            return base_cps * 3.0
        elif text_length <= 5:
            return base_cps * 2.0
        elif text_length <= 10:
            return base_cps * 1.5
        else:
            return base_cps
    
    def _calculate_merge_benefit(self, entry1: Dict, entry2: Dict) -> float:
        """
        计算合并两个条目的收益分数
        
        Args:
            entry1: 第一个条目
            entry2: 第二个条目
            
        Returns:
            合并收益分数（越高越好）
        """
        benefit_score = 0.0
        
        # 时长收益：过短的条目合并收益更高
        duration1 = entry1['end'] - entry1['start']
        duration2 = entry2['end'] - entry2['start']
        
        if duration1 < self.min_subtitle_duration:
            benefit_score += (self.min_subtitle_duration - duration1) * 20  # 增加权重
        
        if duration2 < self.min_subtitle_duration:
            benefit_score += (self.min_subtitle_duration - duration2) * 20  # 增加权重
        
        # 间隔收益：间隔越小，合并收益越高，但要求更严格
        gap = entry2['start'] - entry1['end']
        if gap < 0.3:  # 间隔小于300ms才有高收益
            benefit_score += (0.3 - gap) * 10
        elif gap < 0.5:  # 间隔小于500ms有中等收益
            benefit_score += (0.5 - gap) * 5
        
        # 字符数收益：过短的文本合并收益更高
        char_count1 = entry1.get('char_count', len(entry1['text']))
        char_count2 = entry2.get('char_count', len(entry2['text']))
        
        if char_count1 < 3:  # 极短文本
            benefit_score += (3 - char_count1) * 5
        elif char_count1 < 8:  # 短文本
            benefit_score += (8 - char_count1) * 2
        
        if char_count2 < 3:  # 极短文本
            benefit_score += (3 - char_count2) * 5
        elif char_count2 < 8:  # 短文本
            benefit_score += (8 - char_count2) * 2
        
        return benefit_score
    
    def merge_basic_entries(self, basic_entries: List[Dict]) -> List[Dict]:
        """
        智能合并基本条目
        
        Args:
            basic_entries: 基本条目列表
            
        Returns:
            合并后的条目列表
        """
        if not basic_entries:
            return []
        
        merged_entries = []
        i = 0
        
        while i < len(basic_entries):
            current_entry = basic_entries[i].copy()
            
            # 尝试与后续条目合并
            merged_any = True
            while merged_any and i + 1 < len(basic_entries):
                merged_any = False
                next_entry = basic_entries[i + 1]
                
                # 检查是否可以合并
                can_merge, reason = self._can_merge_entries(current_entry, next_entry)
                
                if can_merge:
                    # 计算合并收益
                    benefit = self._calculate_merge_benefit(current_entry, next_entry)
                    
                    # 如果收益足够高，执行合并
                    if benefit > 5.0:  # 提高收益阈值，更保守的合并策略
                        # 执行合并
                        current_entry = self._merge_two_entries(current_entry, next_entry)
                        i += 1  # 跳过已合并的条目
                        merged_any = True
            
            merged_entries.append(current_entry)
            i += 1
        
        return merged_entries

    def _merge_two_entries(self, entry1: Dict, entry2: Dict) -> Dict:
        """
        合并两个条目

        Args:
            entry1: 第一个条目
            entry2: 第二个条目

        Returns:
            合并后的条目
        """
        # 智能文本合并：根据语言和标点符号决定是否添加空格
        text1 = entry1['text'].strip()
        text2 = entry2['text'].strip()

        # 如果第一个文本以标点符号结尾，直接连接
        if text1 and text1[-1] in "。？！、，；：""''（）《》「」.?!,;:()\"'-":
            merged_text = text1 + text2
        else:
            # 否则添加适当的分隔符
            if self.is_cjk:
                merged_text = text1 + text2  # CJK语言通常不需要空格
            else:
                merged_text = text1 + ' ' + text2  # 拉丁语言添加空格

        merged_entry = {
            'text': merged_text,
            'start': entry1['start'],
            'end': entry2['end'],
            'words': entry1.get('words', []) + entry2.get('words', []),
            'is_audio_event': entry1.get('is_audio_event', False) or entry2.get('is_audio_event', False),
            'word_count': entry1.get('word_count', 0) + entry2.get('word_count', 0),
            'char_count': len(merged_text.replace(' ', ''))  # 重新计算字符数
        }

        return merged_entry

    def optimize_merged_entries(self, merged_entries: List[Dict]) -> List[Dict]:
        """
        优化合并后的条目

        Args:
            merged_entries: 合并后的条目列表

        Returns:
            优化后的条目列表
        """
        if not merged_entries:
            return []

        optimized_entries = []

        for i, entry in enumerate(merged_entries):
            optimized_entry = self._optimize_single_entry(entry)

            # 确保与下一个字幕的时间间隔
            if i + 1 < len(merged_entries):
                next_entry = merged_entries[i + 1]
                gap = next_entry['start'] - optimized_entry['end']

                if gap < self.min_subtitle_gap:
                    # 调整当前字幕的结束时间
                    optimized_entry['end'] = next_entry['start'] - self.min_subtitle_gap

                    # 确保不会导致时长过短
                    min_end_time = optimized_entry['start'] + self.min_subtitle_duration
                    if optimized_entry['end'] < min_end_time:
                        optimized_entry['end'] = min_end_time

            optimized_entries.append(optimized_entry)

        return optimized_entries

    def _optimize_single_entry(self, entry: Dict) -> Dict:
        """优化单个条目"""
        optimized_entry = entry.copy()

        # 优化时间
        duration = entry['end'] - entry['start']
        text = entry['text']

        # 确保最大时长限制
        if duration > self.max_subtitle_duration:
            optimized_entry['end'] = entry['start'] + self.max_subtitle_duration
            duration = self.max_subtitle_duration

        # 确保最小时长
        if duration < self.min_subtitle_duration:
            optimized_entry['end'] = entry['start'] + self.min_subtitle_duration
            duration = self.min_subtitle_duration

        # 确保CPS不超限
        current_cps = self._calculate_cps(text, duration)
        dynamic_limit = self._get_dynamic_cps_limit(text)

        if current_cps > dynamic_limit:
            required_duration = len(re.sub(r'\s+', '', text)) / dynamic_limit
            # 确保不超过最大时长限制
            required_duration = min(required_duration, self.max_subtitle_duration)
            optimized_entry['end'] = entry['start'] + required_duration

        return optimized_entry

    def analyze_merge_quality(self, original_entries: List[Dict], merged_entries: List[Dict]) -> Dict:
        """
        分析合并质量

        Args:
            original_entries: 原始条目列表
            merged_entries: 合并后条目列表

        Returns:
            合并质量分析结果
        """
        original_count = len(original_entries)
        merged_count = len(merged_entries)
        merge_rate = (original_count - merged_count) / original_count if original_count > 0 else 0

        # 统计时长分布
        short_duration_count = sum(1 for entry in merged_entries
                                 if (entry['end'] - entry['start']) < self.min_subtitle_duration)

        # 统计CPS分布
        high_cps_count = sum(1 for entry in merged_entries
                           if self._calculate_cps(entry['text'], entry['end'] - entry['start']) > self.max_cps)

        return {
            'original_count': original_count,
            'merged_count': merged_count,
            'merge_rate': merge_rate,
            'short_duration_count': short_duration_count,
            'high_cps_count': high_cps_count,
            'avg_duration': sum(entry['end'] - entry['start'] for entry in merged_entries) / merged_count if merged_count > 0 else 0
        }
