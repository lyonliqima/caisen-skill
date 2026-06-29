---
name: alphaear-search
description: "财经搜索工具。支持多引擎网络搜索（Jina/DDG/百度）和本地RAG文档搜索。在四方法论框架中作为辅助数据源，为方法论推导提供背景信息搜索能力。"
---

# AlphaEar 搜索工具

> **在方法论体系中的定位**：辅助数据工具（低权重）。为四套方法论提供信息搜索能力，但搜索结果需经过方法论框架处理才能成为结论。

## Overview / 概述

统一搜索能力：网络搜索（Jina/DDG/百度）和本地RAG搜索。

## Capabilities / 功能

### 1. 网络搜索

通过 `scripts/search_tools.py` 中的 `SearchTools` 使用。

-   **搜索**: `search(query, engine, max_results)`
    -   引擎：`jina`、`ddg`、`baidu`、`local`
    -   返回：JSON字符串（摘要）或 List[Dict]
-   **智能缓存（Agent驱动）**: 使用 `references/PROMPTS.md` 中的搜索缓存Prompt避免重复搜索
-   **聚合搜索**: `aggregate_search(query)`
    -   合并多个引擎的搜索结果

### 2. 本地RAG

通过 `scripts/hybrid_search.py` 或 `SearchTools` 的 `engine='local'` 使用。

-   **搜索**: 搜索本地 `daily_news` 数据库

## Dependencies / 依赖

-   `requests`, `beautifulsoup4`, `jieba`
-   `scripts/database_manager.py` (本地数据库)
