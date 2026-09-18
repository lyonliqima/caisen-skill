# -*- coding: utf-8 -*-
"""通用入口：把 tdx_kline 落盘的结果文件 → 蔡森全链路成品（图 + 文字）

用法:
    python run_from_tdx.py <结果文件> <code> <expect_name> [out_dir]

结果文件格式兼容两种：
  1) 纯 JSON
  2) 「中文摘要前缀 + JSON」（MCP 大结果落盘时的形态）
自动截取第一个 '{' 到最后一个 '}' 之间的 JSON 主体。

S6 守卫仍在 parse_kline_json 内：不支持市场 / 空数据 / 标的错位一律上抛，
绝不静默出图。
"""
from __future__ import annotations
import sys, json, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from caisen_pipeline import run   # noqa: E402


def load_raw(path: str) -> dict:
    """读落盘结果文件，截出其中的 JSON 主体。

    落盘文件常在 JSON 前后附带中文摘要与说明文字，且尾部说明里可能含花括号，
    故用 raw_decode 从第一个 '{' 起解析**恰好一个** JSON 对象，而非按最后一个
    '}' 截取（后者会多截导致 Extra data）。
    """
    text = Path(path).read_text(encoding="utf-8")
    i = text.find("{")
    if i < 0:
        raise ValueError(f"文件中找不到 JSON 主体: {path}")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[i:])
        return obj
    except json.JSONDecodeError:
        j = text.rfind("}")
        if j <= i:
            raise ValueError(f"文件中的 JSON 无法解析: {path}")
        return json.loads(text[i:j + 1])


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        print("  说明：不传 out_dir 时，成品默认写到当前工作目录的 ./outputs/ 下"
              "（不写进技能安装目录，避免污染只读路径）。")
        return 2
    src, code, name = sys.argv[1], sys.argv[2], sys.argv[3]
    # 默认写到「当前工作目录」而非技能安装目录：技能目录可能只读或被版本管理托管
    out_dir = sys.argv[4] if len(sys.argv) > 4 else os.path.join(os.getcwd(), "outputs")

    raw = load_raw(src)
    res = run(raw, query=code, expect_name=name, out_dir=out_dir, dpi=250)

    print("=" * 78)
    print(res["report"])
    print("=" * 78)
    print("PNG:", res["png"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
