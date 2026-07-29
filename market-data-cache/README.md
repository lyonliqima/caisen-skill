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

## 接入的 skill
- `integrated-market-analysis` —— 分析前先 `latest.py` 读缓存当背景，仅目标股实时拉
- `caisen-10-experts-analyst` —— 同上

## ⚠️ 运行环境
WorkBuddy 沙箱对行情 API 有硬性 ~4% 通过率上限（与并发无关），东财在沙箱被网络层掐断。
**务必在你本机**用 crontab（macOS/Linux）或任务计划程序（Windows）每日盘后触发，再把
`cache/` 目录同步给 WorkBuddy 读。不要在沙箱内依赖实时拉取全市场。
