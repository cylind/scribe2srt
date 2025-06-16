#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
字幕分割质量分析脚本
检测SRT字幕是否在标点符号处分割，计算分割质量指标
"""

import os
import re
import json
from typing import List, Dict, Tuple
from pathlib import Path

class SubtitleQualityAnalyzer:
    """字幕质量分析器"""
    
    def __init__(self):
        # 定义中文标点符号
        self.chinese_punctuation = set("。！？；：，、""''（）【】《》〈〉「」『』…—")
        # 定义英文标点符号
        self.english_punctuation = set(".,;:!?()[]{}\"'-")
        # 所有标点符号
        self.all_punctuation = self.chinese_punctuation | self.english_punctuation
        
    def parse_srt_file(self, srt_path: str) -> List[Dict]:
        """
        解析SRT文件，提取字幕内容
        
        Args:
            srt_path: SRT文件路径
            
        Returns:
            字幕列表，每个元素包含序号、时间和文本
        """
        subtitles = []
        
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
            # 按空行分割字幕块
            subtitle_blocks = re.split(r'\n\s*\n', content)
            
            for block in subtitle_blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    # 序号
                    try:
                        number = int(lines[0])
                    except ValueError:
                        continue
                        
                    # 时间轴
                    time_line = lines[1]
                    
                    # 字幕文本（可能多行）
                    text_lines = lines[2:]
                    text = '\n'.join(text_lines).strip()
                    
                    if text:  # 只添加非空字幕
                        subtitles.append({
                            'number': number,
                            'time': time_line,
                            'text': text
                        })
                        
        except Exception as e:
            print(f"解析SRT文件时出错 {srt_path}: {e}")
            
        return subtitles
        
    def get_last_character(self, text: str) -> str:
        """
        获取字幕文本的最后一个字符（忽略空白字符）
        
        Args:
            text: 字幕文本
            
        Returns:
            最后一个非空白字符
        """
        # 如果是多行文本，取最后一行
        lines = text.strip().split('\n')
        last_line = lines[-1].strip()
        
        # 返回最后一个字符
        return last_line[-1] if last_line else ''
        
    def is_punctuation_ending(self, text: str) -> bool:
        """
        检查字幕是否以标点符号结尾
        
        Args:
            text: 字幕文本
            
        Returns:
            是否以标点符号结尾
        """
        last_char = self.get_last_character(text)
        return last_char in self.all_punctuation
        
    def analyze_subtitle_file(self, srt_path: str) -> Dict:
        """
        分析单个字幕文件的分割质量
        
        Args:
            srt_path: SRT文件路径
            
        Returns:
            分析结果字典
        """
        subtitles = self.parse_srt_file(srt_path)
        
        if not subtitles:
            return {
                'file': srt_path,
                'total_subtitles': 0,
                'punctuation_endings': 0,
                'punctuation_ratio': 0.0,
                'non_punctuation_endings': [],
                'error': 'No subtitles found'
            }
            
        punctuation_count = 0
        non_punctuation_endings = []
        
        for subtitle in subtitles:
            text = subtitle['text']
            last_char = self.get_last_character(text)
            
            if self.is_punctuation_ending(text):
                punctuation_count += 1
            else:
                non_punctuation_endings.append({
                    'number': subtitle['number'],
                    'text': text,
                    'last_char': last_char,
                    'time': subtitle['time']
                })
                
        total_count = len(subtitles)
        punctuation_ratio = punctuation_count / total_count if total_count > 0 else 0.0
        
        return {
            'file': os.path.basename(srt_path),
            'total_subtitles': total_count,
            'punctuation_endings': punctuation_count,
            'non_punctuation_endings_count': len(non_punctuation_endings),
            'punctuation_ratio': punctuation_ratio,
            'non_punctuation_endings': non_punctuation_endings[:10],  # 只显示前10个
            'all_non_punctuation_endings': non_punctuation_endings  # 完整列表用于详细分析
        }
        
    def analyze_directory(self, directory: str) -> Dict:
        """
        分析目录中所有SRT文件的分割质量
        
        Args:
            directory: 目录路径
            
        Returns:
            总体分析结果
        """
        srt_files = list(Path(directory).glob('*.srt'))
        
        if not srt_files:
            return {
                'error': f'No SRT files found in {directory}'
            }
            
        file_results = []
        total_subtitles = 0
        total_punctuation_endings = 0
        
        for srt_file in srt_files:
            result = self.analyze_subtitle_file(str(srt_file))
            file_results.append(result)
            
            if 'error' not in result:
                total_subtitles += result['total_subtitles']
                total_punctuation_endings += result['punctuation_endings']
                
        overall_ratio = total_punctuation_endings / total_subtitles if total_subtitles > 0 else 0.0
        
        return {
            'directory': directory,
            'total_files': len(srt_files),
            'total_subtitles': total_subtitles,
            'total_punctuation_endings': total_punctuation_endings,
            'overall_punctuation_ratio': overall_ratio,
            'file_results': file_results
        }
        
    def print_analysis_report(self, analysis_result: Dict):
        """
        打印分析报告
        
        Args:
            analysis_result: 分析结果
        """
        if 'error' in analysis_result:
            print(f"错误: {analysis_result['error']}")
            return
            
        print("=" * 60)
        print("字幕分割质量分析报告")
        print("=" * 60)
        
        print(f"分析目录: {analysis_result['directory']}")
        print(f"文件总数: {analysis_result['total_files']}")
        print(f"字幕总数: {analysis_result['total_subtitles']}")
        print(f"标点符号结尾: {analysis_result['total_punctuation_endings']}")
        print(f"标点符号分割比例: {analysis_result['overall_punctuation_ratio']:.2%}")
        print()
        
        print("各文件详细分析:")
        print("-" * 60)
        
        for result in analysis_result['file_results']:
            if 'error' in result:
                print(f"{result['file']}: 错误 - {result['error']}")
                continue
                
            print(f"文件: {result['file']}")
            print(f"  字幕数量: {result['total_subtitles']}")
            print(f"  标点结尾: {result['punctuation_endings']}")
            print(f"  非标点结尾: {result['non_punctuation_endings_count']}")
            print(f"  标点比例: {result['punctuation_ratio']:.2%}")
            
            # 显示非标点结尾的示例
            if result['non_punctuation_endings']:
                print("  非标点结尾示例:")
                for example in result['non_punctuation_endings'][:3]:  # 只显示前3个
                    text_preview = example['text'].replace('\n', ' ')[:50]
                    if len(text_preview) < len(example['text'].replace('\n', ' ')):
                        text_preview += "..."
                    print(f"    #{example['number']}: '{text_preview}' (末尾: '{example['last_char']}')")
            print()
            
    def save_detailed_report(self, analysis_result: Dict, output_file: str):
        """
        保存详细分析报告到JSON文件
        
        Args:
            analysis_result: 分析结果
            output_file: 输出文件路径
        """
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_result, f, ensure_ascii=False, indent=2)
            print(f"详细报告已保存到: {output_file}")
        except Exception as e:
            print(f"保存报告时出错: {e}")

def main():
    """主函数"""
    analyzer = SubtitleQualityAnalyzer()
    
    # 分析sample目录中的字幕文件
    sample_dir = "sample"
    
    if not os.path.exists(sample_dir):
        print(f"目录 {sample_dir} 不存在")
        return
        
    print("开始分析字幕分割质量...")
    analysis_result = analyzer.analyze_directory(sample_dir)
    
    # 打印报告
    analyzer.print_analysis_report(analysis_result)
    
    # 保存详细报告
    analyzer.save_detailed_report(analysis_result, "subtitle_quality_report.json")
    
    # 提供改进建议
    if 'overall_punctuation_ratio' in analysis_result:
        ratio = analysis_result['overall_punctuation_ratio']
        print("=" * 60)
        print("改进建议:")
        
        if ratio >= 0.95:
            print("✅ 优秀！字幕分割质量很高，95%以上在标点符号处分割")
        elif ratio >= 0.85:
            print("✅ 良好！字幕分割质量较好，85%以上在标点符号处分割")
        elif ratio >= 0.70:
            print("⚠️  一般！字幕分割质量有待改进，建议优化算法")
        else:
            print("❌ 较差！字幕分割质量需要大幅改进")
            
        print(f"当前标点符号分割比例: {ratio:.2%}")
        print(f"建议目标: 95%以上")

if __name__ == "__main__":
    main()
