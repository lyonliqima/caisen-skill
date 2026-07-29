#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scenario_tree.py — 兵棋推演情景树末端联合概率计算
=================================================
输入一棵情景树（节点 + 条件概率），输出：
  1) 每条根到叶路径的联合概率（= 沿途各层条件概率之积），按降序排列
  2) 累计概率覆盖（top 80% 路径）
  3) 按方向（牛/基准/熊）聚合的三情景概率（由路径聚合得出，不得另拍）

校验：每个节点的兄弟分支概率之和须在 1±0.01 内，否则报错退出。

输入 JSON 结构（节点递归）：
{
  "name": "根",
  "children": [
    {"name": "牛路径A", "prob": 0.4, "direction": "牛", "children": [ ... ]},
    {"name": "基准路径B", "prob": 0.4, "direction": "基准"},
    {"name": "熊路径C", "prob": 0.2, "direction": "熊"}
  ]
}
末端叶节点需带 direction（牛/基准/熊），作为该路径的方向归属。

用法
----
  python3 tools/scenario_tree.py --file tree.json
  cat tree.json | python3 tools/scenario_tree.py
  python3 tools/scenario_tree.py --help
"""
import argparse
import json
import sys

DIRECTION_KEYS = ["牛", "基准", "熊"]


def _validate_node(node, path, tol=0.01):
    kids = node.get("children")
    if not kids:
        if node.get("direction") not in DIRECTION_KEYS:
            sys.stderr.write("✗ 叶节点 %s 缺 direction（须为 牛/基准/熊）\n" % path)
            sys.exit(2)
        return
    s = sum(float(k.get("prob", 0)) for k in kids)
    if abs(s - 1.0) > tol:
        sys.stderr.write("✗ 节点 %s 子分支概率和 = %.4f（应≈1.00±%s）\n" % (path, s, tol))
        sys.exit(2)
    for k in kids:
        _validate_node(k, path + "/" + str(k.get("name", "?")))


def _walk(node, acc_prob, path_parts, paths):
    kids = node.get("children")
    if not kids:
        paths.append({
            "path": " > ".join(path_parts + [str(node.get("name", "?"))]),
            "prob": round(acc_prob, 6),
            "direction": node.get("direction"),
            "steps": len(path_parts),
        })
        return
    for k in kids:
        _walk(k, acc_prob * float(k.get("prob", 0)),
              path_parts + [str(k.get("name", "?"))], paths)


def compute(tree):
    _validate_node(tree, "root")
    paths = []
    _walk(tree, 1.0, [], paths)
    paths.sort(key=lambda x: x["prob"], reverse=True)

    total = sum(p["prob"] for p in paths) or 1.0
    cum = 0.0
    for p in paths:
        cum += p["prob"]
        p["cum_prob"] = round(cum, 6)
    # 累计覆盖 top 80%
    top80 = [p for p in paths if p["cum_prob"] <= 0.8001]
    if not top80 and paths:
        top80 = [paths[0]]

    agg = {k: 0.0 for k in DIRECTION_KEYS}
    for p in paths:
        agg[p["direction"]] = round(agg[p["direction"]] + p["prob"], 6)

    return {
        "terminal_paths": paths,
        "n_paths": len(paths),
        "top80_paths": top80,
        "aggregated_scenarios": agg,  # 由树聚合，单位：概率和应≈1
        "tail_risk": [p for p in paths if p["prob"] < 0.01],  # 尾部风险清单（概率<1%）
    }


def main():
    ap = argparse.ArgumentParser(description="情景树末端联合概率计算")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="树结构 JSON 文件")
    src.add_argument("--json", help="树结构 JSON 字符串")
    args = ap.parse_args()

    raw = args.json
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            raw = f.read()
    try:
        tree = json.loads(raw)
    except Exception as e:
        sys.stderr.write("✗ JSON 解析失败: %s\n" % e)
        sys.exit(2)

    out = compute(tree)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
