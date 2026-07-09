---
name: alphaear
description: AlphaEar 金融研究辅助套件（四方法论框架的辅助数据源与输出工具）。整合 news(财经新闻聚合)/search(多引擎+本地RAG搜索)/sentiment(金融文本情绪)/predictor(时序预测)/reporter(专业报告生成)/stock(A股港股美股行情与基本面)/logic-visualizer(逻辑传导图)/signal-tracker(信号追踪)/deepear-lite(高频信号) 九个模块。当用户需要新闻背景、数据搜索、情绪分析、预测参考、报告生成、行情数据、逻辑图、信号跟踪或高频信号时调用；预测结果不能覆盖方法论推导结论。
---

# AlphaEar 金融研究辅助套件

AlphaEar 是「四方法论框架」（蔡森形态学 / 笨鸟数据拆解 / 卢麒元制度结构 / 杨世光宏观六步法）的**辅助数据源与输出工具**。它由九个独立微模块合并而成，统一在 `alphaear` 技能下调用：news、search、sentiment、predictor、reporter、stock、logic-visualizer、signal-tracker、deepear-lite。

> **重要定位**：所有模块均为**辅助（低权重）**性质——它们为方法论推导提供新闻背景、数据、情绪、预测、图表与报告能力，但**任何预测/搜索/信号结果都不能推翻或覆盖四套方法论的推导结论**。

## 九模块

### 1. news — 财经新闻聚合
实时聚合微博 / 知乎 / 华尔街见闻等多平台热点财经新闻，生成统一趋势报告，并获取 Polymarket 预测市场数据。需要新闻背景时调用。详见 `references/alphaear-news.md`。

### 2. search — 多引擎 + 本地 RAG 搜索
统一搜索能力：网络搜索（Jina / DDG / 百度）与本地 RAG 文档搜索。需要检索背景信息、公司资料、历史资讯时调用。详见 `references/alphaear-search.md`。

### 3. sentiment — 金融文本情绪
使用 FinBERT 本地模型或 LLM 分析金融文本情绪（正面 / 负面 / 中性）及评分，为笨鸟反常信号识别法提供舆情数据支撑。需要量化市场情绪时调用。详见 `references/alphaear-sentiment.md`。

### 4. predictor — 时序预测
使用 Kronos 模型进行时序预测，并结合新闻情绪调整结果。作为方法论推导的量化参考输入，**预测结果不能覆盖方法论结论**。需要量化预测参考时调用。详见 `references/alphaear-predictor.md`。

### 5. reporter — 专业报告生成
规划、撰写、编辑专业金融报告并生成图表配置，将方法论推导结论结构化输出。需要产出最终报告时调用。详见 `references/alphaear-reporter.md`。

### 6. stock — A股/港股/美股行情与基本面
搜索股票代码、获取历史 OHLCV 价格数据、查询基本面信息（行业 / 市值 / PE）。为蔡森形态学与笨鸟数据拆解提供价格与基本面数据。详见 `references/alphaear-stock.md`。

### 7. logic-visualizer — 逻辑传导图
创建 Draw.io XML 格式的可视化逻辑传导链图，将方法论推导链条图形化展示。需要可视化因果 / 传导关系时调用。详见 `references/alphaear-logic-visualizer.md`。

### 8. signal-tracker — 信号追踪
追踪投资信号的演化，根据新市场信息判断信号是强化、弱化还是被证伪。需要跟踪既有信号状态时调用（依赖 search 与 stock 模块收集数据）。详见 `references/alphaear-signal-tracker.md`。

### 9. deepear-lite — 高频信号
抓取 DeepEar Lite 平台最新金融市场信号（标题、摘要、置信度评分、推理过程），作为高频市场信号参考输入。详见 `references/alphaear-deepear-lite.md`。

## 参考索引

各模块的完整说明（功能、核心工具、依赖）已逐字保留在 `references/` 下：

| 模块 | 说明 | 详细文档 |
|------|------|----------|
| news | 财经新闻聚合 | `references/alphaear-news.md` |
| search | 多引擎 + 本地 RAG 搜索 | `references/alphaear-search.md` |
| sentiment | 金融文本情绪 | `references/alphaear-sentiment.md` |
| predictor | 时序预测 | `references/alphaear-predictor.md` |
| reporter | 专业报告生成 | `references/alphaear-reporter.md` |
| stock | A股/港股/美股行情与基本面 | `references/alphaear-stock.md` |
| logic-visualizer | 逻辑传导图 | `references/alphaear-logic-visualizer.md` |
| signal-tracker | 信号追踪 | `references/alphaear-signal-tracker.md` |
| deepear-lite | 高频信号 | `references/alphaear-deepear-lite.md` |

脚本位于 `scripts/<module>/`（例如 `scripts/alphaear-news/`）。
