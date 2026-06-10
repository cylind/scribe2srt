#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
60dB STT 响应规整器（normalize_60db_response）的单元测试。

重点验证 60dB 响应被正确转换为本项目内部（ElevenLabs 风格）的转录结构，
从而保证两个 provider 在下游 SRT 引擎中的行为一致：
- word -> text、language -> language_code 的字段映射
- 非 CJK 语言为每个词补尾随空格（弥补 60dB 没有 spacing 条目）
- CJK 语言不补空格
- 无 words 时从 segments 展开
- 缺少时间戳的词被丢弃
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.client import normalize_60db_response


def test_field_mapping_and_types():
    resp = {
        "language": "en",
        "text": "Hello world.",
        "words": [
            {"word": "Hello", "start": 0.0, "end": 0.4},
            {"word": "world.", "start": 0.4, "end": 0.9},
        ],
    }
    norm = normalize_60db_response(resp)
    assert norm["language_code"] == "en"
    assert norm["text"] == "Hello world."
    assert all(w["type"] == "word" for w in norm["words"])
    assert all(isinstance(w["start"], float) and isinstance(w["end"], float) for w in norm["words"])


def test_latin_words_get_trailing_space():
    resp = {
        "language": "en",
        "text": "Hello world",
        "words": [
            {"word": "Hello", "start": 0.0, "end": 0.4},
            {"word": "world", "start": 0.4, "end": 0.9},
        ],
    }
    norm = normalize_60db_response(resp)
    # 非 CJK：每个词都应以空格结尾，拼接后才不会粘连成 "Helloworld"
    assert norm["words"][0]["text"] == "Hello "
    assert norm["words"][1]["text"] == "world "
    assert "".join(w["text"] for w in norm["words"]).strip() == "Hello world"


def test_cjk_words_have_no_trailing_space():
    resp = {
        "language": "zh",
        "text": "你好世界",
        "words": [
            {"word": "你好", "start": 0.0, "end": 0.8},
            {"word": "世界", "start": 0.8, "end": 1.6},
        ],
    }
    norm = normalize_60db_response(resp)
    assert norm["words"][0]["text"] == "你好"
    assert norm["words"][1]["text"] == "世界"
    assert not any(w["text"].endswith(" ") for w in norm["words"])


def test_words_flattened_from_segments_when_no_flat_words():
    resp = {
        "language": "ja",
        "text": "テスト",
        "segments": [
            {"start": 0.0, "end": 1.0, "words": [{"word": "こん", "start": 0.0, "end": 0.5}]},
            {"start": 1.0, "end": 2.0, "words": [{"word": "にちは", "start": 1.0, "end": 1.6}]},
        ],
    }
    norm = normalize_60db_response(resp)
    assert len(norm["words"]) == 2
    assert norm["words"][0]["start"] == 0.0
    assert norm["words"][1]["start"] == 1.0


def test_words_without_timestamps_are_dropped():
    resp = {
        "language": "en",
        "text": "ok",
        "words": [
            {"word": "no_timestamp"},
            {"word": "ok", "start": 0.1, "end": 0.5},
        ],
    }
    norm = normalize_60db_response(resp)
    assert len(norm["words"]) == 1
    assert norm["words"][0]["text"] == "ok "


def test_missing_language_defaults_to_auto():
    resp = {"text": "", "words": []}
    norm = normalize_60db_response(resp)
    assert norm["language_code"] == "auto"
    assert norm["words"] == []


def test_speaker_field_is_preserved():
    resp = {
        "language": "en",
        "text": "hi",
        "words": [{"word": "hi", "start": 0.0, "end": 0.3, "speaker": "SPEAKER_00"}],
    }
    norm = normalize_60db_response(resp)
    assert norm["words"][0]["speaker_id"] == "SPEAKER_00"


def _run_all():
    """无 pytest 时也可直接运行：python tests/test_60db_normalizer.py"""
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"  PASS: {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed.")


if __name__ == "__main__":
    _run_all()
