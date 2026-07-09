#!/usr/bin/env python3
"""render.py — 把 agent 写好的 body 片段套进 shell.html，输出最终 HTML（分析类报告）。

用法:
    python3 render.py <body_file> <output_html> --title="<报告标题>" [--date=YYYY-MM-DD] [--keep-body]

参数:
    body_file      agent 写的 body 片段（只含内容 + class，不含 <head>/<style>）
    output_html    最终 HTML 输出路径
    --title        <title> 标签内容（也是浏览器标签页标题）
    --date         报告日期，默认今天
    --keep-body    渲染完不删除 body 片段（默认会删，调试时加这个）

行为:
    1. 读 shell.html（同目录）
    2. 读 body_file
    3. 替换 {{TITLE}} / {{BODY}} / {{DATE}}
    4. 删除 body 中残留的未使用 {{SLOT}} 占位符（保持 HTML 干净）
    5. 写到 output_html
    6. 默认删除 body_file（除非 --keep-body）

依赖:
    Python 3.8+ 标准库。
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SHELL_PATH = SCRIPT_DIR / "shell.html"
_UNUSED_SLOT = re.compile(r"\{\{[A-Z0-9_]+\}\}")


def render(body_file: Path, output_html: Path, title: str, date: str) -> None:
    if not SHELL_PATH.is_file():
        print(f"[render] shell.html 缺失: {SHELL_PATH}", file=sys.stderr)
        raise SystemExit(2)
    if not body_file.is_file():
        print(f"[render] body 文件不存在: {body_file}", file=sys.stderr)
        raise SystemExit(2)

    shell = SHELL_PATH.read_text(encoding="utf-8")
    body = body_file.read_text(encoding="utf-8")

    for placeholder in ("{{TITLE}}", "{{BODY}}", "{{DATE}}"):
        if placeholder not in shell:
            print(f"[render] shell.html 缺少占位符 {placeholder}", file=sys.stderr)
            raise SystemExit(3)

    final = (
        shell
        .replace("{{TITLE}}", title)
        .replace("{{BODY}}", body)
        .replace("{{DATE}}", date)
    )
    # 清掉 body 里残留的未使用占位符（模型没填的槽位）
    final = _UNUSED_SLOT.sub("", final)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(final, encoding="utf-8")
    size_kb = output_html.stat().st_size // 1024
    print(f"[render] 已合成 → {output_html} ({size_kb} KB)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="分析报告 body → 完整 HTML")
    parser.add_argument("body_file", help="agent 写的 body 片段路径")
    parser.add_argument("output_html", help="最终 HTML 输出路径")
    parser.add_argument("--title", required=True, help="HTML <title> 标签内容")
    parser.add_argument("--date", default=None, help="报告日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--keep-body", action="store_true", help="保留 body 片段文件（默认渲染完即删）")
    args = parser.parse_args()

    body_file = Path(args.body_file).resolve()
    output_html = Path(args.output_html).resolve()
    date = args.date or datetime.date.today().isoformat()

    render(body_file, output_html, args.title, date)

    if not args.keep_body:
        try:
            body_file.unlink()
            print(f"[render] 已清理 body 片段: {body_file.name}", flush=True)
        except OSError as exc:
            print(f"[render] 删除 body 片段失败（忽略）: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
