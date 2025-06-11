import datetime
from typing import Dict

# --- Subtitle Generation Rules ---
MAX_LINES_PER_SUBTITLE = 2
MAX_CPS = 14
MIN_SUBTITLE_DURATION = 1.0
MAX_SUBTITLE_DURATION = 7.0
PAUSE_THRESHOLD = 0.7

def format_srt_time(seconds: float) -> str:
    """Formats seconds into SRT time format HH:MM:SS,ms."""
    delta = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = int(delta.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

class SrtProcessor:
    """
    A class to process word-level transcription data into professional SRT subtitles.
    """
    def __init__(self, json_data: Dict, max_chars_per_line: int):
        self.srt_content = []
        self.line_number = 1
        self.max_chars_per_line = max_chars_per_line
        self._preprocess_words(json_data)

    def _preprocess_words(self, json_data: Dict):
        """
        Pre-processes the word list to merge standalone punctuation onto the previous word.
        This fixes issues where pauses cause punctuation to be orphaned.
        """
        raw_words = [w for w in json_data.get("words", []) if w.get("type") != "spacing"]
        self.words = []
        for i, word_info in enumerate(raw_words):
            # Check for standalone CJK punctuation
            is_standalone_punctuation = len(word_info['text']) == 1 and word_info['text'] in "。？！」「、"
            
            # If it is, and if there's a previous word, merge it
            if is_standalone_punctuation and self.words:
                prev_word = self.words[-1]
                
                # Ensure the previous word isn't also punctuation or an event
                if prev_word['text'] and prev_word['text'][-1] not in "。？！」「、" and prev_word.get("type") == "word":
                    # Append text and update the end time
                    prev_word['text'] += word_info['text']
                    prev_word['end'] = word_info['end']
                    continue # Skip appending the standalone punctuation

            self.words.append(word_info)

    def _split_text_into_lines(self, text: str) -> str:
        """Intelligently splits a single line of text into two if it exceeds max length."""
        if len(text) <= self.max_chars_per_line:
            return text

        best_split_pos = -1
        # Try to find the last punctuation mark before the max length limit
        for i in range(min(len(text) - 1, self.max_chars_per_line), 0, -1):
            if text[i] in "、。「」？！":
                best_split_pos = i + 1
                break
        
        if best_split_pos != -1:
            line1 = text[:best_split_pos]
            line2 = text[best_split_pos:]
            # If the second line is still too long, this simple split is not enough.
            if len(line2) > self.max_chars_per_line:
                 return text[:self.max_chars_per_line] + "\n" + text[self.max_chars_per_line:]
            return f"{line1}\n{line2}"

        # If no punctuation, do a hard split at the max length
        return text[:self.max_chars_per_line] + "\n" + text[self.max_chars_per_line:]

    def _finalize_and_add_subtitle(self, words_in_block, next_word_start=None):
        if not words_in_block: return
        start_time = words_in_block[0]['start']
        end_time = words_in_block[-1]['end']
        text = "".join(w['text'] for w in words_in_block)
        duration = end_time - start_time
        if duration < MIN_SUBTITLE_DURATION:
            end_time = start_time + MIN_SUBTITLE_DURATION
        effective_duration = end_time - start_time
        cps = len(text) / effective_duration if effective_duration > 0 else 999
        if cps > MAX_CPS:
            required_duration = len(text) / MAX_CPS
            end_time = start_time + required_duration
        if next_word_start and end_time >= next_word_start:
            end_time = next_word_start - 0.001
        final_text = self._split_text_into_lines(text)
        self.srt_content.append(f"{self.line_number}\n{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n{final_text}\n")
        self.line_number += 1

    def create_srt(self) -> str:
        if not self.words: return ""
        current_block = []
        for i, word in enumerate(self.words):
            if word.get("type") == "audio_event":
                self._finalize_and_add_subtitle(current_block, next_word_start=word.get('start'))
                current_block = []
                self.srt_content.append(f"{self.line_number}\n{format_srt_time(word['start'])} --> {format_srt_time(word['end'])}\n{word['text']}\n")
                self.line_number += 1
                continue
            current_block.append(word)
            text_so_far = "".join(w['text'] for w in current_block)
            duration_so_far = word['end'] - current_block[0]['start']
            is_last_word = (i == len(self.words) - 1)
            hard_break = word['text'].endswith(('。', '？', '！'))
            long_pause, next_start_time = False, None
            if not is_last_word:
                next_word = self.words[i+1]
                if next_word.get("type") != "audio_event":
                    next_start_time = next_word['start']
                    if (next_start_time - word['end']) > PAUSE_THRESHOLD:
                        long_pause = True
            duration_exceeded = duration_so_far > MAX_SUBTITLE_DURATION
            length_exceeded = len(text_so_far) > (self.max_chars_per_line * MAX_LINES_PER_SUBTITLE)
            if is_last_word or hard_break or long_pause or duration_exceeded or length_exceeded:
                self._finalize_and_add_subtitle(current_block, next_word_start=next_start_time)
                current_block = []
        return "\n".join(self.srt_content)

def create_srt_from_json(json_data: Dict, max_chars_per_line: int) -> str:
    """
    Processes transcription JSON data to create a professional SRT file.
    """
    processor = SrtProcessor(json_data, max_chars_per_line)
    return processor.create_srt()

if __name__ == '__main__':
    # This block allows for direct testing of the SRT processor.
    # It scans the 'sample' directory, processes all .json files,
    # and saves the output as .srt files in the same directory.
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
                    
                    test_max_chars = 18
                    generated_srt = create_srt_from_json(test_json_data, test_max_chars)
                    
                    with open(srt_path, 'w', encoding='utf-8') as f_out:
                        f_out.write(generated_srt)
                    
                    print(f"  -> Successfully generated and saved to '{os.path.basename(srt_path)}'\n")

                except Exception as e:
                    print(f"  -> Error processing file '{filename}': {e}\n")
        
        if json_files_found == 0:
            print("No .json files found in the sample directory.")
        else:
            print(f"--- Batch processing finished. Processed {json_files_found} file(s). ---")