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

class SrtProcessor:
    """
    Processes word-level transcription data into professional SRT subtitles
    using a two-stage approach: semantic grouping and visual formatting.

    Follows professional subtitle standards including:
    - Dynamic CPS (Characters Per Second) based on language
    - Proper timing with minimum gaps between subtitles
    - Intelligent line breaking following semantic rules
    - Language-specific formatting optimizations
    """
    def __init__(self, json_data: Dict, pause_threshold: float = None, max_subtitle_duration: float = None,
                 subtitle_settings: Dict = None):
        self.srt_content = []
        self.line_number = 1
        self.language = json_data.get("language_code", "eng")[:3] # e.g., "eng"
        self.is_cjk = self._is_cjk_language()

        # 如果提供了高级设置，使用它们；否则使用默认值
        if subtitle_settings:
            self.pause_threshold = subtitle_settings.get("pause_threshold", 0.7)
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
            self.pause_threshold = pause_threshold if pause_threshold is not None else 0.7
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

            is_cjk_punctuation = len(word_info['text']) == 1 and word_info['text'] in "。？！」「、"
            if is_cjk_punctuation and self.words:
                prev_word = self.words[-1]
                if prev_word.get("type") == "word" and prev_word['text'] and prev_word['text'][-1] not in "。？！」「、":
                    prev_word['text'] += word_info['text']
                    prev_word['end'] = word_info['end']
                    continue
            self.words.append(word_info)

    def _get_split_characters(self) -> str:
        """Get appropriate split characters based on language."""
        if self.is_cjk:
            # CJK languages: prioritize punctuation marks
            return "。？！、，；：""''（）【】《》〈〉「」『』 "
        else:
            # Latin languages: prioritize spaces and common punctuation
            return " .,;:!?()[]{}\"'-"

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

    def _split_text_into_lines(self, text: str) -> str:
        """
        Intelligently splits a text block into a maximum of two lines,
        following professional subtitle standards for line breaking.

        Prioritizes semantic completeness over visual aesthetics (Netflix standard).

        Note: This method should NOT truncate text. If text is too long for two lines,
        it should be handled at the semantic grouping stage, not here.
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
            # The semantic grouping stage should have handled this case
            return f"{first_line}\n{remaining_text}"

    def _calculate_optimal_timing(self, text: str, start_time: float, end_time: float, next_word_start: float = None) -> Tuple[float, float]:
        """
        Calculate optimal timing for a subtitle following professional standards.

        Returns:
            Tuple of (adjusted_start_time, adjusted_end_time)
        """
        original_duration = end_time - start_time
        text_length = len(text)

        # Apply minimum duration constraint with enhanced logic
        if original_duration < self.min_subtitle_duration:
            # 优先延长到最小时长
            proposed_end_time = start_time + self.min_subtitle_duration

            # 检查是否与下一个字幕冲突
            if next_word_start is not None:
                max_allowed_end = next_word_start - self.min_subtitle_gap
                if proposed_end_time > max_allowed_end:
                    # 如果延长会冲突，标记为需要后续合并处理
                    end_time = min(proposed_end_time, max_allowed_end)
                else:
                    end_time = proposed_end_time
            else:
                end_time = proposed_end_time

        # Apply maximum duration constraint
        if original_duration > self.max_subtitle_duration:
            end_time = start_time + self.max_subtitle_duration

        # Apply CPS (Characters Per Second) constraint with dynamic limit
        effective_duration = end_time - start_time
        current_cps = text_length / effective_duration if effective_duration > 0 else 999

        # Use dynamic CPS limit based on text length
        dynamic_cps_limit = self._get_dynamic_cps_limit(text)

        if current_cps > dynamic_cps_limit:
            # Extend duration to meet CPS requirement
            required_duration = text_length / dynamic_cps_limit
            end_time = start_time + required_duration

        # Ensure minimum gap with next subtitle
        if next_word_start is not None:
            max_allowed_end = next_word_start - self.min_subtitle_gap
            if end_time > max_allowed_end:
                end_time = max_allowed_end

                # If this creates a timing conflict, prioritize readability
                if end_time <= start_time:
                    end_time = start_time + self.min_subtitle_duration
                    # In this case, we might need to shorten the text or adjust next subtitle

        return start_time, end_time

    def _finalize_and_add_subtitle(self, words_in_block, next_word_start=None):
        """
        Takes a block of words, formats them into a subtitle, and adds it to the list.
        This is the 'Visual Formatting' stage with professional timing standards.
        """
        if not words_in_block:
            return

        text = "".join(w['text'] for w in words_in_block).strip()
        if not text:
            return  # Fix for empty subtitle bug

        # Find the first and last actual words (not spacing) for timing
        # This fixes the issue where spacing characters cause incorrect timing
        word_blocks = [w for w in words_in_block if w.get('type') == 'word']

        if not word_blocks:
            # If no actual words found, fall back to original logic
            start_time = words_in_block[0]['start']
            end_time = words_in_block[-1]['end']
        else:
            # Use timing from actual words only, ignoring spacing characters
            start_time = word_blocks[0]['start']
            end_time = word_blocks[-1]['end']

        # Calculate optimal timing using professional standards
        start_time, end_time = self._calculate_optimal_timing(text, start_time, end_time, next_word_start)

        # Format text with intelligent line breaking
        final_text = self._split_text_into_lines(text)

        # Add subtitle to content
        subtitle_entry = f"{self.line_number}\n{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n{final_text}\n"
        self.srt_content.append(subtitle_entry)
        self.line_number += 1

    def _get_hard_break_characters(self) -> str:
        """Get hard break characters based on language."""
        if self.is_cjk:
            return ".?!。？！；：""''』」》〉"
        else:
            return '.?!;:"\''

    def _should_break_at_word(self, word: Dict, current_block: List[Dict], is_last_word: bool, next_word_start: float = None) -> bool:
        """
        Determine if we should break the subtitle at this word based on professional rules.
        Enhanced to better detect when we should break before adding a word.

        Args:
            word: Current word dictionary
            current_block: Current block of words
            is_last_word: Whether this is the last word
            next_word_start: Start time of next word (if any)

        Returns:
            Boolean indicating whether to break
        """
        if not current_block:
            return False

        # Always break at the last word
        if is_last_word:
            return True

        # Check for hard break characters (sentence endings) in the PREVIOUS word
        # This ensures we break AFTER punctuation, not before it
        if len(current_block) > 0:
            prev_word = current_block[-1]
            hard_break_chars = self._get_hard_break_characters()
            ends_with_hard_break = prev_word['text'] and prev_word['text'][-1] in hard_break_chars

            # If previous word ended with hard break and we have enough content, break here
            if ends_with_hard_break:
                current_text = "".join(w['text'] for w in current_block).strip()
                if len(current_text) >= 10:  # Minimum reasonable length
                    return True

        # Check for long pause (natural speech break)
        long_pause = False
        if next_word_start is not None:
            pause_duration = next_word_start - word['end']
            long_pause = pause_duration > self.pause_threshold

        # Check for maximum duration exceeded - but be more lenient for short phrases
        duration_so_far = word['end'] - current_block[0]['start']
        duration_exceeded = duration_so_far > self.max_subtitle_duration

        # NEW: Check if this is a short phrase that should stay together despite duration
        if duration_exceeded:
            current_text = "".join(w['text'] for w in current_block).strip()
            # If it's a short phrase (like "I'm not doing this"), be more lenient
            if self._is_short_phrase_that_should_stay_together(current_text, next_word_start, word['end']):
                duration_exceeded = False
            # Also check if current block looks like start of a common phrase
            elif self._looks_like_phrase_beginning(current_text):
                duration_exceeded = False

        # Enhanced text length check with punctuation priority - this is the key improvement
        text_length_check = self._should_break_for_length_enhanced(current_block, word)

        return long_pause or duration_exceeded or text_length_check

    def _is_short_phrase_that_should_stay_together(self, current_text: str, next_word_start: float, current_word_end: float) -> bool:
        """
        Check if this is a short phrase that should stay together despite duration limits.

        Args:
            current_text: Current text in the block
            next_word_start: Start time of next word (if any)
            current_word_end: End time of current word

        Returns:
            Boolean indicating if this phrase should stay together
        """
        # If the text is very short (like single words or short phrases), be more lenient
        word_count = len(current_text.split())

        # For very short phrases (1-4 words), be more lenient with duration
        if word_count <= 4:
            # Check if there's a reasonable pause after this phrase
            if next_word_start is not None:
                pause_after = next_word_start - current_word_end
                # If there's a natural pause after this short phrase, keep it together
                if pause_after > 0.3:  # 300ms pause suggests natural break point
                    return True

            # Also check for common short phrases that should stay together
            short_phrases = [
                "I'm not", "I'm not doing", "I'm not doing this",
                "you're not", "we're not", "they're not",
                "don't do", "can't do", "won't do",
                "let's go", "let's not", "let's do"
            ]

            for phrase in short_phrases:
                if phrase.lower() in current_text.lower():
                    return True

        return False

    def _looks_like_phrase_beginning(self, current_text: str) -> bool:
        """
        Check if the current text looks like the beginning of a common phrase that should be kept together.

        Args:
            current_text: Current text in the block

        Returns:
            Boolean indicating if this looks like a phrase beginning
        """
        # Common phrase beginnings that should be kept with following words
        phrase_beginnings = [
            "I'm", "you're", "we're", "they're", "he's", "she's", "it's",
            "don't", "can't", "won't", "shouldn't", "couldn't", "wouldn't",
            "let's", "that's", "what's", "where's", "when's", "how's",
            "I'll", "you'll", "we'll", "they'll", "he'll", "she'll"
        ]

        current_text_lower = current_text.lower().strip()

        # Check if current text is exactly one of these phrase beginnings
        for beginning in phrase_beginnings:
            if current_text_lower == beginning.lower():
                return True

        return False

    def _should_merge_short_subtitles(self, current_subtitle: str, next_subtitle: str,
                                     current_end: float, next_start: float) -> bool:
        """
        判断是否应该合并短字幕

        Args:
            current_subtitle: 当前字幕文本
            next_subtitle: 下一个字幕文本
            current_end: 当前字幕结束时间
            next_start: 下一个字幕开始时间

        Returns:
            是否应该合并
        """
        import re

        # 计算当前字幕的字符数（去除空白）
        current_chars = len(re.sub(r'\s+', '', current_subtitle))
        next_chars = len(re.sub(r'\s+', '', next_subtitle))

        # 计算间隔
        gap = next_start - current_end

        # 合并条件：
        # 1. 当前字幕很短（少于5个字符）
        # 2. 间隔很小（小于500ms）
        # 3. 合并后总长度不超过50个字符
        if (current_chars <= 5 and
            gap < 0.5 and
            current_chars + next_chars <= 50):
            return True

        # 或者：两个都很短且间隔很小
        if (current_chars <= 3 and
            next_chars <= 3 and
            gap < 0.3):
            return True

        return False

    def _should_break_before_adding_word(self, word: Dict, current_block: List[Dict]) -> bool:
        """
        Determine if we should break BEFORE adding this word to the current block.
        Enhanced to be more aggressive about finding punctuation breaks.

        Args:
            word: The word we're considering adding
            current_block: Current block of words (without the new word)

        Returns:
            Boolean indicating whether to break before adding the word
        """
        if not current_block:
            return False  # Never break if block is empty

        # Get current text and projected text with new word
        current_text = "".join(w['text'] for w in current_block).strip()
        text_with_new_word = current_text + word['text']

        # Very aggressive length checking - start looking for breaks even earlier
        if len(text_with_new_word) <= self.max_chars_per_line * 0.95:  # Further reduced to 0.95x
            return False

        # We're approaching length limits, aggressively look for punctuation breaks
        punctuation_break_index = self._find_best_punctuation_break_aggressive(current_block)

        if punctuation_break_index >= 0:
            # Found punctuation, check if breaking there creates reasonable segments
            text_before_punct = "".join(w['text'] for w in current_block[:punctuation_break_index+1]).strip()
            text_after_punct = "".join(w['text'] for w in current_block[punctuation_break_index+1:]).strip() + word['text']

            # Even more lenient requirements for punctuation breaks
            if (len(text_before_punct) >= 4 and  # Further reduced from 6
                len(text_after_punct) >= 2 and  # Further reduced from 3
                not self._text_exceeds_two_lines(text_before_punct) and
                not self._text_exceeds_two_lines(text_after_punct)):
                return True

        # If no good punctuation break and text would exceed two lines, we must break
        return self._text_exceeds_two_lines(text_with_new_word)

    def _find_best_punctuation_break_aggressive(self, current_block: List[Dict]) -> int:
        """
        Aggressively find the best punctuation break point, prioritizing any punctuation over no punctuation.

        Args:
            current_block: Current block of words

        Returns:
            Index of word with punctuation (or -1 if none found)
        """
        if len(current_block) < 2:
            return -1

        # Define punctuation in priority order
        if self.is_cjk:
            high_priority = ["。", "！", "？"]
            medium_priority = ["；", "："]
            low_priority = ["，", "、"]
        else:
            high_priority = [".", "!", "?"]
            medium_priority = [";", ":"]
            low_priority = [","]

        # First pass: look for high and medium priority punctuation
        for punct_list in [high_priority, medium_priority]:
            for i in range(len(current_block) - 1, 0, -1):
                word_text = current_block[i]['text'].strip()
                for punct in punct_list:
                    if word_text.endswith(punct):
                        # For high/medium priority, be very lenient with requirements
                        text_before = "".join(w['text'] for w in current_block[:i+1]).strip()
                        if len(text_before) >= 3:  # Minimal requirement
                            return i

        # Second pass: look for low priority punctuation (commas) with more strict requirements
        for i in range(len(current_block) - 1, 0, -1):
            word_text = current_block[i]['text'].strip()
            for punct in low_priority:
                if word_text.endswith(punct):
                    text_before = "".join(w['text'] for w in current_block[:i+1]).strip()
                    text_after = "".join(w['text'] for w in current_block[i+1:]).strip()

                    # For commas, ensure reasonable balance but be more lenient
                    if (len(text_before) >= 4 and len(text_after) >= 2 and
                        len(text_before) <= self.max_chars_per_line * 1.8):  # Don't let first part get too long
                        return i

        return -1  # No suitable punctuation found

    def _should_break_for_length_enhanced(self, current_block: List[Dict], current_word: Dict) -> bool:
        """
        Enhanced length-based breaking logic that aggressively prioritizes punctuation marks.

        This method implements a three-stage approach:
        1. Check if we're approaching length limits
        2. Look backwards for recent punctuation marks to break at
        3. Only break if we find good punctuation or if absolutely necessary

        Args:
            current_block: Current block of words
            current_word: The word we're considering adding

        Returns:
            Boolean indicating whether we should break before adding current_word
        """
        if not current_block:
            return False

        # Get current text and projected text with new word
        current_text = "".join(w['text'] for w in current_block).strip()
        text_with_new_word = current_text + current_word['text']

        # Stage 1: If we're not approaching limits, don't break
        if len(text_with_new_word) <= self.max_chars_per_line * 1.2:  # 20% buffer
            return False

        # Stage 2: We're approaching limits, look for recent punctuation breaks
        punctuation_break_index = self._find_recent_punctuation_break(current_block)

        if punctuation_break_index >= 0:
            # Found a good punctuation break point, check if it creates reasonable segments
            text_before_punct = "".join(w['text'] for w in current_block[:punctuation_break_index+1]).strip()
            text_after_punct = "".join(w['text'] for w in current_block[punctuation_break_index+1:]).strip() + current_word['text']

            # If breaking at punctuation creates good segments, do it
            if (len(text_before_punct) >= 8 and
                not self._text_exceeds_two_lines(text_before_punct) and
                not self._text_exceeds_two_lines(text_after_punct)):
                return True

        # Stage 3: Check if we absolutely must break (exceeds two-line limit)
        return self._text_exceeds_two_lines(text_with_new_word)

    def _find_recent_punctuation_break(self, current_block: List[Dict]) -> int:
        """
        Find the most recent good punctuation break point in the current block.
        Searches backwards from the end to find punctuation marks.

        Args:
            current_block: Current block of words

        Returns:
            Index of word with punctuation (or -1 if none found)
        """
        if len(current_block) < 2:
            return -1

        # Define punctuation in priority order
        if self.is_cjk:
            high_priority = ["。", "！", "？"]
            medium_priority = ["；", "："]
            low_priority = ["，", "、"]
        else:
            high_priority = [".", "!", "?"]
            medium_priority = [";", ":"]
            low_priority = [","]

        # Search backwards through ALL words, not just recent ones
        # This is important for finding punctuation that might be further back

        # Try high priority punctuation first
        for punct_list in [high_priority, medium_priority, low_priority]:
            for i in range(len(current_block) - 1, 0, -1):  # Start from end, go to index 1
                word_text = current_block[i]['text'].strip()
                for punct in punct_list:
                    if word_text.endswith(punct):
                        # Found punctuation, check if breaking here creates reasonable segments
                        text_before = "".join(w['text'] for w in current_block[:i+1]).strip()
                        text_after = "".join(w['text'] for w in current_block[i+1:]).strip()

                        # Make sure both segments are reasonable length
                        if (len(text_before) >= 8 and len(text_after) >= 3 and
                            len(text_before) <= self.max_chars_per_line * 2):  # Don't break if first part is too long
                            return i

        return -1  # No suitable punctuation found

    def _should_break_for_length(self, current_block: List[Dict], current_word: Dict) -> bool:
        """
        Enhanced length-based breaking logic that prioritizes punctuation marks.

        This method implements a more sophisticated approach:
        1. First checks if we're approaching length limits
        2. Looks ahead for good punctuation-based breaking points
        3. Only breaks if a good punctuation point is found or if absolutely necessary

        Args:
            current_block: Current block of words
            current_word: The word we're considering adding

        Returns:
            Boolean indicating whether we should break before adding current_word
        """
        if not current_block:
            return False

        # Get current text without the new word
        current_text = "".join(w['text'] for w in current_block).strip()

        # If current text is already too long for two lines, we must break
        if self._text_exceeds_two_lines(current_text):
            return True

        # Check if adding the current word would exceed limits
        text_with_new_word = current_text + current_word['text']

        # If still fits comfortably, don't break
        if len(text_with_new_word) <= self.max_chars_per_line * 1.3:  # Allow some buffer
            return False

        # We're approaching limits, look for good punctuation break points
        # First, check if current word ends with good punctuation
        if self._word_ends_with_good_punctuation(current_word):
            return False  # Don't break before a word that ends with punctuation

        # Look for punctuation break points in the current block
        punctuation_break_found = self._find_punctuation_break_point(current_block)

        # If we found a good punctuation break point, use it
        if punctuation_break_found:
            return True

        # If no punctuation break point and we're getting too long, check if we must break
        return self._text_exceeds_two_lines(text_with_new_word)



    def _text_exceeds_two_lines(self, text: str) -> bool:
        """
        Check if text would exceed two-line subtitle limits.
        """
        if len(text) <= self.max_chars_per_line:
            return False  # Single line, no problem

        # Try to split into two lines
        split_pos = self._find_best_split_position(text, self.max_chars_per_line)
        remaining_text = text[split_pos:].strip()

        # If remaining text is too long for second line, it exceeds limits
        return len(remaining_text) > self.max_chars_per_line

    def _word_ends_with_good_punctuation(self, word: Dict) -> bool:
        """
        Check if a word ends with punctuation that makes a good break point.

        Args:
            word: Word dictionary to check

        Returns:
            Boolean indicating if word ends with good punctuation
        """
        word_text = word['text'].strip()
        if not word_text:
            return False

        if self.is_cjk:
            good_punctuation = ["。", "！", "？", "；", "：", "，", "、"]
        else:
            good_punctuation = [".", "!", "?", ";", ":", ","]

        return any(word_text.endswith(punct) for punct in good_punctuation)

    def _find_punctuation_break_point(self, current_block: List[Dict]) -> bool:
        """
        Look for a good punctuation-based break point in the current block.

        This method searches backwards through the current block to find
        the most recent punctuation mark that would make a good break point.
        Uses a more sophisticated scoring system to find the best break point.

        Args:
            current_block: Current block of words

        Returns:
            Boolean indicating whether a good break point was found
        """
        if len(current_block) <= 2:
            return len(current_block) > 1  # Only break if we have more than one word

        # Define punctuation marks in priority order (higher priority = better break point)
        if self.is_cjk:
            high_priority_punct = ["。", "！", "？"]  # Sentence endings
            medium_priority_punct = ["；", "："]      # Clause endings
            low_priority_punct = ["，", "、"]         # Phrase separators
        else:
            high_priority_punct = [".", "!", "?"]    # Sentence endings
            medium_priority_punct = [";", ":"]       # Clause endings
            low_priority_punct = [","]               # Phrase separators

        # Search for break points in priority order
        for punct_priority, punct_list in enumerate([high_priority_punct, medium_priority_punct, low_priority_punct]):
            # Search backwards through the block for punctuation marks
            for i in range(len(current_block) - 1, max(0, len(current_block) - 8), -1):  # Look at last 8 words max
                word = current_block[i]
                word_text = word['text'].strip()

                # Check if this word ends with punctuation from current priority level
                for punct in punct_list:
                    if word_text.endswith(punct):
                        # Found a punctuation mark, evaluate if it's a good break point
                        text_before = "".join(w['text'] for w in current_block[:i+1]).strip()
                        text_after = "".join(w['text'] for w in current_block[i+1:]).strip()

                        # Quality checks for the break point
                        if self._is_good_break_point(text_before, text_after, punct_priority):
                            return True

        # No good punctuation break point found
        return False

    def _is_good_break_point(self, text_before: str, text_after: str, punct_priority: int) -> bool:
        """
        Evaluate if a potential break point is good quality.

        Args:
            text_before: Text before the break point
            text_after: Text after the break point
            punct_priority: Priority level of the punctuation (0=high, 1=medium, 2=low)

        Returns:
            Boolean indicating if this is a good break point
        """
        # Minimum length requirements (stricter for lower priority punctuation)
        min_before = [8, 10, 12][punct_priority]  # Minimum chars before break
        min_after = [5, 8, 10][punct_priority]    # Minimum chars after break

        # Check minimum lengths
        if len(text_before) < min_before or len(text_after) < min_after:
            return False

        # Check that both parts don't exceed two-line limits
        if self._text_exceeds_two_lines(text_before) or self._text_exceeds_two_lines(text_after):
            return False

        # For high priority punctuation (sentence endings), be more lenient
        if punct_priority == 0:
            return True

        # For medium/low priority, ensure reasonable balance
        length_ratio = len(text_before) / len(text_after) if len(text_after) > 0 else 999
        return 0.3 <= length_ratio <= 3.0  # Not too unbalanced

    def create_srt(self) -> str:
        """
        Creates the full SRT content by grouping words semantically.
        This is the 'Semantic Grouping' stage with enhanced professional rules
        that prioritize punctuation-based breaking.
        """
        if not self.words:
            return ""

        current_block = []

        for i, word in enumerate(self.words):
            # Handle audio events separately
            if word.get("type") == "audio_event":
                # Finalize current block first
                if current_block:
                    self._finalize_and_add_subtitle(current_block)
                    current_block = []
                # Add audio event as its own subtitle
                self._finalize_and_add_subtitle([word])
                continue

            is_last_word = (i == len(self.words) - 1)
            next_word_start = None

            # Get next word start time for timing calculations
            if not is_last_word:
                next_word = self.words[i+1]
                if next_word.get("type") != "audio_event":
                    next_word_start = next_word['start']

            # Before adding the word, check if we should break due to length constraints
            # This is the key improvement: check BEFORE adding the word
            should_break_before_adding = self._should_break_before_adding_word(word, current_block)

            if should_break_before_adding:
                # Find the best break point in the current block (before adding the new word)
                optimal_break_point = self._find_optimal_break_point(current_block)

                if optimal_break_point > 0 and optimal_break_point < len(current_block):
                    # Split the block at the optimal point
                    first_part = current_block[:optimal_break_point]
                    remaining_part = current_block[optimal_break_point:]

                    # Finalize the first part
                    self._finalize_and_add_subtitle(first_part, next_word_start=remaining_part[0]['start'] if remaining_part else word['start'])

                    # Start new block with remaining part + current word
                    current_block = remaining_part + [word]
                else:
                    # No good break point found, finalize current block and start new one
                    self._finalize_and_add_subtitle(current_block, next_word_start=word['start'])
                    current_block = [word]
            else:
                # Add word to current block
                current_block.append(word)

            # Now check if we should break after adding this word (for other reasons)
            should_break_after = self._should_break_at_word(word, current_block, is_last_word, next_word_start)

            if should_break_after:
                # Break at current position (after adding the word)
                self._finalize_and_add_subtitle(current_block, next_word_start=next_word_start)
                current_block = []

        # Handle any remaining words in the current block
        if current_block:
            self._finalize_and_add_subtitle(current_block)

        # Post-processing: optimize generated subtitles
        optimized_content = self._post_process_subtitles()

        return optimized_content

    def _post_process_subtitles(self) -> str:
        """
        后处理优化生成的字幕
        包括：合并过短字幕、调整时间间隔等

        Returns:
            优化后的SRT内容
        """
        if not self.srt_content:
            return ""

        # 解析现有字幕
        subtitles = self._parse_srt_content()

        # 应用优化
        optimized_subtitles = self._merge_short_subtitles(subtitles)
        optimized_subtitles = self._ensure_minimum_gaps(optimized_subtitles)

        # 重新生成SRT内容
        return self._generate_srt_from_subtitles(optimized_subtitles)

    def _parse_srt_content(self) -> List[Dict]:
        """解析SRT内容为字典列表"""
        import re

        subtitles = []
        for entry in self.srt_content:
            lines = entry.strip().split('\n')
            if len(lines) >= 3:
                try:
                    number = int(lines[0])
                    time_line = lines[1]
                    text = '\n'.join(lines[2:])

                    # 解析时间
                    time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', time_line)
                    if time_match:
                        start_str, end_str = time_match.groups()
                        start_time = self._parse_srt_time(start_str)
                        end_time = self._parse_srt_time(end_str)

                        subtitles.append({
                            'number': number,
                            'start': start_time,
                            'end': end_time,
                            'text': text,
                            'duration': end_time - start_time
                        })
                except (ValueError, IndexError):
                    continue

        return subtitles

    def _parse_srt_time(self, time_str: str) -> float:
        """将SRT时间格式转换为秒数"""
        try:
            time_part, ms_part = time_str.split(',')
            h, m, s = map(int, time_part.split(':'))
            ms = int(ms_part)
            return h * 3600 + m * 60 + s + ms / 1000.0
        except:
            return 0.0

    def _merge_short_subtitles(self, subtitles: List[Dict]) -> List[Dict]:
        """合并过短的字幕"""
        if not subtitles:
            return subtitles

        merged = []
        i = 0

        while i < len(subtitles):
            current = subtitles[i]

            # 检查是否需要与下一个字幕合并
            if (i + 1 < len(subtitles) and
                self._should_merge_short_subtitles(
                    current['text'],
                    subtitles[i + 1]['text'],
                    current['end'],
                    subtitles[i + 1]['start']
                )):

                # 合并字幕
                next_subtitle = subtitles[i + 1]
                merged_subtitle = {
                    'number': current['number'],
                    'start': current['start'],
                    'end': next_subtitle['end'],
                    'text': current['text'] + ' ' + next_subtitle['text'],
                    'duration': next_subtitle['end'] - current['start']
                }
                merged.append(merged_subtitle)
                i += 2  # 跳过下一个字幕
            else:
                merged.append(current)
                i += 1

        return merged

    def _ensure_minimum_gaps(self, subtitles: List[Dict]) -> List[Dict]:
        """确保字幕间的最小间隔"""
        if len(subtitles) <= 1:
            return subtitles

        adjusted = []
        tolerance = 1e-3  # 1毫秒容差

        for i, subtitle in enumerate(subtitles):
            adjusted_subtitle = subtitle.copy()

            # 检查与下一个字幕的间隔
            if i + 1 < len(subtitles):
                next_subtitle = subtitles[i + 1]
                gap = next_subtitle['start'] - subtitle['end']

                if gap < (self.min_subtitle_gap - tolerance):
                    # 调整时间以确保最小间隔
                    adjustment = (self.min_subtitle_gap - gap) / 2
                    adjusted_subtitle['end'] = max(
                        adjusted_subtitle['start'] + self.min_subtitle_duration,
                        adjusted_subtitle['end'] - adjustment
                    )

            adjusted.append(adjusted_subtitle)

        return adjusted

    def _generate_srt_from_subtitles(self, subtitles: List[Dict]) -> str:
        """从字幕列表生成SRT内容"""
        srt_lines = []

        for i, subtitle in enumerate(subtitles, 1):
            # 重新编号
            subtitle['number'] = i

            # 格式化时间
            start_time_str = format_srt_time(subtitle['start'])
            end_time_str = format_srt_time(subtitle['end'])

            # 生成字幕条目
            entry = f"{i}\n{start_time_str} --> {end_time_str}\n{subtitle['text']}\n"
            srt_lines.append(entry)

        return "\n".join(srt_lines)

    def _find_optimal_break_point(self, current_block: List[Dict]) -> int:
        """
        Find the optimal position to break within the current block.
        Enhanced to aggressively prioritize punctuation marks.

        Args:
            current_block: Current block of words

        Returns:
            Index where to break (0 means no break, len(block) means break at end)
        """
        if len(current_block) <= 1:
            return len(current_block)  # Break at end if only one word

        # Use the aggressive punctuation search first
        aggressive_punct_index = self._find_best_punctuation_break_aggressive(current_block)

        if aggressive_punct_index >= 0:
            # Found punctuation with aggressive search, use it
            break_position = aggressive_punct_index + 1

            if break_position < len(current_block):  # Make sure we're not breaking at the very end
                text_before = "".join(w['text'] for w in current_block[:break_position]).strip()
                text_after = "".join(w['text'] for w in current_block[break_position:]).strip()

                # More lenient requirements for punctuation breaks
                if (len(text_before) >= 5 and len(text_after) >= 3 and
                    not self._text_exceeds_two_lines(text_before) and
                    not self._text_exceeds_two_lines(text_after)):
                    return break_position

        # Fallback: try the original punctuation search
        recent_punct_index = self._find_recent_punctuation_break(current_block)

        if recent_punct_index >= 0:
            break_position = recent_punct_index + 1

            if break_position < len(current_block):
                text_before = "".join(w['text'] for w in current_block[:break_position]).strip()
                text_after = "".join(w['text'] for w in current_block[break_position:]).strip()

                if (len(text_before) >= 5 and len(text_after) >= 3 and
                    not self._text_exceeds_two_lines(text_before) and
                    not self._text_exceeds_two_lines(text_after)):
                    return break_position

        # If no punctuation breaks work, check if we really need to break
        current_text = "".join(w['text'] for w in current_block).strip()

        # Only break if text is getting too long
        if not self._text_exceeds_two_lines(current_text) and len(current_text) <= self.max_chars_per_line * 1.2:
            return len(current_block)  # Don't break if not necessary

        # Last resort: use scoring system but with lower threshold
        if self.is_cjk:
            punctuation_scores = {
                "。": 100, "！": 95, "？": 95,  # Sentence endings
                "；": 80, "：": 75,             # Clause endings
                "，": 60, "、": 55              # Phrase separators
            }
        else:
            punctuation_scores = {
                ".": 100, "!": 95, "?": 95,     # Sentence endings
                ";": 80, ":": 75,               # Clause endings
                ",": 60                         # Phrase separators
            }

        best_break_point = 0
        best_score = 0

        # Search through the block for the best break point
        for i in range(1, len(current_block)):
            word = current_block[i-1]  # Look at the word before position i
            word_text = word['text'].strip()

            # Calculate score for breaking at position i (after word i-1)
            score = self._calculate_break_point_score(current_block, i, word_text, punctuation_scores)

            if score > best_score:
                best_score = score
                best_break_point = i

        # Return the best break point found, with lower threshold to prefer any punctuation
        return best_break_point if best_score > 10 else len(current_block)

    def _calculate_break_point_score(self, current_block: List[Dict], break_position: int,
                                   word_text: str, punctuation_scores: Dict[str, int]) -> int:
        """
        Calculate a score for a potential break point.
        Higher scores indicate better break points.

        Args:
            current_block: Current block of words
            break_position: Position where we're considering breaking
            word_text: Text of the word before the break position
            punctuation_scores: Dictionary mapping punctuation to scores

        Returns:
            Score for this break point (0-100+)
        """
        if break_position <= 0 or break_position >= len(current_block):
            return 0

        # Get text before and after the break
        text_before = "".join(w['text'] for w in current_block[:break_position]).strip()
        text_after = "".join(w['text'] for w in current_block[break_position:]).strip()

        # Base score starts at 0
        score = 0

        # Check for punctuation at the end of the word before break
        for punct, punct_score in punctuation_scores.items():
            if word_text.endswith(punct):
                score += punct_score
                break  # Only count the highest priority punctuation

        # Length balance bonus (prefer more balanced splits)
        if len(text_before) > 0 and len(text_after) > 0:
            length_ratio = min(len(text_before), len(text_after)) / max(len(text_before), len(text_after))
            score += int(length_ratio * 20)  # Up to 20 points for balance

        # Minimum length penalty (avoid too short segments)
        min_length = 8
        if len(text_before) < min_length:
            score -= (min_length - len(text_before)) * 5
        if len(text_after) < min_length:
            score -= (min_length - len(text_after)) * 5

        # Two-line limit penalty (heavily penalize if either part exceeds two lines)
        if self._text_exceeds_two_lines(text_before):
            score -= 50
        if self._text_exceeds_two_lines(text_after):
            score -= 50

        # Position preference (slightly prefer breaks closer to the middle)
        middle_position = len(current_block) / 2
        position_distance = abs(break_position - middle_position) / len(current_block)
        score += int((1 - position_distance) * 10)  # Up to 10 points for good position

        return max(0, score)  # Ensure non-negative score

    def _find_fallback_break_point(self, current_block: List[Dict]) -> int:
        """
        Find a fallback break point when no good punctuation-based break is available.
        This is used as a last resort to prevent overly long subtitles.

        Args:
            current_block: Current block of words

        Returns:
            Index where to break
        """
        if len(current_block) <= 2:
            return len(current_block)

        # Try to break roughly in the middle, but prefer earlier break points
        target_position = len(current_block) // 2

        # Look for a reasonable break point around the middle
        for offset in range(min(target_position, len(current_block) - target_position)):
            # Try positions around the middle
            for pos in [target_position - offset, target_position + offset]:
                if 1 < pos < len(current_block) - 1:  # Don't break too close to edges
                    text_before = "".join(w['text'] for w in current_block[:pos]).strip()
                    text_after = "".join(w['text'] for w in current_block[pos:]).strip()

                    # Check if both parts are reasonable
                    if (len(text_before) >= 8 and len(text_after) >= 5 and
                        not self._text_exceeds_two_lines(text_before) and
                        not self._text_exceeds_two_lines(text_after)):
                        return pos

        # If all else fails, break at 2/3 position to avoid overly long first part
        return max(2, len(current_block) * 2 // 3)

def create_srt_from_json(json_data: Dict, pause_threshold: float = None, max_subtitle_duration: float = None,
                        subtitle_settings: Dict = None) -> str:
    """
    Processes transcription JSON data to create a professional SRT file.

    Args:
        json_data: Transcription data from ElevenLabs or similar service
        pause_threshold: Minimum pause duration to break subtitles (default: 0.7s)
        max_subtitle_duration: Maximum duration for a single subtitle (default: 7.0s)
        subtitle_settings: Dictionary containing advanced subtitle settings

    Returns:
        Professional SRT content following industry standards
    """
    processor = SrtProcessor(json_data, pause_threshold, max_subtitle_duration, subtitle_settings)
    return processor.create_srt()

if __name__ == '__main__':
    import os
    import json

    print("--- Running srt_processor.py in batch test mode ---")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sample_dir = os.path.join(script_dir, 'sample')

    if not os.path.isdir(sample_dir):
        print(f"Error: Sample directory not found at '{sample_dir}'")
    else:
        print(f"Scanning for .json files in: {sample_dir}\n")
        json_files_found = 0
        for filename in os.listdir(sample_dir):
            if filename.lower().endswith('.json'):
                json_files_found += 1
                json_path = os.path.join(sample_dir, filename)
                srt_path = os.path.splitext(json_path)[0] + '.srt'
                
                print(f"Processing '{filename}'...")

                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        test_json_data = json.load(f)
                    
                    # Use optimized default parameters for professional subtitle generation
                    generated_srt = create_srt_from_json(test_json_data)  # Uses professional defaults
                    
                    with open(srt_path, 'w', encoding='utf-8') as f_out:
                        f_out.write(generated_srt)
                    
                    print(f"  -> Successfully generated and saved to '{os.path.basename(srt_path)}'\n")

                except Exception as e:
                    print(f"  -> Error processing file '{filename}': {e}\n")
        
        if json_files_found == 0:
            print("No .json files found in the sample directory.")
        else:
            print(f"--- Batch processing finished. Processed {json_files_found} file(s). ---")