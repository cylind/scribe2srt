#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SRT字幕处理器模块
使用新的两阶段算法：基于标点符号的句子预分割 + 智能合并
"""

import datetime
from typing import Dict, List, Tuple

from .config import (
    MIN_SUBTITLE_DURATION, MIN_SUBTITLE_GAP, CPS_SETTINGS, CPL_SETTINGS
)
from .sentence_splitter import SentenceSplitter
from .intelligent_merger import IntelligentMerger


def format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
    td = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(td.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},{milliseconds:03d}"


class SrtProcessor:
    """
    SRT字幕处理器类
    
    核心功能：
    - 使用新的两阶段算法处理转录数据
    - 基于标点符号的语义分割
    - 智能合并优化
    - 多语言支持和专业标准遵循
    """
    
    def __init__(self, json_data: Dict, max_subtitle_duration: float = None,
                 subtitle_settings: Dict = None):
        self.srt_content = []
        self.line_number = 1
        self.language = json_data.get("language_code", "eng")[:3] # e.g., "eng"
        self.is_cjk = self._is_cjk_language()

        # 如果提供了高级设置，使用它们；否则使用默认值
        if subtitle_settings:
            self.max_subtitle_duration = subtitle_settings.get("max_subtitle_duration", 7.0)
            self.min_subtitle_duration = subtitle_settings.get("min_subtitle_duration", MIN_SUBTITLE_DURATION)
            self.min_subtitle_gap = subtitle_settings.get("min_subtitle_gap", MIN_SUBTITLE_GAP)

            # 使用用户自定义的CPS和CPL设置
            if self.is_cjk:
                self.max_cps = subtitle_settings.get("cjk_cps", CPS_SETTINGS["cjk"])
                self.max_chars_per_line = subtitle_settings.get("cjk_chars_per_line", CPL_SETTINGS["cjk"])
            else:
                self.max_cps = subtitle_settings.get("latin_cps", CPS_SETTINGS["latin"])
                self.max_chars_per_line = subtitle_settings.get("latin_chars_per_line", CPL_SETTINGS["latin"])
        else:
            # 使用传入参数或默认值（向后兼容）
            self.max_subtitle_duration = max_subtitle_duration if max_subtitle_duration is not None else 7.0
            self.min_subtitle_duration = MIN_SUBTITLE_DURATION
            self.min_subtitle_gap = MIN_SUBTITLE_GAP

            # 根据语言动态设置参数
            self.max_chars_per_line = self._get_max_chars_for_language()
            self.max_cps = self._get_max_cps_for_language()

        self._preprocess_words(json_data)

    def _is_cjk_language(self) -> bool:
        """Check if the language is CJK (Chinese, Japanese, Korean)."""
        return self.language in ["zho", "jpn", "kor", "chi", "zh", "ja", "ko"]

    def _get_max_chars_for_language(self) -> int:
        """Returns the recommended max characters per line based on language."""
        if self.is_cjk:
            return CPL_SETTINGS["cjk"]
        else:
            return CPL_SETTINGS["latin"]

    def _get_max_cps_for_language(self) -> float:
        """Returns the recommended max CPS based on language."""
        if self.is_cjk:
            return CPS_SETTINGS["cjk"]
        else:
            return CPS_SETTINGS["latin"]

    def _get_dynamic_cps_limit(self, text: str) -> float:
        """
        根据文本长度动态调整CPS限制

        Args:
            text: 文本内容

        Returns:
            动态调整后的CPS限制
        """
        import re
        base_cps = self.max_cps
        text_length = len(re.sub(r'\s+', '', text))  # 去除空白字符的长度

        # 对于极短文本，允许更高的CPS
        if text_length <= 3:
            return base_cps * 3.0  # 极短文本（如"啊"）允许3倍CPS
        elif text_length <= 5:
            return base_cps * 2.0  # 短文本允许2倍CPS
        elif text_length <= 10:
            return base_cps * 1.5  # 中短文本允许1.5倍CPS
        else:
            return base_cps

    def _preprocess_words(self, json_data: Dict):
        """
        Pre-processes the word list to handle language-specific quirks,
        such as merging standalone CJK punctuation and filtering out spacing characters.
        """
        raw_words = json_data.get("words", [])
        self.words = []
        for word_info in raw_words:
            # Skip spacing characters to fix timing issues with Latin text
            # But preserve the space character in the text of the previous word
            if word_info.get('type') == 'spacing':
                # Add space to the previous word if it exists and doesn't already end with space
                if (self.words and
                    word_info.get('text', '').strip() == '' and  # Only for actual spaces
                    self.words[-1].get('type') == 'word' and
                    not self.words[-1]['text'].endswith(' ')):
                    self.words[-1]['text'] += ' '
                continue

            is_cjk_punctuation = len(word_info['text']) == 1 and word_info['text'] in "。？！」「、・，"
            if is_cjk_punctuation and self.words:
                prev_word = self.words[-1]
                if prev_word.get("type") == "word" and prev_word['text'] and prev_word['text'][-1] not in "。？！」「、・，":
                    prev_word['text'] += word_info['text']
                    prev_word['end'] = word_info['end']
                    continue
            self.words.append(word_info)

    def create_srt(self) -> str:
        """
        Creates the full SRT content using the new two-stage approach:
        1. Sentence-level pre-splitting based on punctuation priority
        2. Intelligent merging based on CPS, CPL, and display time rules
        """
        if not self.words:
            return ""

        # Stage 1: Sentence-level pre-splitting
        sentence_splitter = SentenceSplitter(self.language)
        sentence_groups = sentence_splitter.split_into_sentence_groups(self.words)
        basic_entries = sentence_splitter.create_basic_subtitle_entries(sentence_groups)

        # Stage 2: Intelligent merging
        subtitle_settings = {
            'min_subtitle_duration': self.min_subtitle_duration,
            'min_subtitle_gap': self.min_subtitle_gap,
            'max_subtitle_duration': self.max_subtitle_duration,
            'cjk_cps': self.max_cps if self.is_cjk else CPS_SETTINGS["cjk"],
            'latin_cps': self.max_cps if not self.is_cjk else CPS_SETTINGS["latin"],
            'cjk_chars_per_line': self.max_chars_per_line if self.is_cjk else CPL_SETTINGS["cjk"],
            'latin_chars_per_line': self.max_chars_per_line if not self.is_cjk else CPL_SETTINGS["latin"]
        }
        
        intelligent_merger = IntelligentMerger(self.language, subtitle_settings)
        merged_entries = intelligent_merger.merge_basic_entries(basic_entries)
        optimized_entries = intelligent_merger.optimize_merged_entries(merged_entries)

        # Stage 3: Generate final SRT content with optimized display formatting
        return self._generate_final_srt_content(optimized_entries)

    def _generate_final_srt_content(self, entries: List[Dict]) -> str:
        """
        Generate final SRT content with optimized display formatting
        
        Args:
            entries: List of optimized subtitle entries
            
        Returns:
            Final SRT content string
        """
        if not entries:
            return ""
        
        srt_lines = []
        
        for i, entry in enumerate(entries, 1):
            # Format timing
            start_time_str = format_srt_time(entry['start'])
            end_time_str = format_srt_time(entry['end'])
            
            # Optimize text display format
            formatted_text = self._optimize_text_display(entry['text'])
            
            # Generate SRT entry
            srt_entry = f"{i}\n{start_time_str} --> {end_time_str}\n{formatted_text}\n"
            srt_lines.append(srt_entry)
        
        return "\n".join(srt_lines)
    
    def _optimize_text_display(self, text: str) -> str:
        """
        Optimize text display format: prioritize single line, break at punctuation if needed
        
        Args:
            text: Original text
            
        Returns:
            Optimized display text
        """
        text = text.strip()
        if not text:
            return text
        
        # If text fits in single line, return as-is
        if len(text) <= self.max_chars_per_line:
            return text
        
        # Need to split into multiple lines, prioritize punctuation breaks
        return self._split_text_into_lines(text)

    def _split_text_into_lines(self, text: str) -> str:
        """
        Intelligently splits a text block into a maximum of two lines,
        following professional subtitle standards for line breaking.

        Prioritizes semantic completeness over visual aesthetics (Netflix standard).
        """
        text = text.strip()
        if len(text) <= self.max_chars_per_line:
            return text

        # Find the best split position for the first line
        split_pos = self._find_best_split_position(text, self.max_chars_per_line)

        first_line = text[:split_pos].strip()
        remaining_text = text[split_pos:].strip()

        # If remaining text fits in the second line, return two lines
        if len(remaining_text) <= self.max_chars_per_line:
            return f"{first_line}\n{remaining_text}"
        else:
            # If remaining text is too long, return as-is to preserve content
            return f"{first_line}\n{remaining_text}"

    def _find_best_split_position(self, text: str, max_length: int) -> int:
        """
        Find the best position to split text following semantic rules.
        Prioritizes linguistic sense over visual aesthetics (Netflix standard).
        """
        if len(text) <= max_length:
            return len(text)

        split_chars = self._get_split_characters()

        # Search for the best split position within the allowed range
        best_pos = -1
        search_end = min(max_length + 1, len(text))

        # Try to find split characters in reverse order (prefer later positions)
        for i in range(search_end - 1, 0, -1):
            if text[i] in split_chars:
                # For spaces, split before the space
                if text[i] == ' ':
                    best_pos = i
                    break
                # For punctuation, split after the punctuation
                else:
                    best_pos = i + 1
                    break

        # If no good split point found, force split at max_length
        if best_pos <= 0:
            best_pos = max_length

        return best_pos

    def _get_split_characters(self) -> str:
        """Get appropriate split characters based on language."""
        if self.is_cjk:
            # CJK languages: prioritize punctuation marks
            return "。？！、，；：""''（）《》「」 "
        else:
            # Latin languages: prioritize spaces and common punctuation
            return " .,;:!?()\"'-"


def create_srt_from_json(json_data: Dict, max_subtitle_duration: float = None,
                        subtitle_settings: Dict = None) -> str:
    """
    Processes transcription JSON data to create a professional SRT file.

    Args:
        json_data: Transcription data from ElevenLabs or similar service
        max_subtitle_duration: Maximum duration for a single subtitle (default: 7.0s)
        subtitle_settings: Dictionary containing advanced subtitle settings

    Returns:
        Professional SRT content following industry standards
    """
    processor = SrtProcessor(json_data, max_subtitle_duration, subtitle_settings)
    return processor.create_srt()
