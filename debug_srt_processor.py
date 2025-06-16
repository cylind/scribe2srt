#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
调试版本的SRT处理器，用于理解分割逻辑
"""

import datetime
from typing import Dict, List, Tuple

from core.config import (
    MIN_SUBTITLE_DURATION, MIN_SUBTITLE_GAP, CPS_SETTINGS, CPL_SETTINGS
)

def format_srt_time(seconds: float) -> str:
    """Formats seconds into SRT time format HH:MM:SS,ms."""
    delta = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = int(delta.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

class DebugSrtProcessor:
    """调试版本的SRT处理器"""
    
    def __init__(self, json_data: Dict):
        self.srt_content = []
        self.line_number = 1
        self.language = json_data.get("language_code", "eng")[:3]
        self.is_cjk = self._is_cjk_language()
        self.max_chars_per_line = CPL_SETTINGS["cjk"] if self.is_cjk else CPL_SETTINGS["latin"]
        self.max_cps = CPS_SETTINGS["cjk"] if self.is_cjk else CPS_SETTINGS["latin"]
        self.pause_threshold = 0.7
        self.max_subtitle_duration = 7.0
        self.min_subtitle_duration = MIN_SUBTITLE_DURATION
        self.min_subtitle_gap = MIN_SUBTITLE_GAP
        
        self._preprocess_words(json_data)
        
    def _is_cjk_language(self) -> bool:
        """Check if the language is CJK (Chinese, Japanese, Korean)."""
        return self.language in ["zho", "jpn", "kor", "chi", "zh", "ja", "ko"]
        
    def _preprocess_words(self, json_data: Dict):
        """Pre-processes the word list."""
        raw_words = json_data.get("words", [])
        self.words = []
        for i, word_info in enumerate(raw_words):
            is_cjk_punctuation = len(word_info['text']) == 1 and word_info['text'] in "。？！」「、"
            if is_cjk_punctuation and self.words:
                prev_word = self.words[-1]
                if prev_word.get("type") == "word" and prev_word['text'] and prev_word['text'][-1] not in "。？！」「、":
                    prev_word['text'] += word_info['text']
                    prev_word['end'] = word_info['end']
                    continue
            self.words.append(word_info)
            
    def _text_exceeds_two_lines(self, text: str) -> bool:
        """Check if text would exceed two-line subtitle limits."""
        if len(text) <= self.max_chars_per_line:
            return False  # Single line, no problem
        # For simplicity, assume if text > 2 * max_chars_per_line, it exceeds
        return len(text) > self.max_chars_per_line * 2
        
    def _find_recent_punctuation_break(self, current_block: List[Dict]) -> int:
        """Find punctuation break point with debug info."""
        if len(current_block) < 2:
            print(f"    [DEBUG] Block too short: {len(current_block)} words")
            return -1
            
        print(f"    [DEBUG] Looking for punctuation in block of {len(current_block)} words:")
        for i, word in enumerate(current_block):
            print(f"      Word {i}: '{word['text']}'")
            
        # Define punctuation in priority order
        if self.is_cjk:
            high_priority = ["。", "！", "？"]
            medium_priority = ["；", "："] 
            low_priority = ["，", "、"]
        else:
            high_priority = [".", "!", "?"]
            medium_priority = [";", ":"]
            low_priority = [","]
            
        # Try high priority punctuation first
        for priority, punct_list in enumerate([high_priority, medium_priority, low_priority]):
            print(f"    [DEBUG] Trying priority {priority} punctuation: {punct_list}")
            for i in range(len(current_block) - 1, 0, -1):
                word_text = current_block[i]['text'].strip()
                for punct in punct_list:
                    if word_text.endswith(punct):
                        print(f"    [DEBUG] Found '{punct}' at index {i}")
                        # Check if breaking here creates reasonable segments
                        text_before = "".join(w['text'] for w in current_block[:i+1]).strip()
                        text_after = "".join(w['text'] for w in current_block[i+1:]).strip()
                        
                        print(f"    [DEBUG] Text before: '{text_before}' (len={len(text_before)})")
                        print(f"    [DEBUG] Text after: '{text_after}' (len={len(text_after)})")
                        
                        if (len(text_before) >= 8 and len(text_after) >= 3 and
                            len(text_before) <= self.max_chars_per_line * 2):
                            print(f"    [DEBUG] Good break point found at index {i}")
                            return i
                        else:
                            print(f"    [DEBUG] Break point at index {i} rejected")
        
        print(f"    [DEBUG] No suitable punctuation found")
        return -1
        
    def _should_break_before_adding_word(self, word: Dict, current_block: List[Dict]) -> bool:
        """Debug version of break detection."""
        if not current_block:
            return False
            
        current_text = "".join(w['text'] for w in current_block).strip()
        text_with_new_word = current_text + word['text']
        
        print(f"  [DEBUG] Checking if should break before adding '{word['text']}'")
        print(f"  [DEBUG] Current text: '{current_text}' (len={len(current_text)})")
        print(f"  [DEBUG] With new word: '{text_with_new_word}' (len={len(text_with_new_word)})")
        print(f"  [DEBUG] Max chars per line: {self.max_chars_per_line}")
        print(f"  [DEBUG] Threshold (1.3x): {self.max_chars_per_line * 1.3}")
        
        # If adding the word doesn't cause length issues, don't break
        if len(text_with_new_word) <= self.max_chars_per_line * 1.3:
            print(f"  [DEBUG] Text still within limits, no break needed")
            return False
            
        print(f"  [DEBUG] Text approaching limits, looking for punctuation break")
        punctuation_break_index = self._find_recent_punctuation_break(current_block)
        
        if punctuation_break_index >= 0:
            print(f"  [DEBUG] Found punctuation break at index {punctuation_break_index}")
            return True
        
        # If no good punctuation break and text would exceed two lines, we must break
        exceeds_two_lines = self._text_exceeds_two_lines(text_with_new_word)
        print(f"  [DEBUG] Exceeds two lines: {exceeds_two_lines}")
        return exceeds_two_lines
        
    def create_srt_debug(self) -> str:
        """Create SRT with debug output."""
        if not self.words:
            return ""

        current_block = []
        
        print(f"[DEBUG] Starting SRT creation with {len(self.words)} words")
        print(f"[DEBUG] Max chars per line: {self.max_chars_per_line}")

        for i, word in enumerate(self.words):
            print(f"\n[DEBUG] Processing word {i}: '{word['text']}'")
            
            # Handle audio events separately
            if word.get("type") == "audio_event":
                if current_block:
                    print(f"[DEBUG] Finalizing block before audio event")
                    self._finalize_and_add_subtitle_debug(current_block)
                    current_block = []
                self._finalize_and_add_subtitle_debug([word])
                continue

            is_last_word = (i == len(self.words) - 1)

            # Check if we should break before adding this word
            should_break_before_adding = self._should_break_before_adding_word(word, current_block)
            
            if should_break_before_adding:
                print(f"[DEBUG] Breaking before adding word '{word['text']}'")
                # Find optimal break point and split
                optimal_break_point = self._find_optimal_break_point_debug(current_block)
                
                if optimal_break_point > 0 and optimal_break_point < len(current_block):
                    first_part = current_block[:optimal_break_point]
                    remaining_part = current_block[optimal_break_point:]
                    
                    print(f"[DEBUG] Splitting at position {optimal_break_point}")
                    self._finalize_and_add_subtitle_debug(first_part)
                    current_block = remaining_part + [word]
                else:
                    print(f"[DEBUG] No good split point, finalizing whole block")
                    self._finalize_and_add_subtitle_debug(current_block)
                    current_block = [word]
            else:
                # Add word to current block
                current_block.append(word)
                print(f"[DEBUG] Added word to block, block size now: {len(current_block)}")
                
            # Check if we should break after adding (for other reasons like last word)
            if is_last_word and current_block:
                print(f"[DEBUG] Last word, finalizing remaining block")
                self._finalize_and_add_subtitle_debug(current_block)
                current_block = []

        return "\n".join(self.srt_content)
        
    def _find_optimal_break_point_debug(self, current_block: List[Dict]) -> int:
        """Debug version of optimal break point finding."""
        print(f"    [DEBUG] Finding optimal break point in block of {len(current_block)} words")
        
        if len(current_block) <= 1:
            return len(current_block)
            
        # Try to find recent punctuation break
        recent_punct_index = self._find_recent_punctuation_break(current_block)
        
        if recent_punct_index >= 0:
            break_position = recent_punct_index + 1
            print(f"    [DEBUG] Using punctuation break at position {break_position}")
            return break_position
            
        print(f"    [DEBUG] No punctuation break found, breaking at end")
        return len(current_block)
        
    def _finalize_and_add_subtitle_debug(self, words_in_block):
        """Debug version of subtitle finalization."""
        if not words_in_block:
            return

        text = "".join(w['text'] for w in words_in_block).strip()
        if not text:
            return

        print(f"    [DEBUG] Finalizing subtitle: '{text}' (len={len(text)})")

        start_time = words_in_block[0]['start']
        end_time = words_in_block[-1]['end']

        subtitle_entry = f"{self.line_number}\n{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n{text}\n"
        self.srt_content.append(subtitle_entry)
        self.line_number += 1

def debug_create_srt_from_json(json_data: Dict) -> str:
    """Debug version of SRT creation."""
    processor = DebugSrtProcessor(json_data)
    return processor.create_srt_debug()
