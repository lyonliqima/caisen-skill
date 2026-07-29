#!/bin/bash
# pre-commit 钩子：提交前跑全仓 markdown 断链检查。
# 存在非 allowlist 的断链则阻止提交；allowlist（tools/check_links.allowlist）中的已知缺失跳过。
# 安装：仓库根目录执行  ln -s ../../tools/pre-commit-check-links.sh .git/hooks/pre-commit
set -e
ROOT="$(git rev-parse --show-toplevel)"
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "pre-commit: 未找到 python3，跳过断链检查" >&2
  exit 0
fi
"$PY" "$ROOT/tools/check_links.py"
