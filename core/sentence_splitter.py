#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
句子分割器模块
实现基于标点符号优先级的句子边界检测，支持多语言和特殊类型处理
"""

from typing import Dict, List, Tuple
import re


class SentenceSplitter:
    """
    句子分割器类
    
    核心功能：
    1. 基于标点符号优先级进行句子边界检测
    2. 正确处理spacing类型的空白字符
    3. 识别并单独处理音频事件
    4. 支持多语言（CJK和Latin）
    """
    
    def __init__(self, language_code: str = "eng"):
        self.language = language_code[:3]
        self.is_cjk = self._is_cjk_language()
        
        # 定义标点符号优先级
        if self.is_cjk:
            self.high_priority_punct = ["。", "！", "？"]  # 句子结束符
            self.medium_priority_punct = ["；", "："]      # 子句结束符
            self.low_priority_punct = ["，", "、"]         # 短语分隔符
        else:
            self.high_priority_punct = [".", "!", "?"]    # 句子结束符
            self.medium_priority_punct = [";", ":"]       # 子句结束符
            self.low_priority_punct = [","]               # 短语分隔符
        
        # 所有分割标点符号
        self.all_split_punct = (self.high_priority_punct + 
                               self.medium_priority_punct + 
                               self.low_priority_punct)
        
        # 音频事件关键词（可扩展）
        self.audio_event_keywords = [
            "music", "sound", "noise", "applause", "laughter",
            "音乐", "音效", "掌声", "笑声", "背景音",
            "♪", "♫", "♬", "♩", "🎵", "🎶"
        ]
    
    def _is_cjk_language(self) -> bool:
        """检查是否为CJK语言"""
        return self.language in ["zho", "jpn", "kor", "chi", "zh", "ja", "ko"]
    
    def _is_audio_event(self, word_info: Dict) -> bool:
        """
        检测是否为音频事件
        
        Args:
            word_info: 单词信息字典
            
        Returns:
            是否为音频事件
        """
        text = word_info.get('text', '').strip().lower()
        
        # 检查是否包含音频事件关键词
        for keyword in self.audio_event_keywords:
            if keyword.lower() in text:
                return True
        
        # 检查是否为纯符号（可能是音乐符号）
        if re.match(r'^[^\w\s]+$', text) and len(text) <= 3:
            return True
            
        return False
    
    def _get_punctuation_priority(self, punct: str) -> int:
        """
        获取标点符号的优先级
        
        Args:
            punct: 标点符号
            
        Returns:
            优先级 (0=高, 1=中, 2=低, -1=不是分割标点)
        """
        if punct in self.high_priority_punct:
            return 0
        elif punct in self.medium_priority_punct:
            return 1
        elif punct in self.low_priority_punct:
            return 2
        else:
            return -1
    
    def _word_ends_with_split_punct(self, word_info: Dict) -> Tuple[bool, str, int]:
        """
        检查单词是否以分割标点符号结尾
        
        Args:
            word_info: 单词信息字典
            
        Returns:
            (是否以分割标点结尾, 标点符号, 优先级)
        """
        text = word_info.get('text', '').strip()
        if not text:
            return False, "", -1
        
        # 检查最后一个字符
        last_char = text[-1]
        priority = self._get_punctuation_priority(last_char)
        
        if priority >= 0:
            return True, last_char, priority
        
        return False, "", -1
    
    def _should_split_at_word(self, word_info: Dict, accumulated_words: List[Dict]) -> bool:
        """
        判断是否应该在此单词处分割句子
        
        Args:
            word_info: 当前单词信息
            accumulated_words: 已累积的单词列表
            
        Returns:
            是否应该分割
        """
        # 如果是音频事件，应该独立成句
        if self._is_audio_event(word_info):
            return True
        
        # 检查是否以分割标点符号结尾
        has_punct, punct, priority = self._word_ends_with_split_punct(word_info)
        
        if not has_punct:
            return False
        
        # 高优先级标点符号总是分割
        if priority == 0:
            return True
        
        # 中优先级标点符号：需要有足够的内容
        if priority == 1:
            if len(accumulated_words) >= 3:  # 至少3个词
                return True
        
        # 低优先级标点符号：需要更多内容且不能太频繁分割
        if priority == 2:
            if len(accumulated_words) >= 5:  # 至少5个词
                # 检查前面是否刚刚有过分割
                total_chars = sum(len(w.get('text', '')) for w in accumulated_words)
                if total_chars >= 15:  # 至少15个字符
                    return True
        
        return False
    
    def split_into_sentence_groups(self, words: List[Dict]) -> List[List[Dict]]:
        """
        将单词列表分割成句子组
        
        Args:
            words: 单词列表
            
        Returns:
            句子组列表，每个句子组包含一组相关的单词
        """
        if not words:
            return []
        
        sentence_groups = []
        current_group = []
        
        for i, word in enumerate(words):
            # 跳过spacing类型，但保留其文本内容到前一个单词
            if word.get('type') == 'spacing':
                if current_group and word.get('text', '').strip() == '':
                    # 将空格添加到前一个单词的文本中
                    if not current_group[-1]['text'].endswith(' '):
                        current_group[-1]['text'] += ' '
                continue
            
            # 添加当前单词到组中
            current_group.append(word.copy())
            
            # 检查是否应该在此处分割
            should_split = self._should_split_at_word(word, current_group[:-1])
            
            # 如果是最后一个单词，强制分割
            is_last_word = (i == len(words) - 1)
            
            if should_split or is_last_word:
                if current_group:
                    sentence_groups.append(current_group)
                    current_group = []
        
        # 处理剩余的单词
        if current_group:
            sentence_groups.append(current_group)
        
        return sentence_groups
    
    def create_basic_subtitle_entries(self, sentence_groups: List[List[Dict]]) -> List[Dict]:
        """
        从句子组创建基本字幕条目
        
        Args:
            sentence_groups: 句子组列表
            
        Returns:
            基本字幕条目列表
        """
        basic_entries = []
        
        for group in sentence_groups:
            if not group:
                continue
            
            # 提取实际单词（非spacing类型）
            actual_words = [w for w in group if w.get('type') == 'word']
            
            if not actual_words:
                continue
            
            # 构建文本
            text = "".join(w['text'] for w in group).strip()
            
            if not text:
                continue
            
            # 计算时间范围
            start_time = actual_words[0]['start']
            end_time = actual_words[-1]['end']
            
            # 创建基本条目
            entry = {
                'text': text,
                'start': start_time,
                'end': end_time,
                'words': group,
                'is_audio_event': any(self._is_audio_event(w) for w in group),
                'word_count': len(actual_words),
                'char_count': len(text.replace(' ', ''))  # 不计空格的字符数
            }
            
            basic_entries.append(entry)
        
        return basic_entries
    
    def analyze_split_quality(self, sentence_groups: List[List[Dict]]) -> Dict:
        """
        分析分割质量
        
        Args:
            sentence_groups: 句子组列表
            
        Returns:
            分割质量分析结果
        """
        if not sentence_groups:
            return {'total_groups': 0, 'avg_words_per_group': 0, 'punct_endings': 0}
        
        total_groups = len(sentence_groups)
        total_words = sum(len(group) for group in sentence_groups)
        avg_words_per_group = total_words / total_groups if total_groups > 0 else 0
        
        # 统计以标点符号结尾的组数
        punct_endings = 0
        for group in sentence_groups:
            if group:
                last_word = group[-1]
                has_punct, _, _ = self._word_ends_with_split_punct(last_word)
                if has_punct:
                    punct_endings += 1
        
        punct_ending_rate = punct_endings / total_groups if total_groups > 0 else 0
        
        return {
            'total_groups': total_groups,
            'total_words': total_words,
            'avg_words_per_group': avg_words_per_group,
            'punct_endings': punct_endings,
            'punct_ending_rate': punct_ending_rate
        }
