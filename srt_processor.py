import datetime
from typing import Dict

from core.config import (
    MAX_CPS, MIN_SUBTITLE_DURATION, MAX_SUBTITLE_DURATION, PAUSE_THRESHOLD
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
    """
    def __init__(self, json_data: Dict, pause_threshold: float, max_subtitle_duration: float):
        self.srt_content = []
        self.line_number = 1
        self.language = json_data.get("language_code", "eng")[:3] # e.g., "eng"
        self.max_chars_per_line = self._get_max_chars_for_language()
        self.pause_threshold = pause_threshold
        self.max_subtitle_duration = max_subtitle_duration
        self._preprocess_words(json_data)

    def _get_max_chars_for_language(self) -> int:
        """Returns the recommended max characters per line based on language."""
        if self.language in ["zho", "jpn", "kor"]: # Chinese, Japanese, Korean
            return 18
        else: # Latin-based languages (English, Spanish, etc.)
            return 42

    def _preprocess_words(self, json_data: Dict):
        """
        Pre-processes the word list to handle language-specific quirks,
        such as merging standalone CJK punctuation.
        """
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

    def _split_text_into_lines(self, text: str) -> str:
        """
        Intelligently splits a text block into a maximum of two lines,
        respecting the max_chars_per_line limit.
        """
        if len(text) <= self.max_chars_per_line:
            return text
        
        lines = []
        remaining_text = text.strip()
        split_chars = "。？！、,." + " "

        if len(remaining_text) > self.max_chars_per_line:
            best_split_pos = -1
            search_range = self.max_chars_per_line + 1
            try:
                best_split_pos = max(remaining_text.rfind(char, 0, search_range) for char in split_chars)
            except ValueError:
                best_split_pos = -1

            if best_split_pos <= 0:
                best_split_pos = self.max_chars_per_line

            split_at_char = remaining_text[best_split_pos]
            if split_at_char == ' ':
                line = remaining_text[:best_split_pos]
                remaining_text = remaining_text[best_split_pos+1:]
            else:
                line = remaining_text[:best_split_pos+1]
                remaining_text = remaining_text[best_split_pos+1:]
            
            lines.append(line.strip())

        if remaining_text:
            lines.append(remaining_text.strip())
            
        return "\n".join(lines)

    def _finalize_and_add_subtitle(self, words_in_block, next_word_start=None):
        """
        Takes a block of words, formats them into a subtitle, and adds it to the list.
        This is the 'Visual Formatting' stage.
        """
        if not words_in_block: return

        text = "".join(w['text'] for w in words_in_block).strip()
        if not text: return # Fix for empty subtitle bug

        start_time = words_in_block[0]['start']
        end_time = words_in_block[-1]['end']
        
        # Adjust timing for readability
        duration = end_time - start_time
        if duration < MIN_SUBTITLE_DURATION:
            end_time = start_time + MIN_SUBTITLE_DURATION
        
        effective_duration = end_time - start_time
        cps = len(text) / effective_duration if effective_duration > 0 else 999
        if cps > MAX_CPS:
            end_time = start_time + (len(text) / MAX_CPS)

        # Prevent overlap with the next subtitle
        if next_word_start and end_time >= next_word_start:
            end_time = next_word_start - 0.001
        
        # Ensure start_time is not after end_time
        if start_time >= end_time:
            end_time = start_time + MIN_SUBTITLE_DURATION

        final_text = self._split_text_into_lines(text)
        self.srt_content.append(f"{self.line_number}\n{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n{final_text}\n")
        self.line_number += 1

    def create_srt(self) -> str:
        """
        Creates the full SRT content by grouping words semantically.
        This is the 'Semantic Grouping' stage.
        """
        if not self.words: return ""
        
        current_block = []
        hard_break_chars = ".?!。？！"

        for i, word in enumerate(self.words):
            if word.get("type") == "audio_event":
                self._finalize_and_add_subtitle(current_block)
                current_block = []
                self._finalize_and_add_subtitle([word]) # Handle event as its own block
                continue

            current_block.append(word)
            
            is_last_word = (i == len(self.words) - 1)
            
            # Check for hard break condition
            ends_with_hard_break = word['text'] and word['text'][-1] in hard_break_chars
            
            # Check for long pause condition
            long_pause = False
            next_start_time = None
            if not is_last_word:
                next_word = self.words[i+1]
                if next_word.get("type") != "audio_event":
                    next_start_time = next_word['start']
                    if (next_start_time - word['end']) > self.pause_threshold:
                        long_pause = True
            
            # Check for duration limit
            duration_so_far = word['end'] - current_block[0]['start']
            duration_exceeded = duration_so_far > self.max_subtitle_duration

            if is_last_word or ends_with_hard_break or long_pause or duration_exceeded:
                self._finalize_and_add_subtitle(current_block, next_word_start=next_start_time)
                current_block = []
                
        return "\n".join(self.srt_content)

def create_srt_from_json(json_data: Dict, pause_threshold: float, max_subtitle_duration: float) -> str:
    """
    Processes transcription JSON data to create a professional SRT file.
    The max_chars_per_line is now determined automatically based on language.
    """
    processor = SrtProcessor(json_data, pause_threshold, max_subtitle_duration)
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
                    
                    # The max_chars_per_line argument is no longer needed.
                    generated_srt = create_srt_from_json(test_json_data) # Uses default params in test mode
                    
                    with open(srt_path, 'w', encoding='utf-8') as f_out:
                        f_out.write(generated_srt)
                    
                    print(f"  -> Successfully generated and saved to '{os.path.basename(srt_path)}'\n")

                except Exception as e:
                    print(f"  -> Error processing file '{filename}': {e}\n")
        
        if json_files_found == 0:
            print("No .json files found in the sample directory.")
        else:
            print(f"--- Batch processing finished. Processed {json_files_found} file(s). ---")