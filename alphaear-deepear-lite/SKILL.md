---
name: alphaear-deepear-lite
description: "DeepEar Lite高频信号获取工具。抓取最新的金融市场信号，包括标题、摘要、置信度评分和推理过程。在四方法论框架中作为辅助数据源，提供高频市场信号参考。"
---

# AlphaEar DeepEar Lite 信号工具

> **在方法论体系中的定位**：辅助数据工具（低权重）。提供DeepEar Lite平台的高频市场信号，作为方法论推导的参考输入。

## Overview / 概述

获取高频金融信号，包括标题、摘要、置信度评分和推理过程，直接来自DeepEar Lite平台实时数据源。

## Capabilities / 功能

### 1. 获取最新金融信号

通过 `scripts/deepear_lite.py` 中的 `DeepEarLiteTools` 使用。

-   **获取信号**: `fetch_latest_signals()`
    -   从 `https://deepear.vercel.app/latest.json` 获取最新信号
    -   返回格式化的信号报告（标题、情绪/置信度、摘要、来源链接）

## Dependencies / 依赖

-   `requests`, `loguru`
-   无需本地数据库
