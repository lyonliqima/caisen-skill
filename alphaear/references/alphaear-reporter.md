---
name: alphaear-reporter
description: "专业金融报告生成工具。规划、撰写、编辑专业金融报告，生成图表配置。在四方法论框架中作为输出工具，将方法论推导结论结构化输出为专业报告。"
---

# AlphaEar 报告生成工具

> **在方法论体系中的定位**：输出工具。将四套方法论的推导结论整合为结构化专业报告。

## Overview / 概述

提供结构化金融报告生成工作流，包括规划、撰写、编辑和图表生成。

## Capabilities / 功能

### 1. 结构化报告生成（Agent工作流）

**你（Agent）** 是报告生成者。使用 `references/PROMPTS.md` 中的Prompt逐步构建报告。

**工作流程：**
1.  **信号聚类**: 读取输入信号，使用 **Cluster Signals Prompt** 分组
2.  **撰写章节**: 对每个聚类，使用 **Write Section Prompt** 生成分析
3.  **组装报告**: 使用 **Final Assembly Prompt** 汇编报告

### 2. 可视化工具

通过 `scripts/visualizer.py` 生成图表配置。

## Dependencies / 依赖

-   `scripts/database_manager.py` (本地数据库)
