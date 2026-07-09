---
name: capital-three-flow
description: 资本三流每日观测系统（工程化监控版）。基于卢麒元"资本三流"框架与费雪方程式 M·V=P·Q，量化监控资本运动的三个核心维度——流量(规模)、流向(方向/分布)、流速(周转速度)。每天运行可采集 M2/名义GDP/外汇储备/基础货币/融资融券/大盘主力资金/人民币汇率(USD/CNY)/板块资金流 等公开数据，计算 CFCI(流向综合)、CFEI(流转效率)、CRI(走资风险，含人民币贬值压力)三大指数与"三流共振"离散打分 S，输出 JSON + Markdown 日报及 Streamlit 大屏。适用：宏观资本动向监控、每日复盘、趋势共振判断。当用户说"跑一下资本三流/三流日报/监控资本流向/今天钱往哪流"时调用。
agent_created: true
---

# 资本三流每日观测系统（监控版）

> **📌 家目录 / 主副本**：本目录 `/Users/weihaoli/Desktop/蔡森 skill/capital-three-flow/` 是三流 skill 的**主副本（与破底翻同目录）**。触发词「看看三流 / 三流」直接运行本目录 `scripts/monitor.py`。镜像副本在 `~/.workbuddy/skills/capital-three-flow/`（Skill 工具注册用），两处需同步维护。

> **定位**：把卢麒元"资本三流"方法论（见 `lu-qiyuan-analysis` 的 M2）**工程化成一个能每天跑的监控工具**。
> 它是 `lu-qiyuan-analysis` 的**操作型补丁**——前者讲框架与观点，本 skill 落地成可量化、可复盘的日报系统。
> 数学底层、公式与口径说明见 [references/methodology.md](references/methodology.md)，请勿脱离口径自行改公式。

## 核心概念（速记）

费雪方程式 `M × V = P × Q` 的三流拆解：
- **流量 M** → 参与循环的资本规模（M2 / 社融 / 北向净流入 / 融资余额）
- **流速 V** → 周转速度（宏观 `V=GDP/M2`；市场 `换手率=成交额/流通市值`）
- **流向** → 分布结构，用方向系数 `D=(流入−流出)/(流入+流出)∈[-1,1]` 与集中度 HHI 量化

三个合成指数 + 共振判定：
- **CFCI** 资本流向综合指数（-100~+100）
- **CFEI** 资本流转效率指数（越高=空转越少）
- **CRI** 走资风险指数（0~100，越高越危险）
- **S = S流量 + S流向 + S流速**（各 -1/0/+1）：`S≥2` 共振确立趋势；`S≤0` 背离混沌

## 何时调用

- 用户要求"跑资本三流 / 出三流日报 / 监控资本流向 / 今天钱往哪流"
- 需要每日宏观资本动向复盘的自动化场景
- 与其它方法论（卢麒元 M1-M9、笨鸟数据拆解、蔡森形态）交叉验证资本背景

## 工作流（每天执行）

```bash
# 1) 真实采集（需 akshare + 网络；在本机运行）
python scripts/monitor.py

# 2) 离线验证流水线（无网络/无 akshare 时用）
python scripts/monitor.py --demo

# 3) 出样例并起大屏
python scripts/monitor.py --demo --dashboard
```

执行顺序（脚本已编排好，无需手动调用）：
1. `collector.collect()` —— 采集多类指标（M2/GDP/外储/基础货币/融资融券/主力资金/人民币汇率/板块资金流），失败降级为 None，写本地缓存
2. `calculator.run_all()` —— 计算三维指标 + 三指数 + 共振打分 S（含板块资金流 HHI、人民币贬值压力进 CRI）
3. `monitor` —— 写出 `reports/capital_three_flow_YYYYMMDD.json` 与 `.md`，可选起大屏

## 目录结构

```
capital-three-flow/
├── SKILL.md
├── config/indicators.yaml     # 权重/阈值集中配置（改这里，别改代码）
├── references/
│   ├── methodology.md         # 费雪方程式三流量化公式全文
│   └── data_sources.md        # 数据源考证（akshare 函数名/状态，2026-07 核实）
├── scripts/
│   ├── collector.py           # 数据采集（akshare，带缓存+降级）
│   ├── calculator.py          # 计算引擎（三维+三指数+打分）
│   ├── monitor.py             # 编排器：采集→计算→报告
│   ├── dashboard.py           # Streamlit 大屏
│   └── sample_data.json       # 离线样例
├── data/cache/                # 采集缓存
└── reports/                   # 每日报告输出
```

## 依赖

```
pip install akshare pandas numpy pyyaml streamlit
```
`akshare`/`streamlit` 为运行真实采集与大屏所需；`--demo` 仅需 `pandas numpy pyyaml`（且 pyyaml 缺失时有内置兜底配置）。

## 数据缺口与口径纪律（重要）

- 任一数据源失败 → 该分项记 `None`，报告标"缺失"，合成指数按**可用分项重新归一化**，绝不编造数值。
- **北向/南向净流量自 2024-08-19 起交易所停更、akshare 已移除接口**（已核实）；跨境流向改用**外汇储备变动**代理，并辅以**人民币汇率 USD/CNY**（`forex_spot_em` 实时，无需 API key）作外部贬值压力代理，进入 CRI。
- **社会融资规模**在 akshare 当前 master 无对应函数，CFEI 的"信贷周转"分项降级为 0（报告标注）。
- **板块资金流 HHI** 由 `stock_fund_flow_industry` 各行业"主力净流入-净额"计算，提供行业级（细分层级）资金集中度；接口失败则 HHI 标"缺失"。
- 真实可用的核心项：M2、名义GDP、外汇储备、基础货币(储备货币)、融资融券、大盘主力资金净流入、人民币汇率、板块资金流。函数名与状态详见 `references/data_sources.md`。
- 跨期比较以**同比 / 滚动均值**优先，避免季节性误判。
- 所有指数均为**相对度量与代理**，用于趋势观察而非精确预测。

## 输出示例（共振情形）

```
[monitor] 观测日期: 2026-07-09  demo=True
[monitor] CFCI=...  CFEI=...  CRI=...
[monitor] 三流得分 S=3 → 三流同向共振 —— 趋势力量确立，宏观趋势可顺势
```

## 免责声明

以上仅为基于卢麒元资本三流框架的方法论量化演示，不构成任何投资建议；数据缺口已标注缺失。
