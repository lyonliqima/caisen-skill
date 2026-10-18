# market-data-cache · 市场数据预取缓存

把「通用市场背景数据」（大盘指数 / 行业板块 / 资金流向）每天跑一次落盘，**分析时读缓存、只对目标个股实时补拉**，绕开每次分析都走的「东财→新浪→腾讯」降级重试链（主要 I/O 延迟来源）。

## 用法

```bash
# 本机跑（沙箱限流，必须在能直连行情源的机器上跑）
python3 market-data-cache/fetch_daily.py            # 拉今天 → cache/<今天>.json
python3 market-data-cache/fetch_daily.py --force    # 覆盖重拉

# 分析时定位最新缓存
python3 market-data-cache/latest.py                 # 路径 + 摘要
python3 market-data-cache/latest.py --path          # 只打印路径
```

## 多源容错链
`fetch_daily.py` 按顺序尝试 **东财 → 新浪 → 腾讯**，任一可用即返回并记下 `sources_used`。
- 单源失败不整体失败；全部失败则 `indices` 为空，分析 skill 自动降级为实时补拉。

## 缓存 JSON 结构
```json
{
  "date": "2026-07-09",
  "generated_at": "2026-07-09T16:30:00",
  "sources_used": ["eastmoney"],
  "indices": {"上证指数": {"price":3210.5,"chg_pct":0.85,"amount":2.8e11}},
  "sectors": [{"name":"半导体","chg_pct":2.3,"rank":1}],
  "flows": {"northbound":"unavailable","southbound":{}}
}
```

## 新鲜度闸门（freshness_check.py · 2026-10-15 追加）

> **为什么追加**：本 README 早就写了「每天跑一次落盘、分析时读缓存」，
> 但 `latest.py` 只按文件 **mtime** 取最新一份、**不判过期**——一份 8 月的缓存丢在那里
> 照样被当成「最新背景」采用。承诺的机制**从未有执行者**：实测 `cache/` 目录
> 在 2026-10-15 之前**从未产出过任何文件**。有说明书，没有闸机。

`freshness_check.py` 把 `caisen-10-experts-analyst/references/数据时效与准确性闸门-20260913.md`
的 **Q-T2 保鲜期表**变成可执行的闸门：判断「此刻应当能拿到的最新数据日」，逐源比对。

```bash
cd "$CAISEN_ROOT"
python3 market-data-cache/freshness_check.py                 # 体检报告（只报告不拦截）
python3 market-data-cache/freshness_check.py --require-fresh  # 阻断级不达标 → exit 2
python3 market-data-cache/freshness_check.py --auto-refetch   # 对可重跑项自动重跑
python3 market-data-cache/freshness_check.py --json           # 机读
python3 market-data-cache/freshness_check.py --now "2026-10-09T17:00"   # 回溯体检
python3 market-data-cache/freshness_check.py --self-test      # 自测（改脚本后必跑）
```

**期望数据日判据**：交易日盘后（≥16:00）→ 当日；交易日盘中或非交易日 → 上一交易日。
**受管源**：`_runs/briefing/*.json`（背景包，block 级）、`cache/*.json`（本目录，warn 级）、
`ocmacro-feed/data/digest-*.json`（warn 级）。`--strict` 可把 warn 全部升级为阻断。

**交易日历**：`trade_calendar.json`（westock-mcp 实测导出，2026 全年 242 个交易日）。
超出 coverage 时脚本自动降级为「仅排除周末」**并在输出中标注**，不静默；**跨年须重新导出**。

**退出码**：`0` 无阻断 · `2` 有阻断级过期/缺失 · `3` 配置错误（日历缺失/损坏）。

---

## 接入的 skill
- `integrated-market-analysis` —— 分析前先 `latest.py` 读缓存当背景，仅目标股实时拉
- `caisen-10-experts-analyst` —— 同上

## ⚠️ 运行环境（层 A 必须在本机跑）
WorkBuddy 沙箱对行情 API 有硬性 ~4% 通过率上限（与并发无关），东财在沙箱被网络层掐断。
**务必在你本机**用 crontab（macOS/Linux）或任务计划程序（Windows）每日盘后触发，再把
`cache/` 目录同步给 WorkBuddy 读。不要在沙箱内依赖实时拉取全市场。

**crontab 一键配置**（每交易日 16:10，节假日由脚本/闸门自判）：

```cron
10 16 * * 1-5 cd "/Users/weihaoli/Desktop/蔡森 skill" && python3 market-data-cache/fetch_daily.py --force >> /tmp/caisen_fetch.log 2>&1
```

安装：`crontab -e` 粘贴上面一行保存。验证：

```bash
# ① 手动先跑一次（确认真的能取到数，而不是只有 --help 通过）
cd "/Users/weihaoli/Desktop/蔡森 skill" && python3 market-data-cache/fetch_daily.py --force
# ② 确认产物真的出现了（这一步不能省）
ls -la market-data-cache/cache/
# ③ 让闸门复验
python3 market-data-cache/freshness_check.py
```

> ⚠️ **必须验证 ②**：框架 2026-09-20 已栽过一次「只看 `--help` 就判定可运行」的假结论
> （见 SKILL.md 第0步第7条纪律）。**脚本存在 ≠ 脚本跑通 ≠ 产物落盘**，三者要分别验证。
