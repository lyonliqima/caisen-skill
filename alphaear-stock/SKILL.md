---
name: alphaear-stock
description: "A股/港股/美股行情数据工具。搜索股票代码、获取历史OHLCV价格数据、查询基本面信息（行业/市值/PE）。在四方法论框架中作为辅助数据源，为蔡森形态学和笨鸟数据拆解提供价格与基本面数据。"
---

# AlphaEar 股票行情工具

> **在方法论体系中的定位**：辅助数据工具（低权重）。为四套方法论提供股票价格、基本面数据，但不能推翻方法论推导的结论。

## Overview / 概述

搜索A股/港股/美股代码，获取历史价格数据（OHLCV）和基本面信息。

## Capabilities / 功能

### 1. 股票搜索与数据

通过 `scripts/stock_tools.py` 中的 `StockTools` 使用。

-   **搜索**: `search_ticker(query)`
    -   按代码或名称模糊搜索（如"茅台"、"600519"）
    -   返回：`{code, name}` 列表
-   **获取价格**: `get_stock_price(ticker, start_date, end_date)`
    -   返回含OHLCV数据的DataFrame
    -   日期格式："YYYY-MM-DD"
-   **获取基本面**: `get_stock_fundamentals(ticker)`
    -   返回行业、市值、PE比率等dict
    -   支持A股/港股/美股

## Dependencies / 依赖

-   `pandas`, `requests`, `akshare`, `yfinance`
-   `scripts/database_manager.py` (股票数据表)

## Notes / 注意

-   **代理设置**: 美股数据（通过 `yfinance`）可能需要设置代理环境变量：
    ```bash
    export HTTP_PROXY="http://<proxy_ip>:<port>"
    export HTTPS_PROXY="http://<proxy_ip>:<port>"
    ```
-   **A股/港股**: 主要通过 `akshare`（东方财富）获取数据，通常国内直连效果最好。工具会自动检测代理问题并尝试直连。
