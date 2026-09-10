---
name: stock-screener
description: A股全市场统一选股引擎，三策略交叉验证。当用户要求「推荐今天的股票」「选几只好票」「帮我找股票」「今天买什么」「扫全市场」「找破底翻」「找碗口反弹」「跑选股」时调用。整合破底翻（左侧底部反转）、碗口反弹（右侧趋势回踩，移植自 a-share-quant-selector）、Mi姐趋势筹码情绪三维（严格确认）三套策略，全市场约5000只逐票扫描，交叉命中加权，输出带止损位/目标位/盈亏比的排名。可作为 caisen-10-experts-analyst 的漏斗前段：先量化粗筛出 Top 20，再交给十二专家圆桌做深度研判。
agent_created: true
---

# A股统一选股引擎（破底翻 × 碗口反弹 × Mi姐三维）

位置：`/Users/weihaoli/Desktop/蔡森 skill/stock-screener/`（桌面主副本，镜像同步到 `~/.workbuddy/skills/`）

## 一句话用法

```bash
cd /Users/weihaoli/Desktop/蔡森 skill/stock-screener
/Users/weihaoli/.workbuddy/binaries/python/envs/default/bin/python3 screener.py
```

常用参数：
```bash
--limit 200         # 只扫前200只（快速试跑）
--top 30            # 控制台显示前30名（默认20）
--no-mi             # 跳过Mi姐三维（省一半时间）
--no-cache          # 忽略本地缓存强制重拉
--workers 12        # 并发线程数（默认12）
--min-amount 5000万 # 提高成交额门槛
--min-price 3       # 提高最低价门槛
```

输出：控制台排名表 + CSV 落在 `stock-screener-output/<策略>_<日期>.csv`
（破底翻 / 碗口反弹 / Mi姐三维 / 综合 四份）

生成 HTML 报告（含漏斗图、命中率对比、Top 名单）：
```bash
/Users/weihaoli/.workbuddy/binaries/python/envs/default/bin/python3 report.py
```
产物 `stock-screener-output/选股报告_<日期>.html`，可直接双击打开。
**跑完 screener 再跑 report**，顺序不能反。

## 三套策略的分工（不要合并，不要只用一套）

| 策略 | 位置 | 核心逻辑 | 单独使用的弱点 |
|------|------|----------|----------------|
| **破底翻** | 左侧 | 底部区域创新低后翻回前低；或全程守住前低站稳N天 | 单边下跌市中假信号极多 |
| **碗口反弹** | 右侧 | 上升趋势中回踩到支撑 + J值超卖 + 近期有放量阳线 | 底部区域几乎筛不出票（要求短趋势线>多空线） |
| **Mi姐三维** | 确认 | 趋势/结构/时机/资金/情绪五模块全对齐才买入 | 命中率极低，常日可能全市场0只 |

**交叉验证是本引擎的核心 alpha**：
- 破底翻 ∩ 碗口反弹 = 底部结构已成立 + 趋势已转多 → 最强组合
- 任一策略 ∩ Mi姐买入 = 严格确认，假信号最少
- 综合分 = 最强策略分 + (命中策略数-1) × 12

## 评分与门槛

- 每个策略独立打 0-100 分，互不调整彼此阈值
- 盈亏比 < 2:1 的自动打八折（仍保留在表里，但排到后面）
- 前置过滤：ST/退市、价格 < 2元、当日成交额 < 3000万、北交所

## ⚠️ 数据源铁律（踩过的坑，不要重犯）

1. **禁止在多线程里调用 akshare**。akshare 内部用 `py_mini_racer`（V8 JS 引擎），
   线程不安全，并发调用会触发 C++ 层 `FATAL: Check failed: !pool->IsInitialized()`
   **直接崩溃进程，且 try/except 抓不到**。实测 2 线程就必崩。
   本模块数据获取已全部改为 urllib 直连，唯一保留的 akshare 调用
   （`stock_info_a_code_name` 代码表）在主线程单次执行并缓存。

2. **东方财富全线不可达**（沙箱代理 ProxyError），不要再加回来。
   可用通道只有三条：
   - 代码表：`ak.stock_info_a_code_name()`（交易所官网，5551只）
   - 实时行情：`hq.sinajs.cn`（批量，含成交额）
   - 日K：`money.finance.sina.com.cn/.../CN_MarketData.getKLineData`
     （与 `mi-analysis/data_feed.py` 同一条已验证通道）

3. **早前记录的「沙箱4%通过率」指的是新浪列表分页接口** `getHQNodeData`，
   与本模块用的个股日K接口不是同一条通道，后者实测 100% 可用。不要被旧结论误导。

4. **Mi姐输入必须把 date 统一成 datetime**。
   `module_A` 内部做 `_weekly_ma60(weekly).reindex(df["date"])`，
   日线若是字符串、周线是 Timestamp，reindex 结果全是 NaN，
   表现为「全市场一只多头都没有」且不报错，极难排查。

5. **空结果也必须写 CSV**（只写表头）。否则 `report.py` 的 `_latest()`
   会读到上一次运行的陈旧文件，把「本次 0 命中」误报成「命中 N 只」——
   这个 bug 真实发生过一次：Mi姐实测 0 只，报告却显示 33 只，
   连带把「市场普跌」的关键警示给吞掉了。

6. **放量倍数 > 20 倍一律剔除**。那不是资金进场，是复牌/除权导致的技术性跳变，
   但会被打分项判成最强信号（满分）。

7. **沙箱内运行会被 OUT_DIR mkdir 拦截**（2026-09-02 实锤）。WorkBuddy 沙箱代理禁止
   桌面 mkdir，`OUT_DIR.mkdir(exist_ok=True)` 抛 `PermissionError: EEXIST`。
   解法：`cp -r` 整个 stock-screener 到工作区（如 `~/WorkBuddy/<session>/screener-run`），
   把 `OUT_DIR = BASE.parent / "stock-screener-output"` 改成 `OUT_DIR = BASE / "stock-screener-output"`
   （指向工作区内），再跑。**只改工作区临时副本，桌面主副本不动。**
   另：本环境 zsh 下 `sed -i ''` 会把替换表达式误当文件名报错，改文件内容用 Edit 工具更稳。

## 参数校准说明（来自原仓库的两处陷阱）

移植 `Dzy-HW-XD/a-share-quant-selector` 的碗口反弹时，发现源码里
**文档注释、类默认参数、yaml 实际配置三者不一致**，实测以 yaml 为准：

| 参数 | 类默认值 | yaml实际值 | 采用 |
|------|---------|-----------|------|
| N（放量倍数） | 4 | **2** | 2 |
| M（回溯天数） | 15 | **30** | 30 |
| J_VAL | 30 | **20** | 20 |
| 多空线周期 | 注释写 5/10/20/30 | 实现用 **14/28/57/114** | 14/28/57/114 |

按类默认值跑，400 只样本里只有 1 只过得了「放量阳线」那一关。

另：原仓库用「总市值 40 亿」做门槛，这里改成「近20日日均成交额 ≥ 1 亿」——
新浪日K不返回股本，且成交额比市值更直接代表"能否从容进出"。

## 与 caisen-10-experts-analyst 的配合（漏斗模式）

用户说「推荐今天的股票」时，正确的执行顺序是**先量化后专家**：

```
第1步  本引擎全市场扫描 → Top 20 候选（几分钟，纯量化，零主观）
第2步  对 Top 20 逐票做风控排雷（risk-control-expert）
第3步  对存活的票启动十二专家圆桌深度研判
第4步  输出 HTML 报告
```

**不要反过来**：让十二专家去逐票分析 5000 只股票是不可能的，
也不要跳过第1步直接让专家拍脑袋选——那就失去了量化的覆盖面优势。

## 局限与诚实声明

- 本引擎只做**技术面+量能**筛选，不含基本面、财报、行业景气度
- 破底翻在系统性下跌中会连续产生假信号，需结合大盘环境判断
- 所有输出是候选名单，不是买入指令；止损位是纪律，不是建议
- 数据源为新浪免费接口，偶发缺失，结果以 CSV 为准并抽查验证
