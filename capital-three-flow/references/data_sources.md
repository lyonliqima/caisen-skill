# 资本三流 —— 数据源考证（2026-07 核实）

> 本文件记录每个指标在 **AKShare 当前 master（1.18.x）** 的真实可得性与函数名。
> 结论通过查阅 akshare 源码（GitHub `akfamily/akshare`）逐函数核实，非凭记忆。
> 用途：采集器 `collector.py` 只调用"已确认可用"的函数；被移除/不可用的项明确标注降级。

## 一、关键变动：北向/南向净流量已不可用

- **2024-08-19 起**，沪深交易所调整沪深港通信息披露机制：不再实时/逐日披露北向（沪股通+深股通）**净买入额**，仅收市后公布成交总额、前十大活跃股，按月/年汇总。
- akshare 原 `stock_hsgt_north_net_flow_in_em` / `stock_hsgt_south_net_flow_in_em` 等接口在 master 中**已被移除**（`stock_hsgt_em.py` 现仅含 `stock_zh_ah_spot_em`、`stock_hsgt_sh_hk_spot_em`）。
- 经核实，akshare 也**没有**"北向持仓"聚合函数（`stock_share_hold.py` 只有高管股份变动 `stock_share_hold_change_*`）。
- **结论**：北向/南向"净流量"在当前开源数据下无法直接取得。本 skill 用**外汇储备变动**作为跨境资本流向的代理（卢麒元三流原框架即包含"外汇储备变动 = 本期 − 上期"），并在报告中标注北向缺失。

## 二、已确认可用的函数（采集器实际调用）

| 指标 | akshare 函数 | 关键返回列 | 频率 | 状态 |
|------|--------------|-----------|------|------|
| 广义货币 M2 | `macro_china_money_supply()` | `货币和准货币(M2)-数量(亿元)`、`货币和准货币(M2)-同比增长`（`月份`列形如 `2026年05月份`） | 月 | ✅ |
| 名义 GDP | `macro_china_gdp()` | `国内生产总值-绝对值`（季度值，需×4年化） | 季 | ✅ |
| 外汇储备 | `macro_china_foreign_exchange_gold()` | `统计时间`、`国家外汇储备`、`黄金储备` | 月 | ✅ |
| 基础货币 | `macro_china_central_bank_balance()` | `储备货币`（央行货币当局资产负债） | 月 | ✅ |
| 融资融券 | `macro_china_market_margin_sh()` | `日期`、`融资余额`、`融券余额`、`融资融券余额` | 日 | ✅ |
| 大盘主力资金 | `stock_market_fund_flow()` | `日期`、`主力净流入-净额`（全市场） | 日 | ✅ |
| 人民币汇率 | `forex_spot_em()` | `代码`、`名称`、`最新价`、`涨跌幅`；过滤 `代码=="USDCNY"` 取美元人民币 | 实时 | ✅ |
| 板块资金流 | `stock_fund_flow_industry(symbol="即时")` | `名称`、`今日主力净流入-净额`（按列名关键词匹配） | 日 | ✅ |

### 货币乘数（现在可真实计算）
- `货币乘数 = M2 / 基础货币(储备货币)`
- 此前用占位 1.0；现接入 `macro_china_central_bank_balance` 的 `储备货币` 列，得到真实乘数（中国约 7~8.5）。

### 跨境资本流向代理
- 用 `国家外汇储备` 当期值与上期之差 `Δ外储` 表征（外储升→净流入压力，降→走资压力）。
- 同时 `Δ外储` 直接进入 **CRI 走资风险指数**。

## 三、不可用 / 需替代的项

| 指标 | 原假设函数 | 现状 | 处理方式 |
|------|-----------|------|----------|
| 北向资金净流入 | `stock_hsgt_north_net_flow_in_em` | master 已移除 | 标记缺失；用 `Δ外储` 代理跨境流向 |
| 南向资金净流入 | `stock_hsgt_south_net_flow_in_em` | master 已移除 | 同上 |
| 社会融资规模 | `macro_china_social_financing` | **master 中不存在** | 标记缺失；CFEI 的信贷周转分项降级为 0，并注明 |
| 两市成交额 | `stock_zh_a_spot_em` | master 中不存在 | 可选：用 `stock_market_fund_flow` 的成交额相关列或省略；当前以主力净流入为主 |
| 美元指数 | `macro_usa_dollar_index` | `macro_usa` 中不存在 | 可选候选，失败则 None；外部压力以 `Δ外储`+人民币汇率代理 |

## 四、本次新增已默认开启的两项

- **人民币汇率（USD/CNY）**：`forex_spot_em()` 实时返回全部外汇对，过滤 `代码=="USDCNY"`（美元人民币）取 `最新价` 与 `涨跌幅`。无需 API key（东方财富源）。人民币贬值（涨跌幅为正）→ 计入 **CRI 走资风险** 作为外部压力代理。
  - 注：akshare 旧版 `currency_usd_cny_spot` 已移除；现 `currency.py` 仅剩 `currency_latest` 等需 currencyscoop.com API key 的函数，故改用 `forex_em.py` 的 `forex_spot_em()`。
- **板块资金流 HHI**：`stock_fund_flow_industry(symbol="即时")` 取各行业 `今日主力净流入-净额`，计算 **流向集中度 HHI = Σ(|net_i|/Σ|net|)²**，实现细分层级（行业级）的资金集中度度量。HHI 为无量纲，行业净流入单位不影响结果。

## 五、运行依赖与网络
- 全部为 akshare 封装的东方财富/新浪/金十等公开源，**需本机 + 网络**。
- WorkBuddy 沙箱对行情类 API 通过率极低（历史实测 ~4%），故**真实采集务必在用户本机运行**；`--demo` 离线验证流水线。
- akshare 接口随政策变动频繁，本文件函数名以 2026-07 核对的 master 为准；若某接口再度失效，采集器会优雅降级（记 None），不会中断。

## 六、采集工程注意（实跑踩坑，已固化进 collector.py）

1. **行序不一致**：`macro_china_money_supply` / `macro_china_gdp` / `macro_china_central_bank_balance` 返回的是**最新一期在前**；`macro_china_foreign_exchange_gold` / `macro_china_market_margin_sh` 是**最老在前**。直接 `iloc[-1]` 会取到最老数据（曾导致 M2 取到 2008 年、基础货币取到 1993 年）。已统一用 `_sorted_df()` 按时间列升序排序后取末行。
2. **时间列格式杂**：`月份`=`2026年05月份`、`统计时间`=`2026.6`、`季度`=`2026年第1季度`、`日期`=`2026-07-08`。`_parse_period()` 已覆盖这四种，统一转 Timestamp 排序。
3. **单位口径**：`macro_china_market_margin_sh` 的融资融券余额原始单位为**元**，需 ÷1e8 转亿元，与 `stock_market_fund_flow`（主力净流入，亦为元→亿元）口径一致，否则 D_market 会被放大 1 亿倍而饱和到 ±1。
4. **GDP 季度→年化**：`macro_china_gdp` 为季度绝对值，流速 `V=名义GDP/M2` 按 **×4 年化** 处理，否则 V 偏低（~0.1）导致 S_velocity 恒为 -1。
5. **板块资金流列名**：`stock_fund_flow_industry` 行业名列为 `行业`、净流列为 `净额`（非"主力净流入-净额"），`_col` 已改为匹配含"净额"且不含"占比"的列。
6. **微观流速（融资买入额）**：`macro_china_market_margin_sh` 除融资/融券余额外，还含 `融资买入额`（单位元→亿元）。其 ÷融资余额 = 杠杆资金**日周转速度**（微观流速代理），沙箱可取到（上交所源）。
7. **板块毛周转/涨跌幅**：`stock_fund_flow_industry` 另含 `流入资金`/`流出资金`（板块间毛周转，衡量微观资本活跃度）与 `行业-涨跌幅`（板块当日表现，用于交易参考多空榜的涨跌幅列）。
8. **交易参考模块**：`calculator.build_trading_reference()` 把三流翻译为「流动性背景 / 资本流向(跨境+板块排名) / 微观流速 / 策略倾向 / 板块多空榜」，纯方法论翻译，非投资建议。

## 七、向心坍缩全球风险指标（卢麒元 M3 扩展）数据源

> 该指标组（见 `config/indicators.yaml` 的 `global_collapse_risk:` 与
> `lu-qiyuan-analysis/references/collapse-risk-indicators.md`）监测全球宏观级"套息→美元流动性→
> 地缘能源→非美压力→风险情绪"级联。多数全球指标**无可靠免费实时源**，`collector.fetch_global_collapse_risk()`
> 对可用项 best-effort 拉取、对不可用项优雅降级（记 `None` / `manual`），绝不编造。

### 7.1 数值型指标 — akshare 候选函数（best-effort，待本机+网络验证）

| 指标 | akshare 候选函数 | 取数逻辑 | 状态 |
|------|------------------|----------|------|
| USD/JPY | `forex_spot_em()` | 过滤 `代码=="USDJPY"` 或名称含"美元日元"，取`最新价` | 预计可用 ✅ |
| US10Y | `bond_zh_us_rate()` | 取最新行含"美国…10年"列 | 预计可用 ✅ |
| JGB10Y | `macro_japan_yield_curve()` | 取含"10"列 | 待验证 ⚠️ |
| 美日利差 | 由 US10Y − JGB10Y 计算 | — | 取决于两者 |
| DXY | `macro_usa_dollar_index()` | master 中已移除（见第三节） | 大概率降级 ❌ |
| Brent | `macro_oil_brent()` | 取最新值 | 待验证 ⚠️ |
| USD/KRW | `forex_spot_em()` | 过滤 `代码=="USDKRW"` 或名称含"美元韩元" | 预计可用 ✅ |
| VIX | `stock_us_spot_em()` | 过滤名称含"VIX" | 待验证 ⚠️ |
| FRA-OIS | （无免费源） | 需专业/订阅终端 | 标记 `manual` |

> 说明：除 `forex_spot_em` 外，其余全球函数未经逐函数核对，实跑时若某函数不存在会抛
> `AttributeError`，采集器捕获后将该项记 `missing`，不影响其它指标与整体流水线。

### 7.2 定性 / 催化项 — 由用户或订阅源维护

无免费实时源、且属"定性信号 / 突发催化"的指标（CFTC 日元持仓、美联储 SRF、新兴市场外储、
新兴市场 CDS、三项地缘硬信号），**不自动采集**，改由 `data/qualitative_state.json` 人工/订阅源置位：

```json
{
  "cftc_jpy_unwind": false,
  "geopolitical": {"hormuz": false, "mideast_export_cut": false, "us_iran_conflict": false},
  "transmission": {"northbound_4w_outflow": false, "cny_weak_but_pboc": false, "domestic_credit_tightening": false}
}
```

- 三项 `geopolitical` 为**坍缩重大催化项**：任一为 `true` → 判定直接跳至"加速坍缩预警"。
- `cftc_jpy_unwind` 为套息平仓前兆信号；`transmission` 三项为"国内传导屏障观测"，不触发崩盘阈值，
  仅用于区分外部冲击与本土系统性风险。
- 文件缺失时 `collector._load_qualitative_state()` 返回全 `false` 默认值，报告标注"未触发"。

### 7.3 判定逻辑位置

- 分级（watch/warm/critical）与阶段定级（平稳/温和压力/风险升温/加速坍缩预警）在
  `calculator.compute_collapse_risk()` 完成，阈值全部来自 `indicators.yaml`，改阈值无需动代码。
- 简易判定规则（≥4 临界 / ≥3 升温含日元原油美债 / 地缘催化）见 `collapse-risk-indicators.md` 第五节。
