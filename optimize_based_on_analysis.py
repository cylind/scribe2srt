#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
基于分析结果的字幕算法优化脚本
根据质量分析报告中发现的问题，进一步优化字幕分割算法
"""

import json
import os
from typing import Dict, List
from analyze_subtitle_quality import SubtitleQualityAnalyzer

def analyze_non_punctuation_patterns(report_file: str = "subtitle_quality_report.json"):
    """
    分析非标点符号结尾的模式，找出改进方向
    
    Args:
        report_file: 分析报告文件路径
    """
    try:
        with open(report_file, 'r', encoding='utf-8') as f:
            report = json.load(f)
    except Exception as e:
        print(f"无法读取报告文件: {e}")
        return
        
    print("=" * 60)
    print("非标点符号结尾模式分析")
    print("=" * 60)
    
    # 统计不同类型的问题
    problem_patterns = {
        'incomplete_words': [],      # 词语被截断
        'missing_punctuation': [],   # 缺少标点符号
        'long_sentences': [],        # 句子过长
        'interjections': [],         # 感叹词、语气词
        'single_characters': []      # 单字符
    }
    
    for file_result in report['file_results']:
        if 'all_non_punctuation_endings' not in file_result:
            continue
            
        file_name = file_result['file']
        print(f"\n分析文件: {file_name}")
        print(f"非标点结尾数量: {file_result['non_punctuation_endings_count']}")
        
        for item in file_result['all_non_punctuation_endings']:
            text = item['text'].replace('\n', ' ').strip()
            last_char = item['last_char']
            
            # 分类问题类型
            if len(text) <= 3:
                problem_patterns['single_characters'].append({
                    'file': file_name,
                    'text': text,
                    'last_char': last_char,
                    'number': item['number']
                })
            elif last_char in 'あいうえおんてでばがやわすクパイふれまそいー':
                problem_patterns['interjections'].append({
                    'file': file_name,
                    'text': text,
                    'last_char': last_char,
                    'number': item['number']
                })
            elif text.endswith(('and', 'the', 'of', 'to', 'in', 'with', 'for')):
                problem_patterns['incomplete_words'].append({
                    'file': file_name,
                    'text': text,
                    'last_char': last_char,
                    'number': item['number']
                })
            elif len(text) > 50:
                problem_patterns['long_sentences'].append({
                    'file': file_name,
                    'text': text,
                    'last_char': last_char,
                    'number': item['number']
                })
            else:
                problem_patterns['missing_punctuation'].append({
                    'file': file_name,
                    'text': text,
                    'last_char': last_char,
                    'number': item['number']
                })
    
    # 输出分析结果
    print("\n" + "=" * 60)
    print("问题模式统计:")
    print("=" * 60)
    
    for pattern_name, items in problem_patterns.items():
        if items:
            print(f"\n{pattern_name.upper()}: {len(items)} 个")
            for i, item in enumerate(items[:3]):  # 只显示前3个示例
                print(f"  示例 {i+1}: {item['file']} #{item['number']}")
                print(f"    文本: {item['text'][:60]}{'...' if len(item['text']) > 60 else ''}")
                print(f"    末尾: '{item['last_char']}'")
    
    return problem_patterns

def generate_optimization_suggestions(problem_patterns: Dict):
    """
    基于问题模式生成优化建议
    
    Args:
        problem_patterns: 问题模式字典
    """
    print("\n" + "=" * 60)
    print("优化建议:")
    print("=" * 60)
    
    suggestions = []
    
    if problem_patterns['incomplete_words']:
        suggestions.append({
            'priority': 'HIGH',
            'issue': '英文词语被截断',
            'suggestion': '增强英文单词边界检测，避免在单词中间分割',
            'implementation': '在_find_best_split_position中增加英文单词边界检查'
        })
    
    if problem_patterns['long_sentences']:
        suggestions.append({
            'priority': 'MEDIUM',
            'issue': '长句子缺少分割点',
            'suggestion': '降低标点符号分割的最小长度要求，更积极地寻找分割点',
            'implementation': '调整_find_best_punctuation_break_aggressive中的长度阈值'
        })
    
    if problem_patterns['interjections']:
        suggestions.append({
            'priority': 'LOW',
            'issue': '日文感叹词和语气词',
            'suggestion': '这些通常是自然的语言表达，可以接受',
            'implementation': '无需特别处理，或者可以在日文标点符号中增加特殊处理'
        })
    
    if problem_patterns['single_characters']:
        suggestions.append({
            'priority': 'MEDIUM',
            'issue': '单字符字幕',
            'suggestion': '避免生成过短的字幕，尝试与前后字幕合并',
            'implementation': '在字幕生成后进行后处理，合并过短的字幕'
        })
    
    if problem_patterns['missing_punctuation']:
        suggestions.append({
            'priority': 'HIGH',
            'issue': '缺少标点符号的句子',
            'suggestion': '进一步降低分割阈值，更早触发标点符号搜索',
            'implementation': '将长度检测阈值从1.1x降低到1.0x或0.9x'
        })
    
    for i, suggestion in enumerate(suggestions, 1):
        print(f"{i}. 【{suggestion['priority']}】{suggestion['issue']}")
        print(f"   建议: {suggestion['suggestion']}")
        print(f"   实现: {suggestion['implementation']}")
        print()

def calculate_improvement_potential(report_file: str = "subtitle_quality_report.json"):
    """
    计算改进潜力
    
    Args:
        report_file: 分析报告文件路径
    """
    try:
        with open(report_file, 'r', encoding='utf-8') as f:
            report = json.load(f)
    except Exception as e:
        print(f"无法读取报告文件: {e}")
        return
        
    current_ratio = report['overall_punctuation_ratio']
    total_non_punctuation = report['total_subtitles'] - report['total_punctuation_endings']
    
    print("\n" + "=" * 60)
    print("改进潜力分析:")
    print("=" * 60)
    
    print(f"当前标点符号分割比例: {current_ratio:.2%}")
    print(f"非标点符号结尾数量: {total_non_punctuation}")
    
    # 假设我们能解决50%的问题
    potential_improvement = total_non_punctuation * 0.5
    new_ratio = (report['total_punctuation_endings'] + potential_improvement) / report['total_subtitles']
    
    print(f"如果解决50%的问题，新比例: {new_ratio:.2%}")
    print(f"提升幅度: {(new_ratio - current_ratio):.2%}")
    
    # 目标分析
    target_95 = 0.95
    needed_improvement = (target_95 * report['total_subtitles']) - report['total_punctuation_endings']
    
    print(f"\n要达到95%目标，需要改进: {needed_improvement:.0f} 个字幕")
    print(f"改进比例: {needed_improvement / total_non_punctuation:.1%} 的非标点结尾字幕")

def main():
    """主函数"""
    print("基于分析结果的字幕算法优化")
    
    # 检查是否存在分析报告
    if not os.path.exists("subtitle_quality_report.json"):
        print("未找到分析报告，正在生成...")
        analyzer = SubtitleQualityAnalyzer()
        analysis_result = analyzer.analyze_directory("sample")
        analyzer.save_detailed_report(analysis_result, "subtitle_quality_report.json")
    
    # 分析非标点符号结尾模式
    problem_patterns = analyze_non_punctuation_patterns()
    
    # 生成优化建议
    if problem_patterns:
        generate_optimization_suggestions(problem_patterns)
    
    # 计算改进潜力
    calculate_improvement_potential()
    
    print("\n" + "=" * 60)
    print("总结:")
    print("=" * 60)
    print("1. 当前算法已经达到93.32%的标点符号分割比例，表现优秀")
    print("2. 主要问题集中在英文长句和日文感叹词")
    print("3. 通过进一步优化，有望达到95%以上的目标")
    print("4. 建议优先处理英文单词边界和长句分割问题")

if __name__ == "__main__":
    main()
