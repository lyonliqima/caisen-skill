---
name: alphaear-logic-visualizer
description: "金融逻辑传导链路图工具。创建Draw.io XML格式的可视化逻辑图，解释复杂的金融传导链或逻辑流程。在四方法论框架中作为可视化辅助，将方法论推导链条图形化展示。"
---

# AlphaEar 逻辑可视化器

> **在方法论体系中的定位**：可视化辅助工具。将方法论推导的传导链条图形化，帮助理解因果关系。

## Overview / 概述

专注于创建逻辑流程的可视化表示，生成Draw.io XML兼容图表。适用于可视化投资论点或信号传导链。

## Capabilities / 功能

### 1. 生成Draw.io图表（Agent工作流）

**你（Agent）** 是可视化者。使用 `references/PROMPTS.md` 中的Prompt生成XML。

**工作流程：**
1.  **生成XML**: 使用 **Draw.io XML Generation Prompt** 将逻辑链转化为XML
2.  **保存/渲染**: 通过 `scripts/visualizer.py` 的 `render_drawio_to_html(xml_content, filename)` 保存为HTML

## Dependencies / 依赖

-   无额外Python依赖（纯XML/HTML生成）
