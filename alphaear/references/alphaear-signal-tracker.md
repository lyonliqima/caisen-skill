---
name: alphaear-signal-tracker
description: "投资信号追踪工具。追踪投资信号的演化过程，根据新市场信息判断信号是强化、弱化还是被证伪。在四方法论框架中作为辅助参考，为方法论推导提供信号跟踪能力。"
---

# AlphaEar 信号追踪工具

> **在方法论体系中的定位**：辅助参考工具（低权重）。追踪和更新投资信号状态，为方法论推导提供信号演化参考。

## Overview / 概述

提供投资信号追踪逻辑。评估新市场信息如何影响现有信号（强化/弱化/证伪/不变）。

## Capabilities / 功能

### 1. 信号演化追踪（Agent工作流）

**你（Agent）** 是追踪者。使用 `references/PROMPTS.md` 中的Prompt。

**工作流程：**
1.  **研究**: 使用 **FinResearcher Prompt** 收集信号相关事实/价格
2.  **分析**: 使用 **FinAnalyst Prompt** 生成初始 `InvestmentSignal`
3.  **追踪**: 对已有信号，使用 **Signal Tracking Prompt** 评估演化（强化/弱化/证伪）

**工具：**
- 使用 `alphaear-search` 和 `alphaear-stock` skills 收集数据
- 使用 `scripts/fin_agent.py` 辅助函数

## Dependencies / 依赖

-   `scripts/database_manager.py` (本地数据库)
