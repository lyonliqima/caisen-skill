---
name: alphaear-news
description: "实时财经新闻聚合与舆情监控工具。获取微博/知乎/华尔街见闻等多平台热点财经新闻，生成统一趋势报告，获取Polymarket预测市场数据。在四方法论框架中作为辅助数据源，为方法论推导提供新闻背景。"
---

# AlphaEar 财经新闻聚合工具

> **在方法论体系中的定位**：辅助参考工具（低权重）。为四套方法论提供实时新闻背景，但不能推翻方法论推导的结论。

## Overview / 概述

获取实时热点新闻、生成多平台统一趋势报告、获取Polymarket预测市场数据。

## Capabilities / 功能

### 1. 热点新闻与趋势

通过 `scripts/news_tools.py` 中的 `NewsNowTools` 使用。

-   **获取新闻**: `fetch_hot_news(source_id, count)`
    -   参见 [sources.md](references/sources.md) 获取有效的 `source_id`（如 `cls`、`weibo`）
-   **统一报告**: `get_unified_trends(sources)`
    -   聚合多个来源的热点新闻

### 2. 预测市场数据

通过 `scripts/news_tools.py` 中的 `PolymarketTools` 使用。

-   **市场摘要**: `get_market_summary(limit)`
    -   返回活跃预测市场的格式化报告

## Dependencies / 依赖

-   `requests`, `loguru`
-   `scripts/database_manager.py` (本地数据库)
