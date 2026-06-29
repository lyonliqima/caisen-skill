---
name: alphaear-sentiment
description: "金融文本情绪分析工具。使用FinBERT本地模型或LLM分析金融文本的情绪（正面/负面/中性）及评分。在四方法论框架中作为辅助数据源，为笨鸟反常信号识别法提供舆情数据支撑。"
---

# AlphaEar 情绪分析工具

> **在方法论体系中的定位**：辅助数据工具（低权重）。为四套方法论提供市场情绪量化数据，但不能推翻方法论推导的结论。

## Overview / 概述

提供面向金融文本的情绪分析能力，支持FinBERT（本地模型）和LLM两种分析模式。

## Capabilities / 功能

### 1. 情绪分析（FinBERT / 本地）

通过 `scripts/sentiment_tools.py` 进行高速本地情绪分析。

**核心方法：**

-   `analyze_sentiment(text)`: 获取情绪评分和标签
    -   **返回**: `{'score': float, 'label': str, 'reason': str}`
    -   **评分范围**: -1.0（负面）到 1.0（正面）
-   `batch_update_news_sentiment(source, limit)`: 批量处理数据库中未分析的新闻

### 2. 情绪分析（LLM / Agent驱动）

需要更高精度或推理能力时，**你（Agent）** 应使用 `references/PROMPTS.md` 中的Prompt直接调用LLM分析，然后更新数据库。

## Dependencies / 依赖

-   `transformers`, `torch` (FinBERT)
-   `scripts/database_manager.py` (本地数据库)
