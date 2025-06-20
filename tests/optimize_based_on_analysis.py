#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
增强版字幕质量分析脚本
不仅测试标点符号分割，还全面测试字幕规则合规性
包括：时长、间隔、字符数、CPS等专业标准
"""

import json
import os
import re
import sys
from typing import Dict, List, Tuple, Optional
from pathlib import Path

# 添加父目录到路径以导入配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import (
    MIN_SUBTITLE_DURATION, MAX_SUBTITLE_DURATION, MIN_SUBTITLE_GAP,
    CPS_SETTINGS, CPL_SETTINGS, MAX_LINES_PER_SUBTITLE
)

class SubtitleQualityAnalyzer:
    """字幕质量分析器 - 独立版本"""

    def parse_srt_file(self, srt_path: str) -> List[Dict]:
        """解析SRT文件"""
        subtitles = []
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            # 分割字幕块
            blocks = re.split(r'\n\s*\n', content)

            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    try:
                        number = int(lines[0])
                        time = lines[1]
                        text = '\n'.join(lines[2:])

                        subtitles.append({
                            'number': number,
                            'time': time,
                            'text': text
                        })
                    except (ValueError, IndexError):
                        continue
        except Exception as e:
            print(f"解析SRT文件时出错: {e}")

        return subtitles

    def is_punctuation_ending(self, text: str) -> bool:
        """检查文本是否以标点符号结尾 - 恢复到原始的严格标点符号检测"""
        if not text:
            return False

        # 定义标准标点符号（不包括语气词和常见结尾词）
        punctuation_chars = {
            # 英文标点
            '.', '!', '?', ',', ';', ':', '"', "'", ')', ']', '}',
            # 中文标点
            '。', '！', '？', '，', '；', '：', '"', '"', ''', ''', '）', '】', '』', '》',
            # 日文标点
            '。', '！', '？', '、', '」', '』', '》', '）'
        }

        last_char = text.strip()[-1] if text.strip() else ''
        return last_char in punctuation_chars

    def get_last_character(self, text: str) -> str:
        """获取文本的最后一个字符"""
        return text.strip()[-1] if text.strip() else ''

class EnhancedSubtitleAnalyzer:
    """增强版字幕分析器，测试所有字幕规则"""

    def __init__(self):
        self.quality_analyzer = SubtitleQualityAnalyzer()
        # 字幕规则配置
        self.rules = {
            'min_duration': MIN_SUBTITLE_DURATION,
            'max_duration': MAX_SUBTITLE_DURATION,
            'min_gap': MIN_SUBTITLE_GAP,
            'max_lines': MAX_LINES_PER_SUBTITLE,
            'cjk_cps': CPS_SETTINGS["cjk"],
            'latin_cps': CPS_SETTINGS["latin"],
            'cjk_cpl': CPL_SETTINGS["cjk"],
            'latin_cpl': CPL_SETTINGS["latin"]
        }

    def parse_srt_time(self, time_str: str) -> float:
        """将SRT时间格式转换为秒数"""
        try:
            # 格式: HH:MM:SS,mmm
            time_part, ms_part = time_str.split(',')
            h, m, s = map(int, time_part.split(':'))
            ms = int(ms_part)
            return h * 3600 + m * 60 + s + ms / 1000.0
        except:
            return 0.0

    def detect_language(self, text: str) -> str:
        """简单的语言检测"""
        # 检测中日韩字符
        cjk_chars = len(re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', text))
        total_chars = len(re.sub(r'\s', '', text))

        if total_chars == 0:
            return 'unknown'

        cjk_ratio = cjk_chars / total_chars
        return 'cjk' if cjk_ratio > 0.3 else 'latin'

    def calculate_cps(self, text: str, duration: float) -> float:
        """计算字符每秒速度"""
        if duration <= 0:
            return 0.0
        # 去除空白字符计算实际字符数
        char_count = len(re.sub(r'\s', '', text))
        return char_count / duration

    def analyze_subtitle_rules(self, srt_path: str) -> Dict:
        """分析单个字幕文件的规则合规性"""
        subtitles = self.quality_analyzer.parse_srt_file(srt_path)

        if not subtitles:
            return {'error': 'No subtitles found'}

        violations = {
            'duration_too_short': [],
            'duration_too_long': [],
            'gap_too_small': [],
            'cps_too_high': [],
            'cpl_exceeded': [],
            'too_many_lines': [],
            'punctuation_issues': []
        }

        stats = {
            'total_subtitles': len(subtitles),
            'avg_duration': 0.0,
            'avg_gap': 0.0,
            'avg_cps': 0.0,
            'language_distribution': {'cjk': 0, 'latin': 0, 'unknown': 0}
        }

        total_duration = 0.0
        total_gaps = 0.0
        gap_count = 0
        total_cps = 0.0

        for i, subtitle in enumerate(subtitles):
            # 解析时间
            time_parts = subtitle['time'].split(' --> ')
            if len(time_parts) != 2:
                continue

            start_time = self.parse_srt_time(time_parts[0])
            end_time = self.parse_srt_time(time_parts[1])
            duration = end_time - start_time

            total_duration += duration

            # 检测语言
            language = self.detect_language(subtitle['text'])
            stats['language_distribution'][language] += 1

            # 1. 检查字幕时长（使用容差处理浮点数精度问题）
            tolerance = 1e-3  # 1毫秒的容差，更实用的精度
            if duration < (self.rules['min_duration'] - tolerance):
                violations['duration_too_short'].append({
                    'number': subtitle['number'],
                    'duration': duration,
                    'text': subtitle['text'][:50] + '...' if len(subtitle['text']) > 50 else subtitle['text'],
                    'time': subtitle['time']
                })

            if duration > (self.rules['max_duration'] + tolerance):
                violations['duration_too_long'].append({
                    'number': subtitle['number'],
                    'duration': duration,
                    'text': subtitle['text'][:50] + '...' if len(subtitle['text']) > 50 else subtitle['text'],
                    'time': subtitle['time']
                })

            # 2. 检查字幕间隔
            if i < len(subtitles) - 1:
                next_subtitle = subtitles[i + 1]
                next_time_parts = next_subtitle['time'].split(' --> ')
                if len(next_time_parts) == 2:
                    next_start = self.parse_srt_time(next_time_parts[0])
                    gap = next_start - end_time
                    total_gaps += gap
                    gap_count += 1

                    # 使用容差来处理浮点数精度问题
                    tolerance = 1e-3  # 1毫秒的容差，更实用的精度
                    if gap < (self.rules['min_gap'] - tolerance) and gap >= 0:  # 负值表示重叠，单独处理
                        violations['gap_too_small'].append({
                            'number': subtitle['number'],
                            'next_number': next_subtitle['number'],
                            'gap': gap,
                            'text': subtitle['text'][:30] + '...' if len(subtitle['text']) > 30 else subtitle['text']
                        })

            # 3. 检查CPS（字符每秒）
            cps = self.calculate_cps(subtitle['text'], duration)
            total_cps += cps

            max_cps = self.rules['cjk_cps'] if language == 'cjk' else self.rules['latin_cps']
            if cps > max_cps:
                violations['cps_too_high'].append({
                    'number': subtitle['number'],
                    'cps': cps,
                    'max_cps': max_cps,
                    'language': language,
                    'text': subtitle['text'][:50] + '...' if len(subtitle['text']) > 50 else subtitle['text']
                })

            # 4. 检查每行字符数（CPL）
            lines = subtitle['text'].split('\n')
            if len(lines) > self.rules['max_lines']:
                violations['too_many_lines'].append({
                    'number': subtitle['number'],
                    'lines': len(lines),
                    'text': subtitle['text']
                })

            max_cpl = self.rules['cjk_cpl'] if language == 'cjk' else self.rules['latin_cpl']
            for line_num, line in enumerate(lines, 1):
                line_length = len(line.strip())
                if line_length > max_cpl:
                    violations['cpl_exceeded'].append({
                        'number': subtitle['number'],
                        'line_number': line_num,
                        'length': line_length,
                        'max_length': max_cpl,
                        'language': language,
                        'line_text': line.strip()
                    })

            # 5. 检查标点符号问题
            if not self.quality_analyzer.is_punctuation_ending(subtitle['text']):
                violations['punctuation_issues'].append({
                    'number': subtitle['number'],
                    'text': subtitle['text'],
                    'last_char': self.quality_analyzer.get_last_character(subtitle['text'])
                })

        # 计算统计数据
        stats['avg_duration'] = total_duration / len(subtitles) if subtitles else 0
        stats['avg_gap'] = total_gaps / gap_count if gap_count > 0 else 0
        stats['avg_cps'] = total_cps / len(subtitles) if subtitles else 0

        return {
            'file': os.path.basename(srt_path),
            'stats': stats,
            'violations': violations,
            'rules': self.rules
        }

    def analyze_directory_rules(self, directory: str) -> Dict:
        """分析目录中所有SRT文件的规则合规性"""
        srt_files = list(Path(directory).glob('*.srt'))

        if not srt_files:
            return {'error': f'No SRT files found in {directory}'}

        file_results = []
        overall_stats = {
            'total_files': len(srt_files),
            'total_subtitles': 0,
            'total_violations': 0,
            'violation_types': {
                'duration_too_short': 0,
                'duration_too_long': 0,
                'gap_too_small': 0,
                'cps_too_high': 0,
                'cpl_exceeded': 0,
                'too_many_lines': 0,
                'punctuation_issues': 0
            },
            'avg_duration': 0.0,
            'avg_gap': 0.0,
            'avg_cps': 0.0
        }

        total_duration = 0.0
        total_gap = 0.0
        total_cps = 0.0

        for i, srt_file in enumerate(srt_files, 1):
            print(f"正在分析文件 {i}/{len(srt_files)}: {srt_file.name}")
            result = self.analyze_subtitle_rules(str(srt_file))
            if 'error' not in result:
                file_results.append(result)

                # 累计统计
                stats = result['stats']
                overall_stats['total_subtitles'] += stats['total_subtitles']
                total_duration += stats['avg_duration'] * stats['total_subtitles']
                total_gap += stats['avg_gap']
                total_cps += stats['avg_cps'] * stats['total_subtitles']

                # 累计违规数量
                for violation_type, violations in result['violations'].items():
                    count = len(violations)
                    overall_stats['violation_types'][violation_type] += count
                    overall_stats['total_violations'] += count

        # 计算平均值
        if overall_stats['total_subtitles'] > 0:
            overall_stats['avg_duration'] = total_duration / overall_stats['total_subtitles']
            overall_stats['avg_cps'] = total_cps / overall_stats['total_subtitles']

        if len(file_results) > 0:
            overall_stats['avg_gap'] = total_gap / len(file_results)

        return {
            'directory': directory,
            'overall_stats': overall_stats,
            'file_results': file_results,
            'rules': self.rules
        }

    def print_rules_analysis_report(self, analysis_result: Dict):
        """打印规则分析报告"""
        if 'error' in analysis_result:
            print(f"错误: {analysis_result['error']}")
            return

        print("=" * 80)
        print("字幕规则合规性分析报告")
        print("=" * 80)

        overall = analysis_result['overall_stats']
        rules = analysis_result['rules']

        print(f"分析目录: {analysis_result['directory']}")
        print(f"文件总数: {overall['total_files']}")
        print(f"字幕总数: {overall['total_subtitles']}")
        print(f"违规总数: {overall['total_violations']}")
        print(f"合规率: {((overall['total_subtitles'] - overall['total_violations']) / overall['total_subtitles'] * 100):.2f}%" if overall['total_subtitles'] > 0 else "N/A")
        print()

        # 规则配置
        print("当前规则配置:")
        print("-" * 40)
        print(f"最短时长: {rules['min_duration']:.3f}s")
        print(f"最长时长: {rules['max_duration']:.1f}s")
        print(f"最小间隔: {rules['min_gap']:.3f}s")
        print(f"最大行数: {rules['max_lines']}")
        print(f"CJK CPS: {rules['cjk_cps']}")
        print(f"Latin CPS: {rules['latin_cps']}")
        print(f"CJK CPL: {rules['cjk_cpl']}")
        print(f"Latin CPL: {rules['latin_cpl']}")
        print()

        # 整体统计
        print("整体统计:")
        print("-" * 40)
        print(f"平均时长: {overall['avg_duration']:.2f}s")
        print(f"平均间隔: {overall['avg_gap']:.3f}s")
        print(f"平均CPS: {overall['avg_cps']:.1f}")
        print()

        # 违规统计
        print("违规类型统计:")
        print("-" * 40)
        violation_types = overall['violation_types']
        for violation_type, count in violation_types.items():
            if count > 0:
                percentage = (count / overall['total_subtitles'] * 100) if overall['total_subtitles'] > 0 else 0
                type_name = {
                    'duration_too_short': '时长过短',
                    'duration_too_long': '时长过长',
                    'gap_too_small': '间隔过小',
                    'cps_too_high': 'CPS过高',
                    'cpl_exceeded': '行长超限',
                    'too_many_lines': '行数过多',
                    'punctuation_issues': '标点问题'
                }.get(violation_type, violation_type)

                print(f"{type_name}: {count} ({percentage:.2f}%)")
        print()
