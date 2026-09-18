#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
append.py — 研判评分卡 → 预测台账 追加器
=================================================
每次「股票/期货」方向性分析产出评分卡后，调用本脚本把一条记录追加进
predictions-ledger/ledger.jsonl（JSONL，逐行一个 JSON，便于追加与复盘）。

用法
----
  # 传 JSON 字符串（默认自动回填基准三字段 + 价格快照）
  python3 append.py --json '{"source_skill":"caisen-10-experts-analyst","methodology":"十二专家综合","asset_class":"A股个股","symbol":"600519 贵州茅台","direction":"多","target_range":"+5%~+15%","time_window":"60D","confidence":70,"falsification":"跌破1400","predictability":"低","market_regime":"震荡市","scenarios":{"bull_prob":50,"base_prob":30,"bear_prob":20},"position":"轻仓","consensus_part":"复苏预期","variant_part":"高端批价动销","evidence_votes":{"价量":"多","资金流":"中性","基本面":"多","政策":"中性","情绪":"多"},"independence_color":"🟢"}' \
        --entry-price 1480.0

  # 传 JSON 文件 / 管道
  python3 append.py --file rec.json
  cat rec.json | python3 append.py

  # 试运行（不写盘，仅打印）
  python3 append.py --json '...' --dry-run

  # 关闭自动基准回填
  python3 append.py --json '...' --no-auto-baseline

  # 写入前做量纲校验（提供数值则自动校验，❌ 则拒绝写入）
  python3 append.py --json '...' --current 1480 --falsification-price 1400 \
        --target-low 0.05 --target-high 0.15

  # 贝叶斯更新（PRED 8）：追加一条更新记录，不覆盖原始 confidence
  python3 append.py update --id P-20260729-001 --trigger "库存降幅3.2%，落入B分支" --new-confidence 55

价格快照闭环（2026-08-25 加固，强制）
--------------------------------------
新记录必须固化 entry_price（预测当日价），两条路任选：
  a) --entry-price 显式传（westock data_quote / data_kline 最新收盘）
  b) market-data-cache/<symbol>.csv 存在 → 自动取最后 close 并算 entry_ma20
推荐流程：data_kline → 管道写 tools/save_kline.py → append.py（b 路自动生效）。
两者都不可用时拒绝写入（--lenient 放行）——否则到期无法计算 actual_return，
复盘闭环断掉（2026-08-25 复盘实锤：对照组三基准全 error，"可用=0 根"）。

自动填补字段
--------------
id / date / data_cutoff / expiry 由脚本自动补；benchmark / ma_rule / random_dir
默认由 tools/baseline.py 自动算（--no-auto-baseline 关闭）；算不出填 {"error":...}。
entry_price / entry_ma20 由 --entry-price 或本地缓存固化。

字段归一化（写盘前强制）
------------------------
direction 收敛到五值枚举：多 / 空 / 中性偏多 / 中性偏空 / 中性震荡
  （15 种历史写法自动映射，如 "中性震荡偏多"→"中性偏多"）
asset_class 收敛到标准枚举（"大宗商品期货/商品期货/commodity_future"→"商品期货"）
predictability 剥掉括号装饰（"低（60日个股方向）"→"低"），并强制置信度硬上限：
  高≤85 / 中≤75 / 低≤65 / 接近随机≤55（scorecard-spec.md 第11项，超限自动压）
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LEDGER = os.path.join(HERE, "ledger.jsonl")
BASELINE = os.path.join(ROOT, "tools", "baseline.py")
SANITY = os.path.join(ROOT, "tools", "sanity_check_card.py")
KLINE_CACHE_DIR = os.path.join(ROOT, "market-data-cache")

# 与 schema.json required 对齐（id/date/data_cutoff/expiry 由脚本自动补，故这里不列）
REQUIRED = ["source_skill", "methodology", "asset_class", "symbol",
            "direction", "target_range", "time_window", "confidence", "falsification",
            "predictability"]

# ─────────────────── 字段归一化（P0-③ 枚举收敛）───────────────────
# direction 历史上出现过 15 种写法 → 收敛到五值枚举
DIRECTION_ALIASES = {
    "多": "多", "看多": "多", "多(待确认)": "中性偏多",
    "空": "空", "看空": "空", "看空(震荡偏弱)": "中性偏空",
    "中性": "中性震荡", "震荡": "中性震荡", "中性震荡": "中性震荡",
    "中性震荡（区间）": "中性震荡",
    "中性偏多": "中性偏多", "震荡偏多": "中性偏多", "中性震荡偏多": "中性偏多",
    "震荡偏强（箱体[2700,3000]上沿）": "中性偏多", "偏多(待确认)": "中性偏多",
    "中性偏空": "中性偏空", "震荡偏弱": "中性偏空", "中性震荡偏弱": "中性偏空",
    "中性偏空/观望": "中性偏空",
}
CANONICAL_DIRECTIONS = ("多", "空", "中性偏多", "中性偏空", "中性震荡")

# asset_class 历史变体 → 标准枚举（与 schema.json 保持一致）
ASSET_ALIASES = {
    "A股个股": "A股个股", "A股个股(科创板)": "A股个股", "科创板": "A股个股",
    "A股": "A股指数", "A股大盘": "A股指数", "A股指数": "A股指数",
    "港股": "港股", "港股个股": "港股",
    "美股": "美股", "美股指数": "美股", "美股个股": "美股个股",
    "商品期货": "商品期货", "大宗商品": "商品期货", "大宗商品期货": "商品期货",
    "commodity_future": "商品期货", "贵金属": "商品期货", "能源": "商品期货",
    "生猪": "商品期货", "大宗商品/生猪": "商品期货", "期货": "商品期货",
    "期货组合": "组合", "组合": "组合",
    "股指期货": "股指期货",
    "国债期货": "国债期货", "中国国债": "国债期货", "美国国债": "国债期货",
    "外汇": "外汇", "宏观指数": "宏观指数", "其他": "其他",
}
CANONICAL_ASSETS = ("A股个股", "A股指数", "港股", "美股", "美股个股",
                    "商品期货", "股指期货", "国债期货", "外汇", "宏观指数", "组合", "其他")

# 可预测性评级 → 置信度硬上限（scorecard-spec.md 第11项）
PREDICTABILITY_CAPS = {"高": 85, "中": 75, "低": 65, "接近随机": 55}
CANONICAL_REGIMES = ("趋势市", "震荡市", "弱势市")


def _strip_parenthetical(v):
    """'低（60日个股方向，受油价驱动）' → '低'。"""
    return re.sub(r"[（(].*?[)）]", "", str(v)).strip()


def normalize_record(rec):
    """写盘前把 direction / asset_class / predictability / market_regime 归一到枚举。

    返回警告列表（归一化动作要透明，审计可追溯）。
    """
    warns = []

    d = rec.get("direction")
    if isinstance(d, str):
        key = _strip_parenthetical(d)
        canon = DIRECTION_ALIASES.get(d) or DIRECTION_ALIASES.get(key)
        if canon:
            if canon != d:
                warns.append("direction '%s' → '%s'" % (d, canon))
            rec["direction"] = canon
        elif d not in CANONICAL_DIRECTIONS:
            warns.append("direction '%s' 无法归一，保留原值（schema 校验可能拒绝）" % d)

    a = rec.get("asset_class")
    if isinstance(a, str):
        key = _strip_parenthetical(a)
        canon = ASSET_ALIASES.get(a) or ASSET_ALIASES.get(key)
        if canon:
            if canon != a:
                warns.append("asset_class '%s' → '%s'" % (a, canon))
            rec["asset_class"] = canon
        elif a not in CANONICAL_ASSETS:
            warns.append("asset_class '%s' 无法归一，保留原值（schema 校验可能拒绝）" % a)

    p = rec.get("predictability")
    if isinstance(p, str):
        key = _strip_parenthetical(p)
        if key in PREDICTABILITY_CAPS:
            if key != p:
                warns.append("predictability '%s' → '%s'" % (p, key))
            rec["predictability"] = key
        else:
            warns.append("predictability '%s' 剥掉括号后仍非 高/中/低/接近随机" % p)

    mr = rec.get("market_regime")
    if isinstance(mr, str):
        key = _strip_parenthetical(mr)
        if key in CANONICAL_REGIMES:
            if key != mr:
                warns.append("market_regime '%s' → '%s'" % (mr, key))
            rec["market_regime"] = key
    return warns


def enforce_predictability_cap(rec):
    """P0-②：置信度硬上限机器强制（scorecard-spec.md 第11项）。

    高≤85 / 中≤75 / 低≤65 / 接近随机≤55；超限自动压并警告。
    校准崩坏（60-70 桶预测中点 65% vs 实际命中 17%，偏差 -48）的病根修复。
    """
    p = rec.get("predictability")
    c = rec.get("confidence")
    if p not in PREDICTABILITY_CAPS or not isinstance(c, int):
        return
    cap = PREDICTABILITY_CAPS[p]
    if c > cap:
        sys.stderr.write("⚠️ 可预测性评级「%s」置信度硬上限 %d，已将 %d 下调至 %d"
                         "（scorecard-spec.md 第11项）。\n" % (p, cap, c, cap))
        rec["confidence"] = cap
        if isinstance(rec.get("calibrated_confidence"), int) \
           and rec["calibrated_confidence"] > cap:
            rec["calibrated_confidence"] = cap


# ─────────────────── 价格快照（P0-① 闭环加固）───────────────────
def _read_kline_cache(symbol_code):
    """读 market-data-cache/<code>.csv 或 <code>.txt → 按日期升序的 [(date, close)]；无则 []。

    2026-09-18 新增 .txt 支持（黑金/生猪实战实锤）：国内商品期货的日K缓存在
    market-data-cache/<合约>.txt，内容是新浪期货返回的 JSON 数组（键 d/o/h/l/c/v/p/s）。
    此前只读 .csv → 所有期货预测的 entry_ma20/基准三字段恒为 error「可用=0 根」，
    且 **量纲闸门（R1≥1σ / R2≥1.5σ）被静默跳过**——期货预测反而比个股少了那道
    最关键的纪律闸门（该闸门正是 2026-09-16 富满微 / 东华科技两次实锤的价值所在）。
    """
    for ext in (".csv", ".txt"):
        p = os.path.join(KLINE_CACHE_DIR, symbol_code + ext)
        if not os.path.exists(p):
            continue
        rows = []
        try:
            if ext == ".txt":
                # 新浪期货日K：整文件是一个 JSON 数组（可能带前后杂质），取首个 [ 到末个 ]
                raw = open(p, encoding="utf-8").read()
                i, j = raw.find("["), raw.rfind("]")
                if i < 0 or j <= i:
                    continue
                for r in json.loads(raw[i:j + 1]):
                    d = str(r.get("d", "")).strip()[:10]
                    try:
                        c = float(r.get("c"))
                    except (TypeError, ValueError):
                        continue
                    if d and c > 0:
                        rows.append((d, c))
            else:
                import csv as _csv
                with open(p, encoding="utf-8") as f:
                    for r in _csv.DictReader(f):
                        d = str(r.get("date", "")).strip()[:10]
                        try:
                            c = float(r.get("close"))
                        except (TypeError, ValueError):
                            continue
                        if d and c > 0:
                            rows.append((d, c))
        except Exception:
            return []
        rows.sort(key=lambda x: x[0])
        return rows
    return []


def snapshot_entry(rec, entry_price=None, lenient=False):
    """固化 entry_price / entry_ma20（预测当日价快照）。

    优先级：--entry-price 显式值 > 本地 K线缓存最后收盘。
    两者都无 → 拒绝写入（lenient 放行但强烈警告）——没有快照，
    到期无法计算 actual_return，反馈闭环断掉。
    """
    code = str(rec.get("symbol", "")).split()[0] if rec.get("symbol") else ""
    cache = _read_kline_cache(code) if code else []
    pred_date = str(rec.get("date", ""))

    # 缓存里 ≤ 预测日的最后一根（防用未来数据当快照）
    cache_upto = [c for c in cache if not pred_date or c[0] <= pred_date]
    last_close = cache_upto[-1][1] if cache_upto else None
    last_date = cache_upto[-1][0] if cache_upto else None

    price = entry_price if entry_price is not None else last_close
    if price is not None:
        rec["entry_price"] = float(price)
        if entry_price is not None and last_close is not None:
            rec.setdefault("entry_price_src", "cli")
        elif entry_price is not None:
            rec.setdefault("entry_price_src", "cli:no-cache")
        else:
            rec.setdefault("entry_price_src", "cache:%s" % last_date)
        # entry_ma20：缓存里 ≤ 预测日的最后 20 根收盘均值
        tail20 = [c for _, c in cache_upto[-20:]]
        if len(tail20) >= 20:
            rec["entry_ma20"] = round(sum(tail20) / 20.0, 4)
        return True

    sys.stderr.write(
        "✗ 无法固化价格快照：--entry-price 未传且 market-data-cache/%s.csv 不存在/为空。\n"
        "   闭环要求：预测时落 entry_price，到期才能算 actual_return（2026-08-25 复盘实锤）。\n"
        "   正确流程：westock data_kline → 管道写 tools/save_kline.py --symbol %s → 再 append。\n"
        % (code or "<symbol>", code or "<symbol>"))
    if lenient:
        sys.stderr.write("⚠️ --lenient 放行：entry_price=null（本条到期将无法自动结算）\n")
        rec["entry_price"] = None
        return False
    sys.exit(2)


def _now():
    return datetime.now()


def _next_id(ledger_path):
    today = _now().strftime("%Y%m%d")
    max_n = 0
    if os.path.exists(ledger_path):
        with open(ledger_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                m = re.match(r"P-(\d{8})-(\d{3})$", str(rec.get("id", "")))
                if m and m.group(1) == today:
                    max_n = max(max_n, int(m.group(2)))
    return "P-%s-%03d" % (today, max_n + 1)


def _infer_expiry(date_str, time_window):
    m = re.match(r"^\s*(\d+)\s*[dD]\s*$", str(time_window))
    if not m:
        return None
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=int(m.group(1)))
        return d.strftime("%Y-%m-%d")
    except Exception:
        return None


def _parse_window(time_window, default=60):
    m = re.match(r"^\s*(\d+)\s*[dD]\s*$", str(time_window))
    return int(m.group(1)) if m else default


def _parse_target_pct(target_range):
    """从 '+5%~+15%' 抽两个百分数 → (0.05, 0.15)；抽不到返回 (None, None)。"""
    if not target_range:
        return (None, None)
    pcts = re.findall(r"([\d.]+)\s*%", str(target_range))
    if len(pcts) >= 2:
        return (float(pcts[0]) / 100.0, float(pcts[1]) / 100.0)
    if len(pcts) == 1:
        return (float(pcts[0]) / 100.0, None)
    return (None, None)


def _run_baseline(symbol, window, direction, tlow, thigh, asof):
    code = str(symbol).split()[0]
    cmd = [sys.executable, BASELINE, "--symbol", code, "--window", str(window),
           "--direction", str(direction), "--asof", asof]
    if tlow is not None:
        cmd += ["--target-low", str(tlow)]
    if thigh is not None:
        cmd += ["--target-high", str(thigh)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout)
        return {"error": (out.stdout or out.stderr).strip()[:200] or "baseline 无输出"}
    except Exception as e:
        return {"error": "baseline 调用失败: %s" % e}


def _run_sanity(symbol, period, current, tlow, thigh, fals):
    cmd = [sys.executable, SANITY, "--symbol", symbol.split()[0],
           "--period-days", str(period), "--current", str(current),
           "--target-low", str(tlow), "--target-high", str(thigh),
           "--falsification", str(fals)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if out.stdout.strip():
            return json.loads(out.stdout)
        return {"ok": False, "error": (out.stderr or "无输出").strip()[:200]}
    except Exception as e:
        return {"ok": False, "error": "sanity 调用失败: %s" % e}


def build(rec, ledger_path, lenient=False, auto_baseline=True,
          cur=None, fals_price=None, tlow=None, thigh=None, skip_sanity=False,
          entry_price=None):
    now = _now()
    rec.setdefault("id", _next_id(ledger_path))
    rec.setdefault("date", now.strftime("%Y-%m-%d"))
    rec.setdefault("data_cutoff", now.strftime("%Y-%m-%d %H:%M"))
    rec.setdefault("expiry", _infer_expiry(rec.get("date", ""), rec.get("time_window", "")))
    rec.setdefault("status", "open")
    rec.setdefault("actual_return", None)
    rec.setdefault("review_date", None)

    # 量纲校验（PRED 4）：数值齐备则自动校验，❌ 拒绝写入
    if not skip_sanity and None not in (cur, fals_price, tlow, thigh):
        san = _run_sanity(rec.get("symbol", ""), _parse_window(rec.get("time_window")),
                          cur, tlow, thigh, fals_price)
        rec["sanity"] = {"pass": bool(san.get("ok")), "reason": "；".join(san.get("issues", [])),
                         "R1": san.get("R1"), "R2": san.get("R2")}
        if not san.get("ok"):
            sys.stderr.write("✗ 量纲校验未通过，拒绝写入（先按建议重设幅度/证伪位）：\n")
            sys.stderr.write(json.dumps(san, ensure_ascii=False, indent=2) + "\n")
            sys.exit(2)

    # 环境过滤器（DISCIPLINE.md）：判市优先于方向，弱市不赌方向 + 置信度纪律
    enforce_regime_discipline(rec)

    # 可预测性硬上限（scorecard-spec.md 第11项）：高85/中75/低65/接近随机55
    enforce_predictability_cap(rec)

    # 价格快照闭环（P0-①）：entry_price / entry_ma20 固化，到期可算 actual_return
    snapshot_entry(rec, entry_price=entry_price, lenient=lenient)

    # 自动基准回填（PRED 1，默认开启）
    if auto_baseline:
        window = _parse_window(rec.get("time_window"))
        plow, phigh = _parse_target_pct(rec.get("target_range"))
        bl = _run_baseline(rec.get("symbol", ""), window, rec.get("direction", "多"),
                           plow if plow is not None else tlow,
                           phigh if phigh is not None else thigh,
                           rec.get("date", now.strftime("%Y-%m-%d")))
        if isinstance(bl, dict) and "error" not in bl:
            rec["random_dir"] = bl.get("random_dir", {"error": "未返回"})
            rec["ma_rule"] = bl.get("ma_rule", {"error": "未返回"})
            rec["benchmark"] = bl.get("benchmark", {"error": "未返回"})
        else:
            err = bl.get("error", "baseline 失败") if isinstance(bl, dict) else "baseline 失败"
            rec["random_dir"] = {"error": err}
            rec["ma_rule"] = {"error": err}
            rec["benchmark"] = {"error": err}
    # 校准后置信度（PRED 9）：样本不足时 = 原始值；n>=30 后由 score.py --calibration 收缩
    rec.setdefault("calibrated_confidence", rec.get("confidence"))

    missing = [k for k in REQUIRED if k not in rec or rec.get(k) in (None, "")]
    if missing:
        if lenient:
            sys.stderr.write("⚠️ 缺失必填字段（--lenient 放行）: %s\n" % ", ".join(missing))
        else:
            sys.stderr.write("✗ 缺失必填字段: %s\n" % ", ".join(missing))
            sys.exit(2)
    return rec


def load_input(args):
    if args.json:
        return json.loads(args.json)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            return json.load(f)
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            return json.loads(data)
    sys.stderr.write("✗ 未提供输入：用 --json / --file 或管道传入 JSON\n")
    sys.exit(2)


def _load_schema():
    p = os.path.join(HERE, "schema.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return None


def validate_schema(rec, schema):
    """未知字段拒绝 + 必填（排除脚本自动填补字段）拒绝 + 枚举校验。无 schema 时跳过。"""
    if not schema:
        return
    allowed = set(schema.get("properties", {}).keys())
    unknown = sorted(k for k in rec.keys() if k not in allowed)
    if unknown:
        sys.stderr.write("✗ 含 schema 未定义字段: %s\n" % ", ".join(unknown))
        sys.exit(2)
    # 枚举校验（P0-③）：归一化后仍非法的值直接拒绝，杜绝 15 种写法再进台账
    for key, prop in schema.get("properties", {}).items():
        enum = prop.get("enum") if isinstance(prop, dict) else None
        if enum and rec.get(key) is not None and rec[key] not in enum:
            sys.stderr.write("✗ 字段 %s='%s' 不在枚举 %s 内（须先归一化为标准值）\n"
                             % (key, rec[key], "/".join(enum)))
            sys.exit(2)
    auto = ("id", "date", "data_cutoff", "expiry")
    req = [k for k in schema.get("required", []) if k not in auto]
    missing = [k for k in req if k not in rec or rec.get(k) in (None, "")]
    if missing:
        sys.stderr.write("✗ 缺失必填字段（schema）: %s\n" % ", ".join(missing))
        sys.exit(2)


def validate_market_prior(rec):
    """宏观 / 事件类预测必须先取 Polymarket 或同类预测市场赔率（约定4 第10项）。

    商品期货 / 个股类不强制（国内商品期货无 Polymarket 对应市场，硬性要求只会
    逼 agent 绕开台账，反而断闭环）。
    """
    if rec.get("asset_class") in ("宏观指数", "外汇"):
        mp = rec.get("market_prior")
        if not isinstance(mp, dict) or mp.get("applicable") is not True \
           or not str(mp.get("polymarket") or "").strip():
            sys.stderr.write(
                "✗ 宏观/事件类预测必须先取 Polymarket 或同类预测市场赔率（约定4 第10项）\n")
            sys.exit(2)


def warn_confidence_distribution(ledger_path):
    """回读最近 10 条，若全落在 55-75 区间则告警（中间值锚定退化）。"""
    try:
        recs = []
        with open(ledger_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except Exception:
                        pass
        recent = [r for r in recs[-10:] if isinstance(r.get("confidence"), int)]
        if len(recent) >= 10 and all(55 <= c <= 75 for c in (r["confidence"] for r in recent)):
            sys.stderr.write(
                "⚠️ 最近 10 条置信度全在 55-75，该字段可能已退化为噪音，"
                "Brier 将失去区分度。请在本周复盘中专项检讨。\n")
    except Exception:
        pass


def enforce_diversity_discipline(rec, ledger_path, force=False):
    """约定13 纪律进代码——最近 10 条窗口/置信度多样性硬约束（含本条）。

    判定逻辑（避免商品期货被永久锁死）：
      历史 9 条 = 台账最近 9 条（不含本条）。
      · 某维度「历史退化」= 该 9 条在该维度全退化（全 60D / 全落 55-75）。
      · 本条「带来多样性」= 窗口非 60D（new_win_div）/ 置信度出 55-75 锚定区
        （new_conf_div；注意用写盘后真实值，已被可预测性硬上限压过）。
      放行条件（满足任一即放）：
        ① 历史窗口已多样（hist_win_degen=False）；或
        ② 历史置信度已多样（hist_conf_degen=False）；或
        ③ 本条带来窗口多样性（new_win_div）；或
        ④ 本条带来置信度多样性（new_conf_div）。
      仅当「历史两维都退化 且 本条哪一维都不改善」时才拒绝。

    为何这样设计：本体系商品期货多为「低」可预测性（置信度硬上限 65，必落
    55-75 锚定区），若用旧逻辑「候选集全锚定即拒」，则每条商品预测都因置信度
    维度被永久锁死、只能 --force，纪律形同虚设。改为「改善任一退化维度即放行」
    后，商品预测改用 5D/20D 短窗口即可破窗放行，纪律真正可执行。
    --force 可放行，但打 `discipline_violation` 标记，score.py 复盘专项统计。
    """
    try:
        recs = []
        with open(ledger_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        return
    hist = recs[-9:]  # 最近 9 条历史（不含本条）
    if len(hist) < 9:
        return  # 前 9 条还没攒够，暂不强制

    # 用写盘后的真实值（confidence 已被可预测性硬上限压过）
    new_win = _parse_window(rec.get("time_window"), 60)
    new_conf = rec.get("confidence")

    hist_win_degen = all(_parse_window(r.get("time_window"), 60) == 60
                         for r in hist if isinstance(r.get("time_window"), str))
    hist_confs = [r.get("confidence") for r in hist if isinstance(r.get("confidence"), int)]
    hist_conf_degen = len(hist_confs) >= 9 and all(55 <= c <= 75 for c in hist_confs)

    new_win_div = new_win != 60
    new_conf_div = isinstance(new_conf, int) and not (55 <= new_conf <= 75)

    # 历史已多样，或本条带来任一维度多样性 → 放行
    if (not hist_win_degen) or (not hist_conf_degen) or new_win_div or new_conf_div:
        return

    # 历史两维都退化 且 本条无改善 → 拒绝
    violations = []
    if hist_win_degen:
        violations.append("窗口退化：最近 9 条历史全为 60D，本条也是 60D "
                          "——约定13 要求每 10 条 ≥3 条 5D/20D 短窗口")
    if hist_conf_degen:
        violations.append("置信度锚定：最近 9 条历史全落 55-75，本条也落 55-75 "
                          "（提示：低可预测性品种被硬上限压在 65，无法靠置信度破锚，"
                          "请改用 5D/20D 短窗口来恢复多样性）")
    msg = ("✗ 纪律校验未通过，拒绝写入（约定13 多样性约束）：\n  - "
           + "\n  - ".join(violations)
           + "\n  恢复方法：补一条 5D/20D 短窗口（position='不动·仅记录'，"
             "目的拿校准数据）或一条置信度 <55 或 >75 的预测；"
             "确认必须写则用 --force 放行（打 discipline_violation 标记）。")
    if not force:
        sys.stderr.write(msg + "\n")
        sys.exit(2)
    sys.stderr.write("⚠️ --force 放行：本条打 discipline_violation 标记，"
                     "score.py 将专项统计。\n")
    rec["discipline_violation"] = violations


# ─────────────────── 环境过滤器（DISCIPLINE.md）───────────────────
# 给方向前必须先判市；弱势市不赌方向、置信度封顶 60；趋势市>70 需 trend_confirmed。
_CONDITIONAL_KW = ["若", "站上", "跌破", "放量", "转多", "转空",
                   "待确认", "观望", "条件", "突破"]


def enforce_regime_discipline(rec):
    """判市优先于方向（DISCIPLINE.md）。在 build() 中自动调用，写盘前强制纪律。

    - 弱势市 / 震荡市 给单边方向但没写条件触发 → 警告（建议改'区间+方向待确认'）
    - 弱势市 方向性判断 置信度 >60 → 自动压到 60（trend_confirmed=true 可豁免）
    - 趋势市 置信度 >70 但 trend_confirmed≠true → 自动封到 70
    """
    regime = rec.get("market_regime")
    direction = rec.get("direction")
    if regime not in ("趋势市", "震荡市", "弱势市"):
        # 由 schema.required 强制；这里仅防御性提示
        sys.stderr.write("⚠️ 未填 market_regime（趋势市/震荡市/弱势市），请先判市再给方向（见 DISCIPLINE.md）。\n")
        return
    text = " ".join(str(rec.get(k, "")) for k in
                   ("target_range", "falsification", "position", "note"))
    is_conditional = any(kw in text for kw in _CONDITIONAL_KW)
    unilateral = direction in ("多", "空")

    if regime in ("弱势市", "震荡市") and unilateral and not is_conditional:
        sys.stderr.write(
            "⚠️ [%s] 给了单边'%s'但未写条件式触发（如'若放量站上X则多'）。\n"
            "   建议改为'区间+方向待确认'，或补上触发条件（见 DISCIPLINE.md 规则1/4）。\n"
            % (regime, direction))

    c = rec.get("confidence")
    if not isinstance(c, int):
        return
    if regime == "弱势市" and unilateral and c > 60 and not rec.get("trend_confirmed"):
        sys.stderr.write("⚠️ 弱势市方向性判断置信度上限60，已将 %d 下调至60（DISCIPLINE.md 置信度纪律）。\n" % c)
        rec["confidence"] = 60
    if regime == "趋势市" and c > 70 and not rec.get("trend_confirmed"):
        sys.stderr.write("⚠️ 趋势市置信度>70 需 trend_confirmed=true（趋势确认），否则上限70，已将 %d 下调至70。\n" % c)
        rec["confidence"] = 70


def do_append(args):
    rec = load_input(args)
    if not isinstance(rec, dict):
        sys.stderr.write("✗ 输入必须是 JSON 对象\n")
        sys.exit(2)

    # 字段归一化（P0-③）：先于 schema 校验，历史写法自动收敛到枚举
    for w in normalize_record(rec):
        sys.stderr.write("🔀 归一化：%s\n" % w)

    schema = _load_schema()
    validate_schema(rec, schema)
    validate_market_prior(rec)

    if args.evidence_ref is not None:
        rec["evidence_ref"] = args.evidence_ref or None
        if args.evidence_ref and not os.path.exists(args.evidence_ref):
            sys.stderr.write("⚠️ evidence_ref 指向文件不存在：%s（仍写入，不阻断）\n" % args.evidence_ref)
    if args.data_quality is not None:
        if not (0 <= args.data_quality <= 100):
            sys.stderr.write("✗ data_quality 超出 [0,100]：%s\n" % args.data_quality)
            sys.exit(2)
        rec["data_quality"] = args.data_quality
        c = rec.get("confidence")
        if isinstance(c, int) and c > args.data_quality:
            sys.stderr.write("⚠️ 置信度 %d 超过数据质量上限 %d，已下调\n" % (c, args.data_quality))
            rec["confidence"] = args.data_quality

    rec = build(rec, LEDGER, args.lenient, args.auto_baseline,
                args.current, args.falsification_price, args.target_low, args.target_high,
                args.skip_sanity, args.entry_price)

    # 约定13 纪律进代码：窗口多样性 + 置信度出界硬校验（写盘前最后一道闸）
    enforce_diversity_discipline(rec, LEDGER, args.force)

    if args.dry_run:
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        return

    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("✓ 已追加 → %s  (id=%s, expiry=%s)" % (LEDGER, rec["id"], rec.get("expiry")))
    warn_confidence_distribution(LEDGER)


def do_update(args):
    """PRED 8：追加一条贝叶斯更新记录到 updates 数组，不覆盖原始 confidence。"""
    recs = []
    if os.path.exists(LEDGER):
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except Exception:
                        pass
    target = next((r for r in recs if r.get("id") == args.id), None)
    if not target:
        sys.stderr.write("✗ 未找到 id=%s\n" % args.id)
        sys.exit(2)
    if not args.trigger or not args.trigger.strip():
        sys.stderr.write("✗ 更新需 --trigger（具体触发条件）\n")
        sys.exit(2)
    if args.new_confidence is None:
        sys.stderr.write("✗ 更新需 --new-confidence\n")
        sys.exit(2)
    entry = {
        "date": _now().strftime("%Y-%m-%d"),
        "trigger": args.trigger.strip(),
        "old_confidence": target.get("confidence"),
        "new_confidence": args.new_confidence,
    }
    target.setdefault("updates", [])
    if not isinstance(target["updates"], list):
        target["updates"] = []
    target["updates"].append(entry)
    target["confidence"] = args.new_confidence

    if args.dry_run:
        print(json.dumps(target, ensure_ascii=False, indent=2))
        return
    with open(LEDGER, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("✓ 已更新 %s → 追加更新记录，confidence %s→%s"
          % (args.id, entry["old_confidence"], args.new_confidence))


def main():
    ap = argparse.ArgumentParser(description="评分卡 → 预测台账 追加器")
    sub = ap.add_subparsers(dest="command")

    # update 子命令
    up = sub.add_parser("update", help="追加贝叶斯更新记录（PRED 8）")
    up.add_argument("--id", required=True, help="记录 id")
    up.add_argument("--trigger", required=True, help="触发条件（具体、可机械判定）")
    up.add_argument("--new-confidence", type=int, required=True, help="更新后置信度")
    up.add_argument("--dry-run", action="store_true", help="不写盘，仅打印")

    # 默认追加模式
    src = ap.add_mutually_exclusive_group(required=False)
    src.add_argument("--json", help="直接传 JSON 字符串")
    src.add_argument("--file", help="传 JSON 文件路径")
    ap.add_argument("--dry-run", action="store_true", help="不写盘，仅打印")
    ap.add_argument("--lenient", action="store_true", help="必填缺失也放行（仍写盘）")
    ap.add_argument("--force", action="store_true",
                    help="约定13 逃生门：跳过窗口多样性/置信度出界硬校验（打 discipline_violation 标记）")
    ap.add_argument("--evidence-ref", default=None,
                    help="证据卡快照路径（_run/evidence-*.md）；无则留空或传空字符串")
    ap.add_argument("--data-quality", type=int, default=None,
                    help="D7 数表算出的数据质量上限分 0-100；若置信度超过则自动下调")
    ap.add_argument("--auto-baseline", dest="auto_baseline", action="store_true",
                    default=True, help="自动回填基准三字段（默认开启）")
    ap.add_argument("--no-auto-baseline", dest="auto_baseline", action="store_false",
                    help="关闭自动基准回填")
    ap.add_argument("--current", type=float, default=None, help="当前价（用于量纲校验）")
    ap.add_argument("--entry-price", type=float, default=None,
                    help="预测当日价格快照（P0-① 强制）：优先取 westock data_quote/data_kline "
                         "最新收盘；未传则回落 market-data-cache/<symbol>.csv 最后收盘；"
                         "两者皆无则拒绝写入（--lenient 放行）")
    ap.add_argument("--falsification-price", type=float, default=None, help="证伪价位（用于量纲校验）")
    ap.add_argument("--target-low", type=float, default=None, help="幅度下界（小数，如0.05）")
    ap.add_argument("--target-high", type=float, default=None, help="幅度上界（小数，如0.15）")
    ap.add_argument("--skip-sanity", action="store_true", help="跳过量纲校验")

    args = ap.parse_args()

    if args.command == "update":
        do_update(args)
    else:
        do_append(args)


if __name__ == "__main__":
    main()
