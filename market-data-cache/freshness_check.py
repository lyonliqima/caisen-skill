#!/usr/bin/env python3
"""freshness_check.py — 背景数据新鲜度闸门（Q-T2 的机器化执行器）

把 `references/数据时效与准确性闸门-20260913.md` 的 Q-T2「频率—保鲜期对照表」
从「写在文档里的规则」变成「跑得起来的闸机」。

**为什么需要它**：Q-T2 明写「指数/个股/期货行情：保鲜期 1 个交易日，超期即重抓，
不得沿用昨日」，但该闸门位于 SKILL.md 第1.5步——分析**已经开跑之后**才查。
且 `market-data-cache/latest.py` 只按文件 mtime 取最新一份，**不判过期**
（丢一份 8 月的缓存进去照样返回）。结果就是「有制度、没闸机」。

本闸机的动作：开工**之前**先体检 → 过期项给出可复制粘贴的重跑命令
→ `--require-fresh` 时阻断级不达标即 exit 2，不许进入后续步骤。

用法:
    python3 market-data-cache/freshness_check.py                # 体检报告（不阻断）
    python3 market-data-cache/freshness_check.py --require-fresh # 阻断级过期即 exit 2（第0步闸门）
    python3 market-data-cache/freshness_check.py --json          # 机器可读
    python3 market-data-cache/freshness_check.py --auto-refetch  # 对可重跑项自动重跑
    python3 market-data-cache/freshness_check.py --strict        # 把 warn 级也升级为阻断
    python3 market-data-cache/freshness_check.py --self-test     # 自测（改本脚本后必跑）

    # 回溯体检（复盘某个历史时点的数据新鲜度）
    python3 market-data-cache/freshness_check.py --now "2026-10-09T17:00"

退出码:
    0 = 无阻断级问题（可能有 warn 级提示）
    2 = 存在阻断级过期/缺失
    3 = 配置或环境错误（日历文件缺失/损坏等）

依赖: Python 3.8+ 标准库。无第三方依赖。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CALENDAR_PATH = ROOT / "market-data-cache" / "trade_calendar.json"

# 收盘后可取当日数据的时点（A股 15:00 收盘，行情/资金流落库留 1 小时余量）
MARKET_CLOSE_HOUR = 16

# ── 受管数据源登记表 ────────────────────────────────────────────────────────
# cadence: daily = 期望数据日必须等于「最近一个已收盘交易日」，超期即 stale
#          weekly / monthly = 按自然日保鲜期判定
# severity: block = 过期即阻断（--require-fresh 生效时为 exit 2）
#           warn  = 过期只提示（这类源允许降级为分析时实时补拉）
SOURCES = [
    {
        "key": "briefing",
        "label": "背景包（12 专家共享）",
        "glob": "_runs/briefing/*.json",
        "date_field": "date",
        "cadence": "daily",
        "severity": "block",
        "refetch": None,
        "refetch_hint": "需由「每日背景包预取」定时任务或 agent 重跑"
                        "（规范见 caisen-10-experts-analyst/references/背景包规范-*.md）",
    },
    {
        "key": "market_cache",
        "label": "大盘行情缓存（指数/板块/资金流）",
        "glob": "market-data-cache/cache/*.json",
        "date_field": "date",
        "cadence": "daily",
        "severity": "warn",
        "refetch": ["python3", "market-data-cache/fetch_daily.py", "--force"],
        "refetch_hint": "⚠️ 须在能直连行情源的机器上跑（沙箱对行情 API 约 4% 通过率）",
    },
    {
        "key": "ocmacro",
        "label": "宏观政策数据（TACO / 地产四件套）",
        "glob": "ocmacro-feed/data/digest-*.json",
        "date_field": None,
        "filename_date_regex": r"digest-(\d{4}-\d{2}-\d{2})\.json",
        "cadence": "daily",
        "severity": "warn",
        "refetch": ["python3", "ocmacro-feed/ocmacro_feed.py", "digest", "--json"],
        "refetch_hint": None,
    },
]


# ── 交易日历 ────────────────────────────────────────────────────────────────
class Calendar:
    """A股交易日历。数据来自 trade_calendar.json（westock-mcp 实测导出）。

    超出 coverage 覆盖范围时**自动降级为「仅排除周六周日」**并置 degraded=True——
    降级信息会出现在报告里，不静默。
    """

    def __init__(self, days: set, coverage: tuple, degraded_from: str) -> None:
        self._days = days
        self.coverage = coverage
        self.degraded = False
        self._coverage_note = ""
        self._degraded_from = degraded_from

    @classmethod
    def load(cls, path: Path) -> "Calendar":
        if not path.exists():
            raise FileNotFoundError(
                f"交易日历缺失：{path}\n"
                f"  请用 westock-mcp data_trade_calendar(market='hs', year=<年>, trading_only=true) 重新导出"
            )
        obj = json.loads(path.read_text(encoding="utf-8"))
        days = {d for d in obj.get("trading_days", [])}
        cov = tuple(obj.get("coverage", ["", ""]))
        return cls(days, cov, str(path))

    def _in_coverage(self, d: dt.date) -> bool:
        if not self.coverage or not self.coverage[0]:
            return False
        return self.coverage[0] <= d.isoformat() <= self.coverage[1]

    def is_trading_day(self, d: dt.date) -> bool:
        if not self._in_coverage(d):
            # 降级：仅排除周末（节假日无法识别 → 可能把休市日误判为交易日）
            self.degraded = True
            return d.weekday() < 5
        return d.isoformat() in self._days

    def prev_trading_day(self, d: dt.date) -> dt.date:
        cur = d
        for _ in range(30):
            cur -= dt.timedelta(days=1)
            if self.is_trading_day(cur):
                return cur
        return cur  # 30 天内无交易日属异常，返回兜底值

    def count_trading_days_between(self, start: dt.date, end: dt.date) -> int:
        """(start, end] 之间的交易日数，用于报「落后 N 个交易日」。"""
        if end <= start:
            return 0
        n, cur = 0, start
        while cur < end:
            cur += dt.timedelta(days=1)
            if self.is_trading_day(cur):
                n += 1
        return n


def expected_data_date(now: dt.datetime, cal: Calendar) -> tuple:
    """返回 (期望数据日, 人类可读理由)。

    规则（Q-T1 数据日确认的机器化）：
      1. 今天是交易日 且 当前时间 >= 16:00  → 今天（已收盘，今日数据应已可用）
      2. 今天是交易日 且 当前时间 <  16:00  → 上一交易日（今日尚未收盘）
      3. 今天不是交易日                      → 上一交易日
    """
    today = now.date()
    if cal.is_trading_day(today):
        if now.hour >= MARKET_CLOSE_HOUR:
            return today, f"{today}（周{'一二三四五六日'[today.weekday()]}，交易日·已收盘）"
        prev = cal.prev_trading_day(today)
        return prev, f"{prev}（周{'一二三四五六日'[prev.weekday()]}）· 今日 {today} 尚未收盘（<{MARKET_CLOSE_HOUR}:00）"
    prev = cal.prev_trading_day(today)
    return prev, f"{prev}（周{'一二三四五六日'[prev.weekday()]}）· 今日 {today} 非交易日"


# ── 数据源发现与判定 ────────────────────────────────────────────────────────
def discover(src: dict) -> tuple:
    """返回 (最新产物路径, 其数据日, 共发现几个)。找不到 → (None, None, 0)。"""
    files = sorted(ROOT.glob(src["glob"]), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None, None, 0
    path = files[0]
    data_date = None
    if src.get("date_field"):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            raw = obj.get(src["date_field"])
            if raw:
                data_date = dt.date.fromisoformat(str(raw)[:10])
        except (json.JSONDecodeError, ValueError, OSError):
            data_date = None
    elif src.get("filename_date_regex"):
        m = re.search(src["filename_date_regex"], path.name)
        if m:
            try:
                data_date = dt.date.fromisoformat(m.group(1))
            except ValueError:
                data_date = None
    return path, data_date, len(files)


def judge(src: dict, data_date, expected: dt.date, cal: Calendar, now: dt.datetime) -> dict:
    """判新鲜度。返回 dict(status, lag_days, lag_trading_days, detail)。"""
    if data_date is None:
        return {"status": "missing", "lag_days": None, "lag_td": None,
                "detail": "无产物文件" if expected else "产物存在但数据日无法解析"}

    cadence = src["cadence"]
    if cadence == "daily":
        if data_date >= expected:
            return {"status": "fresh", "lag_days": 0, "lag_td": 0, "detail": "数据日达标"}
        lag_td = cal.count_trading_days_between(data_date, expected)
        return {"status": "stale", "lag_days": (expected - data_date).days, "lag_td": lag_td,
                "detail": f"落后 {lag_td} 个交易日"}

    # 周频 / 月频：按自然日保鲜期
    limit_days = 14 if cadence == "weekly" else 45
    lag = (now.date() - data_date).days
    if lag <= limit_days:
        return {"status": "fresh", "lag_days": lag, "lag_td": None,
                "detail": f"距数据日 {lag} 天 ≤ 保鲜期 {limit_days} 天"}
    return {"status": "stale", "lag_days": lag, "lag_td": None,
            "detail": f"距数据日 {lag} 天 > 保鲜期 {limit_days} 天"}


def run_refetch(src: dict, dry: bool = False) -> str:
    cmd = src.get("refetch")
    if not cmd:
        return "（无自动重跑命令，见 refetch_hint）"
    printable = " ".join(cmd)
    if dry:
        return f"[dry-run] {printable}"
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=180)
        tail = (p.stdout or p.stderr or "").strip().splitlines()
        tail = tail[-1] if tail else "(无输出)"
        return f"exit={p.returncode} · {tail}"
    except subprocess.TimeoutExpired:
        return "重跑超时（180s）"
    except FileNotFoundError as e:
        return f"重跑失败：{e}"


# ── 报告 ────────────────────────────────────────────────────────────────────
STATUS_TAG = {"fresh": "[新鲜]", "stale": "[过期]", "missing": "[缺失]"}
BLOCK_STATUS = {"stale", "missing"}


def build_report(now: dt.datetime, cal: Calendar, auto_refetch: bool) -> dict:
    expected, reason = expected_data_date(now, cal)
    rows, blockers = [], 0

    for src in SOURCES:
        path, data_date, n_found = discover(src)
        verdict = judge(src, data_date, expected, cal, now)
        blocked = verdict["status"] in BLOCK_STATUS and src["severity"] == "block"
        if blocked:
            blockers += 1
        row = {
            "key": src["key"],
            "label": src["label"],
            "severity": src["severity"],
            "status": verdict["status"],
            "detail": verdict["detail"],
            "lag_trading_days": verdict["lag_td"],
            "path": str(path.relative_to(ROOT)) if path else None,
            "data_date": data_date.isoformat() if data_date else None,
            "files_found": n_found,
            "blocking": blocked,
            "refetch_cmd": " ".join(src["refetch"]) if src.get("refetch") else None,
            "refetch_hint": src.get("refetch_hint"),
            "refetch_result": None,
        }
        if auto_refetch and verdict["status"] in BLOCK_STATUS and src.get("refetch"):
            row["refetch_result"] = run_refetch(src)
        rows.append(row)

    return {
        "checked_at": now.isoformat(timespec="seconds"),
        "expected_data_date": expected.isoformat(),
        "expected_reason": reason,
        "calendar_degraded": cal.degraded,
        "calendar_coverage": list(cal.coverage),
        "sources": rows,
        "blocking_count": blockers,
        "stale_count": sum(1 for r in rows if r["status"] != "fresh"),
    }


def print_human(rep: dict, strict: bool, require_fresh: bool) -> None:
    print(f"=== 背景数据新鲜度体检 · {rep['checked_at']} ===")
    print(f"可观测数据日：{rep['expected_reason']}")
    if rep["calendar_degraded"]:
        print(f"⚠️ 日历降级：{rep['expected_data_date']} 超出本地日历覆盖 "
              f"{rep['calendar_coverage']}，已退化为「仅排除周末」——节假日可能误判，结论仅供参考")
    print()

    for r in rep["sources"]:
        flag = STATUS_TAG[r["status"]]
        sev = "阻断" if r["severity"] == "block" else "提示"
        date_s = r["data_date"] or "—"
        print(f"{flag} {r['label']} ｜ 数据日 {date_s} ｜ [{sev}] {r['detail']}")
        if r["status"] != "fresh":
            print(f"       现行产物：{r['path'] or '无（该源从未落盘）'}")
            if r["refetch_cmd"]:
                print(f"       重跑命令：{r['refetch_cmd']}")
            if r["refetch_hint"]:
                print(f"       ↳ {r['refetch_hint']}")
            if r["refetch_result"]:
                print(f"       已自动重跑：{r['refetch_result']}")
    print()

    n_stale = rep["stale_count"]
    n_block = rep["stale_count"] if strict else rep["blocking_count"]
    armed = strict or require_fresh

    if n_stale == 0:
        print("结论：全部新鲜，可开工。")
    elif n_block == 0:
        print(f"结论：{n_stale} 项过期（均为提示级，可降级为分析时实时补拉）· 不阻断。")
    elif armed:
        print(f"结论：{n_block} 项阻断级不达标 → 不得开工（闸门已武装，exit 2）。")
    else:
        print(f"结论：{n_block} 项阻断级不达标 → 当前为「只报告不拦截」；"
              f"加 --require-fresh 即在此处 exit 2 拦下。")


def run_self_test() -> int:
    """自测：日历与期望数据日逻辑的关键分支。改本脚本后必跑。"""
    fails = []

    def ck(cond, msg):
        if not cond:
            fails.append(msg)

    cal = Calendar.load(CALENDAR_PATH)
    d = dt.date

    ck(len(cal._days) == 242, f"2026 交易日应为 242，实为 {len(cal._days)}")
    ck(cal.is_trading_day(d(2026, 10, 15)) is True, "2026-10-15（周四）应为交易日")
    ck(cal.is_trading_day(d(2026, 10, 17)) is False, "2026-10-17（周六）应为非交易日")
    ck(cal.is_trading_day(d(2026, 10, 1)) is False, "2026-10-01（国庆）应为非交易日")
    ck(cal.is_trading_day(d(2026, 2, 17)) is False, "2026-02-17（春节）应为非交易日")
    ck(cal.is_trading_day(d(2026, 9, 25)) is False, "2026-09-25（中秋）应为非交易日")
    ck(cal.prev_trading_day(d(2026, 10, 8)) == d(2026, 9, 30),
       "2026-10-08 的上一交易日应为 2026-09-30（跨国庆）")
    ck(cal.prev_trading_day(d(2026, 10, 19)) == d(2026, 10, 16),
       "2026-10-19（周一）的上一交易日应为 2026-10-16（周五）")

    # 期望数据日三分支
    e, _ = expected_data_date(dt.datetime(2026, 10, 15, 23, 0), cal)
    ck(e == d(2026, 10, 15), f"交易日盘后应期望当日，实得 {e}")
    e, _ = expected_data_date(dt.datetime(2026, 10, 15, 10, 0), cal)
    ck(e == d(2026, 10, 14), f"交易日盘中应期望上一交易日，实得 {e}")
    e, _ = expected_data_date(dt.datetime(2026, 10, 17, 12, 0), cal)
    ck(e == d(2026, 10, 16), f"周末应期望上一交易日（周五），实得 {e}")
    e, _ = expected_data_date(dt.datetime(2026, 10, 8, 9, 0), cal)
    ck(e == d(2026, 9, 30), f"节后开盘前应期望节前最后交易日，实得 {e}")

    ck(cal.count_trading_days_between(d(2026, 10, 14), d(2026, 10, 15)) == 1,
       "10-14 → 10-15 应为 1 个交易日")

    # 降级分支：超覆盖范围应退化为仅排除周末
    cal2 = Calendar(set(), ("2026-01-01", "2026-12-31"), "test")
    ck(cal2.is_trading_day(d(2027, 3, 3)) is True, "2027 工作日应降级判为交易日")
    ck(cal2.degraded is True, "超覆盖范围应置 degraded")

    if fails:
        print("自测失败：")
        for f in fails:
            print(f"  ✗ {f}")
        return 1
    print(f"自测通过：{len(['calendar','expect'])} 组断言全部成立（日历 242 日 + 期望数据日 4 分支 + 降级分支）")
    return 0


# ── 入口 ────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="背景数据新鲜度闸门（Q-T2 机器化）")
    ap.add_argument("--require-fresh", action="store_true",
                    help="存在阻断级过期/缺失即 exit 2（第0步闸门用法）")
    ap.add_argument("--strict", action="store_true",
                    help="把 warn 级也升级为阻断")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--auto-refetch", action="store_true", help="对可重跑项自动执行重跑命令")
    ap.add_argument("--now", default=None, help="回溯体检的时点 ISO8601（如 2026-10-09T17:00）")
    ap.add_argument("--self-test", action="store_true", help="跑自测并退出")
    args = ap.parse_args()

    if args.self_test:
        return run_self_test()

    try:
        cal = Calendar.load(CALENDAR_PATH)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[freshness] 配置错误：{e}", file=sys.stderr)
        return 3

    now = dt.datetime.fromisoformat(args.now) if args.now else dt.datetime.now()

    rep = build_report(now, cal, auto_refetch=args.auto_refetch)

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print_human(rep, strict=args.strict, require_fresh=args.require_fresh)

    n_block = rep["stale_count"] if args.strict else rep["blocking_count"]
    if n_block > 0 and (args.require_fresh or args.strict):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
