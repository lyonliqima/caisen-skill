#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
append.py — 研判评分卡 → 预测台账 追加器
=================================================
每次「股票/期货」方向性分析产出评分卡后，调用本脚本把一条记录追加进
predictions-ledger/ledger.jsonl（JSONL，逐行一个 JSON，便于追加与复盘）。

用法
----
  # 传 JSON 字符串
  python3 append.py --json '{"source_skill":"caisen-9-experts-analyst","methodology":"九专家综合","asset_class":"A股个股","symbol":"600519 贵州茅台","direction":"多","target_range":"+5%~+15%","time_window":"60D","confidence":70,"falsification":"跌破1400","scenarios":{"bull_prob":50,"base_prob":30,"bear_prob":20,"bull_trigger":"Q3财报超预期","bear_trigger":"消费数据继续走弱"},"position":"轻仓","consensus_part":"复苏预期","variant_part":"高端批价实际动销","evidence_votes":{"价量":"多","资金流":"中性","基本面":"多","政策":"中性","情绪":"多"},"independence_color":"🟢"}'

  # 传 JSON 文件
  python3 append.py --file rec.json

  # 从 stdin 读
  cat rec.json | python3 append.py

  # 试运行（不写盘，仅打印将要写入的记录）
  python3 append.py --json '...' --dry-run

自动填补字段
--------------
- id        : P-YYYYMMDD-NNN（NNN 取台账已有最大序号 +1，同日起始 001）
- date      : 今天 YYYY-MM-DD
- data_cutoff: 现在 YYYY-MM-DD HH:MM
- expiry    : 若 time_window 形如 5D/20D/60D/120D 则按天推算；否则留 null（自由文本窗口，如 2026-Q4）

必填校验
----------
id/date/data_cutoff/expiry 自动补，不强制；其余 required 字段缺失会报错退出（除非 --lenient）。
"""
import argparse, json, os, sys, re
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger.jsonl")

# 与 schema.json required 对齐（id/date/data_cutoff/expiry 由脚本自动补，故这里不列）
REQUIRED = ["source_skill", "methodology", "asset_class", "symbol",
             "direction", "target_range", "time_window", "confidence", "falsification"]


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


def build(rec, ledger_path, lenient=False):
    now = _now()
    rec.setdefault("id", _next_id(ledger_path))
    rec.setdefault("date", now.strftime("%Y-%m-%d"))
    rec.setdefault("data_cutoff", now.strftime("%Y-%m-%d %H:%M"))
    rec.setdefault("expiry", _infer_expiry(rec.get("date", ""), rec.get("time_window", "")))
    rec.setdefault("status", "open")
    rec.setdefault("actual_return", None)
    rec.setdefault("review_date", None)

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


def main():
    ap = argparse.ArgumentParser(description="评分卡 → 预测台账 追加器")
    src = ap.add_mutually_exclusive_group(required=False)
    src.add_argument("--json", help="直接传 JSON 字符串")
    src.add_argument("--file", help="传 JSON 文件路径")
    ap.add_argument("--dry-run", action="store_true", help="不写盘，仅打印")
    ap.add_argument("--lenient", action="store_true", help="必填缺失也放行（仍写盘）")
    ap.add_argument("--evidence-ref", default=None,
                    help="证据卡快照路径（_run/evidence-*.md）；无则留空或传空字符串")
    ap.add_argument("--data-quality", type=int, default=None,
                    help="D7 数表算出的数据质量上限分 0-100；若置信度超过则自动下调")
    args = ap.parse_args()

    rec = load_input(args)
    if not isinstance(rec, dict):
        sys.stderr.write("✗ 输入必须是 JSON 对象\n")
        sys.exit(2)

    # ── 证据快照引用 + 数据质量上限（数据层改造 TASK6）──
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

    rec = build(rec, LEDGER, args.lenient)

    if args.dry_run:
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        return

    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("✓ 已追加 → %s  (id=%s, expiry=%s)" % (LEDGER, rec["id"], rec.get("expiry")))


if __name__ == "__main__":
    main()
