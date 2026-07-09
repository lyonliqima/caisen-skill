---
name: alphaear-predictor
description: "市场时序预测工具。使用Kronos模型进行时序预测，结合新闻情绪调整预测结果。在四方法论框架中作为辅助参考，为方法论推导提供量化预测参考，但预测结果不能覆盖方法论推导结论。"
---

# AlphaEar 预测工具

> **在方法论体系中的定位**：辅助参考工具（低权重）。提供Kronos时序预测作为方法论推导的量化参考，但预测结果不能覆盖方法论推导结论。

## Overview / 概述

使用Kronos模型（通过 `KronosPredictorUtility`）进行时序预测，并根据新闻情绪调整预测结果。

## Capabilities / 功能

### 1. 市场趋势预测

**工作流程：**
1.  **生成基础预测**: 通过 `scripts/kronos_predictor.py`（`KronosPredictorUtility`）生成技术/量化预测
2.  **调整预测（Agent驱动）**: 使用 `references/PROMPTS.md` 中的预测调整Prompt，根据最新新闻/逻辑主观调整数值

**核心工具：**
-   `KronosPredictorUtility.get_base_forecast(df, lookback, pred_len, news_text)`: 返回 `List[KLinePoint]`

## Dependencies / 依赖

-   `torch`, `numpy`, `pandas`
-   `scripts/database_manager.py` (本地数据库)
