---
name: westock-data
description: 通过 westock-mcp 连接器查询 A股/港股/美股个股/指数/ETF 数据——行情、K线、财报、资金、技术指标、板块成份、宏观等。触发词：查行情、看K线、查财报、资金流向、板块概念、宏观数据。需已连接 westock-mcp 连接器。
---

# WeStock Data（MCP 模式）

**数据源**：腾讯自选股 **westock-mcp** 连接器 | **支持市场**：A股、港股、美股

> **前置条件**：专家包已声明 `dependencies.connectors: ["westock-mcp"]`。

> **连接器已连接时（铁律）**：取数**必须且只能**调用连接器的 `data_*` MCP Tool。**禁止**运行本地 `scripts/`、**禁止** `web_search` / WebSearch 替代行情/财务/K线/资金等结构化数据、**禁止**使用其他 skill 或 MCP 取数。westock-data / westock-tool 技能仅提供「何时调哪个 Tool」的方法论，实际取数通道只有 westock-mcp。

> **腾讯自选股连接器未连接时**：无法调用 `data_*` Tool。降级使用 WebSearch 及环境中其他可用 skill/MCP 取数，**效果会明显变差**；主理人会在 chat 单独提示「腾讯自选股连接器未连接」。

> **与 westock-tool 的分工**：
> - **westock-data**（本技能）：查个股/指数/板块详情、宏观、新闻公告、板块成份股
> - **westock-tool**：筛选/选股——找出满足条件的股票列表
> - 用户自选股管理：连接器 `portfolio_*` Tool（非本技能）

**返回处理**：MCP 返回 `{ ok, data, message }`。`ok: false` 时如实转述 `message`；`ok: true` 时将 `data` 转为表格或可读格式展示，禁止输出原始 JSON 堆砌。

完整 Tool 映射见 [references/mcp-tool-map.md](./references/mcp-tool-map.md)。

---

## 调用规范

1. **先 search 再查**：用户只给名称时，先 `data_search` 拿 `code`，再调其他 Tool
2. **多股批量**：支持 `codes` 的 Tool 用逗号分隔，**只调 1 次**（如 `data_quote` codes=`sh600519,sz000001`）
3. **概念股两步**：`data_sector` mode=search → `data_sector` mode=constituent
4. **参数不确定**：先读 Tool schema（`tools/data_*.json`）再调用

## 资讯时效过滤（默认 24h）

> **铁律**：调用以下资讯类接口后，**必须按返回 `time` 字段本地过滤，仅保留 `now − 24h` 内的条目**再展示或进入分析。腾讯接口**不支持时间参数**，此过滤是「取回后」行为，不是传参。

适用接口：`data_news`（type=0公告/1研报/2新闻/3全部）、`data_notice`、`data_report`、`data_dehydrated`。

规范：
1. 默认 `limit` 取 **30**（覆盖 24h 余量，又不过度拉取）。
2. 过滤解析：返回 `time` 格式为 `%Y-%m-%d %H:%M:%S`，与当前时间比较，丢弃超过 24h 的条目。
3. **场景豁免**：深度研究 / 事件复盘 / 成因分析（如蔡森形态、破底翻、资金情绪框架）时，可显式放宽窗口（默认 **7d**，可指定 30d）；此类需求应在调用时说明，不做 24h 强截。
4. 圆桌类技能（如 `caisen-10-experts-analyst`）调用本类接口时，遵循本规范即可，无需各自重写。

过滤参考实现（Python）：
```python
from datetime import datetime, timedelta

def filter_recent(items, hours=24, now=None):
    now = now or datetime.now()
    cutoff = now - timedelta(hours=hours)
    out = []
    for it in items:
        try:
            t = datetime.strptime(it["time"], "%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError):
            continue
        if t >= cutoff:
            out.append(it)
    return out
```

---

## 常用 Tool 速查

### 搜索与行情

```
data_search      query=腾讯控股                    # 搜股票
data_search      query=华夏 type=etf               # 搜 ETF
data_search      query=银行 type=sector            # 搜板块（仅名称+代码）
data_quote       code=sh600519                     # 单股行情
data_quote       codes=sh600519,sz000001,hk00700   # 批量行情
data_score       code=sh600519                     # 诊股评分
```

### K 线与分时

```
data_kline       code=sh600000 period=day limit=20 fq=qfq
data_minute      code=sh600000 days=5
```

周期：`day`/`week`/`month`/`season`/`year`；复权：`qfq`/`hfq`/空(不复权)

### 财务与公司

```
data_finance     code=sh600000 num=4               # 最近 4 期财报
data_finance     code=hk00700 type=income num=4    # 港股损益表
data_profile     code=sh600000
data_rating      code=sh600519
data_consensus   code=sh600519
```

### 资金与交易

```
data_fund_flow   code=sh600000 date=2026-03-10
data_fund_short  code=usAAPL
data_fund_margin code=sz000001
data_fund_block  code=sz000001
data_buyback     code=sh600519
data_lhb         type=jg date=2026-03-20
data_risk        code=sh600000 types=pledge,unlock  # 仅 A 股
```

### 新闻与研究

```
data_news        mode=list symbol=sh600000 limit=20
data_news        mode=detail id=<新闻ID>
data_notice      mode=list symbol=sh600000
data_report      mode=list symbol=sh600000 limit=20
data_dehydrated  mode=list limit=10
```
> ⏱ 上述资讯类接口取回后**必须按 `time` 字段本地过滤 24h**（详见「资讯时效过滤（默认 24h）」章节）；深度研究场景可豁免至 7d。

### 技术与筹码

```
data_technical   code=sh600000 group=macd,rsi
data_chip        code=sh600519
data_shareholder code=sh600519
data_dividend    code=sh600519 years=5
```

### 市场与板块

```
data_hot         kind=stock
data_stocklist   mode=rank                        # 热门股单（非用户自选）
data_changedist  type=hs
data_connect     exchange=sh limit=50             # 沪股通
data_ipo         market=HS
data_calendar    date=2026-03-10 limit=30
data_macro       mode=list                        # 列出指标
data_macro       names=cn_cpi_ppi year=2025
data_sector      mode=search query=华为           # 搜概念
data_sector      mode=constituent code=style_pt01801517  # 成份股
data_index       code=sh000300                    # 指数成份
```

---

## 已知限制

| 限制项 | 说明 |
|--------|------|
| 风险事件 `data_risk` | 仅 A 股（sh/sz/bj） |
| 龙虎榜 `data_lhb` | 仅 A 股 |
| 筹码 `data_chip` | 仅沪深京 A 股 |
| 货币单位 | 港股港元/美元，美股美元，展示时须标注 |
| `data_search`/`data_minute` | 不支持批量 |

---

## 股票代码格式

| 市场 | 格式 | 示例 |
|------|------|------|
| 沪市/科创板 | sh + 6位 | `sh600000`、`sh688981` |
| 深市 | sz + 6位 | `sz000001` |
| 北交所 | bj + 6位 | `bj430047` |
| 港股 | hk + 5位 | `hk00700` |
| 美股 | us + 代码 | `usAAPL` |
| 板块 | pt 或 sw 前缀 | `pt01801080`、`sw1_pt01801080` |

---

## 常见场景

```
查股票：data_search 腾讯 → data_quote hk00700
K线分析：data_kline sz002714 period=day limit=20
多股对比：data_quote hk00700,usBABA
资金流向：data_fund_flow sh688981
概念股：data_sector search 华为 → data_sector constituent <code>
板块排行：data_sector mode=ranking ...
宏观：data_macro names=cn_pmi start=2024 end=2025
```

完整场景（33 个）见 [references/scenarios-guide.md](./references/scenarios-guide.md)（CLI 示例请对照 [mcp-tool-map.md](./references/mcp-tool-map.md) 转换）。

字段说明见 [references/ai_usage_guide.md](./references/ai_usage_guide.md)。

---

## 重要声明

> 1. 本技能仅提供客观市场数据查询与展示，不构成投资建议。
> 2. 数据可能有延迟，以交易所官方为准。
> 3. 投资有风险，决策需谨慎。

**数据来源**：腾讯自选股 westock-mcp 连接器
