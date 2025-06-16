# 测试文件说明

本目录包含项目的测试脚本和分析工具。

## 📁 文件结构

### 核心测试脚本
- `test_subtitle_rules.py` - 字幕规则合规性测试主脚本
- `optimize_based_on_analysis.py` - 字幕质量分析和优化工具
- `subtitle_optimizer.py` - 字幕优化器

### Spacing修复测试
- `test_spacing_fix.py` - 基础spacing修复测试
- `test_spacing_fix_comprehensive.py` - 全面spacing修复测试
- `analyze_spacing_fix_results.py` - spacing修复效果分析

### 配置文件
- `subtitle_rules_analysis.json` - 字幕规则分析配置

## 🚀 使用方法

### 测试单个文件
```bash
python test/test_subtitle_rules.py path/to/subtitle.srt
```

### 测试整个目录
```bash
python test/test_subtitle_rules.py sample/
```

### 分析spacing修复效果
```bash
python test/analyze_spacing_fix_results.py
```

### 测试spacing修复功能
```bash
python test/test_spacing_fix.py
```

## 📊 测试报告

测试脚本会生成详细的合规性报告，包括：
- 字幕时长检查
- CPS（每秒字符数）检查
- 行长度检查
- 标点符号检查
- 间隔时间检查

## 🔧 维护说明

- 所有测试脚本都设计为独立运行
- 测试数据使用`../sample/`目录中的样本文件
- 新增测试功能请遵循现有的命名规范
