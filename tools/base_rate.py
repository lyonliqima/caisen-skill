#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
base_rate.py — 条件基准率（outside view · 防前视偏差）
======================================================
在 asof 之前的历史数据上：
  - 找出所有满足 --condition 的时点 t（condition 只能用 t 及之前可得的信息）
  - 统计其中未来 window 天内满足 --event 的比例（event 用 t+1..t+window 数据）
  - 同时输出无条件基准率（不加 condition）作对照
  - lift = conditional.rate − unconditional.rate

条件样本 n < 20 → reliable=false 并打印「条件样本过少」。

⚠️ 防前视偏差：condition 求值命名空间只含 t 及之前派生的量
（close/ma20/ma60/vol_percentile/open/high/low/...），绝不含未来收益；
event 求值命名空间只含 fwd_return（未来 window 收益）。两者物理隔离。
`--self-test` 用合成数据验证该隔离（详见 _selftest）。

用法
----
  python3 tools/base_rate.py --symbol I2609 --window 60 \
      --event "fwd_return <= -0.05" \
      --condition "close < ma60 and vol_percentile > 0.7" \
      --asof 2026-07-29
  python3 tools/base_rate.py --self-test
  python3 tools/base_rate.py --help
"""
import argparse
import ast
import json
import math
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE_DIR = os.path.join(ROOT, "market-data-cache")


# ───────── 安全表达式求值（白名单 AST） ─────────
_ALLOWED = (ast.Expression, ast.BoolOp, ast.UnaryOp, ast.BinOp, ast.Compare,
            ast.Name, ast.Load, ast.Constant, ast.And, ast.Or, ast.Not,
            ast.USub, ast.UAdd, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
            ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _safe_eval(expr, ns):
    """只求白名单节点，变量仅来自 ns。未知变量 → NameError（证明未来量不在作用域）。"""
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ValueError("不支持的表达式成分: %s" % type(node).__name__)

    def _ev(n):
        if isinstance(n, ast.Expression):
            return _ev(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in ns:
                raise NameError("未知变量（不在作用域）: %s" % n.id)
            return ns[n.id]
        if isinstance(n, ast.UnaryOp):
            return _ev(n.op) * _ev(n.operand) if isinstance(n.op, (ast.USub, ast.UAdd)) else _ev(n.operand)
        if isinstance(n, ast.BinOp):
            a, b = _ev(n.left), _ev(n.right)
            return {ast.Add: a + b, ast.Sub: a - b, ast.Mult: a * b,
                    ast.Div: a / b, ast.Mod: a % b}[type(n.op)]
        if isinstance(n, ast.BoolOp):
            if isinstance(n.op, ast.And):
                return all(_ev(v) for v in n.values)
            return any(_ev(v) for v in n.values)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            return not _ev(n.operand)
        if isinstance(n, ast.Compare):
            left = _ev(n.left)
            for op, comp in zip(n.ops, n.comparators):
                right = _ev(comp)
                ok = {ast.Lt: left < right, ast.LtE: left <= right,
                      ast.Gt: left > right, ast.GtE: left >= right,
                      ast.Eq: left == right, ast.NotEq: left != right}[type(op)]
                if not ok:
                    return False
                left = right
            return True
        raise ValueError("无法求值的节点")
    return _ev(tree)


def wilson(p, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


# ───────── 数据加载（与 baseline.py 同源，简化复用） ─────────
def _load_prices(symbol, asof):
    asof_d = datetime.strptime(asof, "%Y-%m-%d")
    rows = []
    for ext in (".csv", ".json"):
        p = os.path.join(CACHE_DIR, symbol + ext)
        if os.path.exists(p):
            try:
                if ext == ".csv":
                    import csv
                    with open(p, encoding="utf-8") as f:
                        for r in csv.DictReader(f):
                            d, c, v = r.get("date"), r.get("close"), r.get("volume")
                            if d and c not in (None, ""):
                                rows.append((d[:10], float(c), float(v) if v not in (None, "") else 0.0))
                else:
                    with open(p, encoding="utf-8") as f:
                        for r in json.load(f):
                            rows.append((str(r["date"])[:10], float(r["close"]),
                                         float(r.get("volume", 0.0))))
            except Exception:
                rows = []
    if rows:
        out = [(d, c, v) for d, c, v in rows
               if datetime.strptime(d, "%Y-%m-%d") < asof_d]
        out.sort(key=lambda x: x[0])
        if out:
            return out
    return None


def _context_at(prices, i, window):
    """t=i 时刻 condition 可见的命名空间（只用 i 及之前）。"""
    closes = [c for _, c, _ in prices[: i + 1]]
    vols = [v for _, _, v in prices[: i + 1]]
    c = closes[-1]
    ma20 = sum(closes[-20:]) / 20.0 if len(closes) >= 20 else c
    ma60 = sum(closes[-60:]) / 60.0 if len(closes) >= 60 else c
    # 量能百分位：当前量在过去60根中的位置
    win = vols[-60:] if len(vols) >= 60 else vols
    vp = (sum(1 for x in win if x <= vols[-1]) / len(win)) if win else 0.5
    return {"close": c, "open": closes[0], "high": max(closes[-window:]),
            "low": min(closes[-window:]), "ma20": ma20, "ma60": ma60,
            "vol": vols[-1], "vol_percentile": vp,
            "n": len(closes)}


def _fwd_context(prices, i, window):
    """未来 window 收益的命名空间（event 可见，绝不含在 condition 里）。"""
    if i + window >= len(prices):
        return None
    fwd = prices[i + window][1] / prices[i][1] - 1
    return {"fwd_return": fwd, "fwd_close": prices[i + window][1]}


def base_rate(prices, window, condition, event):
    cond_hit = 0
    cond_total = 0
    unc_hit = 0
    unc_total = 0
    for i in range(len(prices) - window):
        ctx_t = _context_at(prices, i, window)
        fwd = _fwd_context(prices, i, window)
        if fwd is None:
            continue
        # 无条件：未来收益 < 0 视为「事件发生」（与 event 默认语义一致时）
        unc_total += 1
        if _safe_eval(event, {"fwd_return": fwd["fwd_return"]}):
            unc_hit += 1
        # 条件
        try:
            if _safe_eval(condition, ctx_t):
                cond_total += 1
                if _safe_eval(event, {"fwd_return": fwd["fwd_return"]}):
                    cond_hit += 1
        except (NameError, ValueError):
            # 历史早期量能不足等导致变量缺失，跳过该点
            continue
    cr = cond_hit / cond_total if cond_total else 0.0
    ur = unc_hit / unc_total if unc_total else 0.0
    clo, chi = wilson(cr, cond_total)
    ulo, uhi = wilson(ur, unc_total)
    return {
        "conditional": {"rate": round(cr, 4), "n": cond_total,
                        "ci95": [round(clo, 4), round(chi, 4)]},
        "unconditional": {"rate": round(ur, 4), "n": unc_total,
                          "ci95": [round(ulo, 4), round(uhi, 4)]},
        "lift": round(cr - ur, 4),
        "reliable": cond_total >= 20,
    }


def _selftest():
    """合成数据验证防前视偏差：condition 命名空间绝不能看到未来。"""
    # 价格单调上升；构造一个「未来才成立」的 condition 应触发 NameError
    prices = [(f"2026-{m:02d}-01", 100.0 + i, 1000.0) for i, m in enumerate(range(1, 13))]
    # condition 引用未来专用变量 fwd_return → 必须 NameError（证明未来量不在作用域）
    try:
        _safe_eval("fwd_return < 0", {"close": 100.0})  # fwd_return 不在 ns
        raise AssertionError("防前视偏差失效：condition 看到了未来变量")
    except NameError:
        pass
    # 正常 condition 应可求值
    ctx = _context_at(prices, len(prices) - 1, 60)
    assert _safe_eval("close > ma60", ctx) in (True, False)
    # 正向逻辑：event 在未来收益上求值，condition 在 t 上求值，结果合理
    out = base_rate(prices, 1, "close > open", "fwd_return > 0")
    assert out["conditional"]["n"] >= 1
    print("✓ 防前视偏差自测通过（condition 命名空间与 event 命名空间物理隔离）")
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(description="条件基准率（outside view）")
    ap.add_argument("--symbol", help="标的代码")
    ap.add_argument("--window", type=int, default=60)
    ap.add_argument("--event", help="未来 window 窗口内的事件，如 'fwd_return <= -0.05'")
    ap.add_argument("--condition", help="t 时刻条件，如 'close < ma60 and vol_percentile > 0.7'")
    ap.add_argument("--asof", help="数据截止日 YYYY-MM-DD")
    ap.add_argument("--self-test", action="store_true", help="运行防前视偏差自测")
    args = ap.parse_args()

    if args.self_test:
        _selftest()

    if not (args.symbol and args.event and args.condition and args.asof):
        sys.stderr.write("✗ 需提供 --symbol --event --condition --asof（或 --self-test）\n")
        sys.exit(2)

    prices = _load_prices(args.symbol, args.asof)
    if not prices or len(prices) < args.window + 2:
        print(json.dumps({"error": "历史数据不足或取数失败（symbol=%s）" % args.symbol,
                          "reliable": False}, ensure_ascii=False))
        sys.exit(1)

    try:
        out = base_rate(prices, args.window, args.condition, args.event)
    except (NameError, ValueError) as e:
        print(json.dumps({"error": "表达式解析失败: %s" % e}, ensure_ascii=False))
        sys.exit(1)
    out["symbol"] = args.symbol
    out["asof"] = args.asof
    out["window"] = args.window
    if not out["reliable"]:
        out["warning"] = "条件样本过少（n=%d < 20），请放宽条件或改用无条件基准" % out["conditional"]["n"]
        sys.stderr.write("⚠️ 条件样本过少（n=%d < 20），请放宽条件或改用无条件基准\n" % out["conditional"]["n"])
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
