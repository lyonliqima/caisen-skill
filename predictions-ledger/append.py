#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
append.py — 研判评分卡 → 预测台账 追加器
=================================================
每次「股票/期货」方向性分析产出评分卡后，调用本脚本把一条记录追加进
predictions-ledger/ledger.jsonl（JSONL，逐行一个 JSON，便于追加与复盘）。

用法
----
  # 传 JSON 字符串（默认自动回填基准三字段）
  python3 append.py --json '{"source_skill":"caisen-10-experts-analyst","methodology":"十二专家综合","asset_class":"A股个股","symbol":"600519 贵州茅台","direction":"多","target_range":"+5%~+15%","time_window":"60D","confidence":70,"falsification":"跌破1400","predictability":"低","scenarios":{"bull_prob":50,"base_prob":30,"bear_prob":20},"position":"轻仓","consensus_part":"复苏预期","variant_part":"高端批价动销","evidence_votes":{"价量":"多","资金流":"中性","基本面":"多","政策":"中性","情绪":"多"},"independence_color":"🟢"}'

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

自动填补字段
--------------
id / date / data_cutoff / expiry 由脚本自动补；benchmark / ma_rule / random_dir
默认由 tools/baseline.py 自动算（--no-auto-baseline 关闭）；算不出填 {"error":...}。
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

# 与 schema.json required 对齐（id/date/data_cutoff/expiry 由脚本自动补，故这里不列）
REQUIRED = ["source_skill", "methodology", "asset_class", "symbol",
            "direction", "target_range", "time_window", "confidence", "falsification",
            "predictability"]


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
          cur=None, fals_price=None, tlow=None, thigh=None, skip_sanity=False):
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
    """未知字段拒绝 + 必填（排除脚本自动填补字段）拒绝。无 schema 时跳过。"""
    if not schema:
        return
    allowed = set(schema.get("properties", {}).keys())
    unknown = sorted(k for k in rec.keys() if k not in allowed)
    if unknown:
        sys.stderr.write("✗ 含 schema 未定义字段: %s\n" % ", ".join(unknown))
        sys.exit(2)
    auto = ("id", "date", "data_cutoff", "expiry")
    req = [k for k in schema.get("required", []) if k not in auto]
    missing = [k for k in req if k not in rec or rec.get(k) in (None, "")]
    if missing:
        sys.stderr.write("✗ 缺失必填字段（schema）: %s\n" % ", ".join(missing))
        sys.exit(2)


def validate_market_prior(rec):
    """宏观 / 事件类预测必须先取 Polymarket 或同类预测市场赔率（约定4 第10项）。"""
    if rec.get("asset_class") in ("大宗商品", "宏观指数", "外汇"):
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


def do_append(args):
    rec = load_input(args)
    if not isinstance(rec, dict):
        sys.stderr.write("✗ 输入必须是 JSON 对象\n")
        sys.exit(2)

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
                args.skip_sanity)

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
    ap.add_argument("--evidence-ref", default=None,
                    help="证据卡快照路径（_run/evidence-*.md）；无则留空或传空字符串")
    ap.add_argument("--data-quality", type=int, default=None,
                    help="D7 数表算出的数据质量上限分 0-100；若置信度超过则自动下调")
    ap.add_argument("--auto-baseline", dest="auto_baseline", action="store_true",
                    default=True, help="自动回填基准三字段（默认开启）")
    ap.add_argument("--no-auto-baseline", dest="auto_baseline", action="store_false",
                    help="关闭自动基准回填")
    ap.add_argument("--current", type=float, default=None, help="当前价（用于量纲校验）")
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
