#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
save_kline.py — 标的日K缓存写入器（PRED 1 数据快照闭环）
=========================================================
用途：把 westock-mcp `data_kline` 拉到的日K数据固化到
`market-data-cache/<symbol>.csv`（列 date,close，升序），供
`tools/baseline.py` 计算对照组三基准（random_dir / ma_rule / buy&hold），
并供 `predictions-ledger/append.py` 固化 entry_price / entry_ma20 快照。

为什么必须落缓存：baseline 只在「预测当日」取数才可靠；等复盘时再拉，
沙箱限流/接口变更会导致「可用=0 根」——2026-08-25 复盘的实锤教训。
快照随预测落盘，复盘只读静态文件，闭环才成立。

用法（agent 工作流，三步）：
  1. 调 westock-mcp data_kline(code="sh600519", period="day", limit=500)
  2. 把返回 JSON 存临时文件 / 直接管道：
       cat kline.json | python3 tools/save_kline.py --symbol 600519
       # 或从剪贴板内容：python3 tools/save_kline.py --symbol M2609 --stdin-json '{"ok":true,...}'
  3. append.py --entry-price <最新收盘价> （或由本缓存自动回填）

支持的输入格式（自动识别）：
  - westock data_kline 完整返回：{"ok":true,"data":{"nodes":[{date,last,...}]}}
  - nodes 数组本体：{"nodes":[...]}
  - 普通数组：[{"date":"2026-08-25","close":1304}, ...]（close 或 last 或 c 均可）

规则：
  - 与已有缓存按 date 合并去重（后写覆盖先写），升序落盘
  - close 取 last → close → c → closePrice 顺序第一个存在的字段
  - 代码归一化：sh600519/sz000001/bj430047/hk00700 → 600519/000001/430047/hk00700
  - 绝不编造：无法解析出任何 (date, close) 对则报错退出（exit 1）

输出：stdout 打印摘要 JSON（symbol / 新增条数 / 总条数 / 最新日期 / 最新收盘）。
"""
import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE_DIR = os.path.join(ROOT, "market-data-cache")

_CLOSE_KEYS = ("last", "close", "c", "closePrice", "close_price")


def normalize_symbol(raw):
    """sh600519 → 600519；M2609 / 600029 原样保留；去空白。"""
    s = str(raw).strip()
    s = re.sub(r"^(sh|sz|bj|SH|SZ|BJ)", "", s)
    return s


def extract_pairs(payload):
    """从任意支持的输入格式提取 [(date, close), ...]；无有效数据返回 []。"""
    if payload is None:
        return []
    # 完整 westock 返回 / nodes 包装
    nodes = None
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("nodes"), list):
            nodes = data["nodes"]
        elif isinstance(payload.get("nodes"), list):
            nodes = payload["nodes"]
        elif isinstance(data, list):  # 容错：data 直接是数组
            nodes = data
    elif isinstance(payload, list):
        nodes = payload
    if nodes is None:
        return []
    pairs = []
    for nd in nodes:
        if not isinstance(nd, dict):
            continue
        d = str(nd.get("date") or nd.get("time") or nd.get("trade_date") or "").strip()[:10]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            # 容错 YYYYMMDD
            m = re.match(r"^(\d{4})(\d{2})(\d{2})$", d)
            if not m:
                continue
            d = "%s-%s-%s" % m.groups()
        c = None
        for k in _CLOSE_KEYS:
            v = nd.get(k)
            if isinstance(v, (int, float)) and v > 0:
                c = float(v)
                break
        if c is None:
            continue
        pairs.append((d, c))
    return pairs


def load_existing(path):
    """读已有缓存 CSV → dict {date: close}；损坏则忽略。"""
    out = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                d = str(r.get("date", "")).strip()[:10]
                try:
                    c = float(r.get("close"))
                except (TypeError, ValueError):
                    continue
                if d and c > 0:
                    out[d] = c
    except Exception:
        pass
    return out


def main():
    ap = argparse.ArgumentParser(description="日K → market-data-cache 快照写入器")
    ap.add_argument("--symbol", required=True,
                    help="标的代码（600519 / M2609 / hk00700；sh 前缀自动剥）")
    ap.add_argument("--stdin-json", default=None,
                    help="直接传 JSON 字符串（与管道二选一）")
    args = ap.parse_args()

    raw = args.stdin_json
    if not raw and not sys.stdin.isatty():
        raw = sys.stdin.read()
    if not raw or not raw.strip():
        sys.stderr.write("✗ 未提供输入：管道传入 data_kline JSON 或用 --stdin-json\n")
        sys.exit(2)
    try:
        payload = json.loads(raw)
    except Exception as e:
        sys.stderr.write("✗ JSON 解析失败: %s\n" % e)
        sys.exit(2)

    symbol = normalize_symbol(args.symbol)
    pairs = extract_pairs(payload)
    if not pairs:
        sys.stderr.write(
            "✗ 未能从输入解析出任何 (date, close) 对——拒绝写入空缓存（绝不编造）。\n"
            "   检查是否传了 data_kline 的完整返回（含 data.nodes）。\n")
        sys.exit(1)

    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, symbol + ".csv")
    merged = load_existing(path)
    new_n = 0
    for d, c in pairs:
        if d not in merged or abs(merged[d] - c) > 1e-9:
            new_n += 1
        merged[d] = c
    dates = sorted(merged.keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "close"])
        for d in dates:
            w.writerow([d, repr(merged[d])])
    latest_d = dates[-1]
    print(json.dumps({
        "ok": True, "symbol": symbol, "path": path,
        "added": new_n, "total": len(dates),
        "latest_date": latest_d, "latest_close": merged[latest_d],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
