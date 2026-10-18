#!/usr/bin/env python3
"""check_links.py — 全仓 markdown 断链静态检查器。

检查两类引用：
1. markdown 链接 [text](relative/path.ext)
2. 反引号内的仓库相对文件路径 `dir/file.ext`（限已知扩展名）

解析规则：
- 相对路径同时尝试「相对本 md 文件所在目录」与「相对仓库根」两种解析，任一存在即通过。
- 跨技能引用：`references/<x>.md` 若**唯一**存在于某个一级子目录下则放行（如
  caisen-10-experts-analyst 的 SKILL.md 引用 yang-shiguang-analysis 的 references/）。
  多命中或零命中仍报断链。2026-10-15 追加。
- `$CAISEN_ROOT/xxx` 一律按仓库根解析。
- 跳过：http(s)/mailto 链接、纯锚点(#...)、含通配/占位符的路径（* { < > YYYY 日期模板等）、
  同一行已标注 [MISSING 的引用（人工确认过的缺失）、_archive/ 与 .workbuddy/ 内的文件。

退出码：0=全部通过；1=存在断链。
用法：python3 tools/check_links.py [--root 仓库根]
"""
import argparse
import os
import re
import sys

EXTS = ('.md', '.py', '.json', '.jsonl', '.yaml', '.yml', '.txt', '.sh',
        '.png', '.jpg', '.html', '.csv', '.pt')
SKIP_DIRS = {'_archive', '.workbuddy', '.git', '__pycache__', 'node_modules',
             '.venv', 'venv', '.cache'}
# 路径里出现这些即视为模板/占位符，不检查
PLACEHOLDER_PAT = re.compile(r'[*{<>]|YYYY|yyyy|<日期>|\{主题\}|\.\.\.')

MD_LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')
BACKTICK = re.compile(r'`([^`\n]+)`')

# 已知缺失引用基线（上游未随本仓库分发 / 运行时生成 / 待补文档）。
# 格式：每行 `相对路径:行号`（# 开头为注释）。精确匹配到行，行号漂移即重新触发检查。
ALLOWLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'check_links.allowlist')


def load_allowlist() -> set:
    if not os.path.exists(ALLOWLIST):
        return set()
    out = set()
    with open(ALLOWLIST, encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            out.add(s.split()[0])  # 允许行尾带注释
    return out


def is_checkable(path: str) -> bool:
    if path.startswith(('http://', 'https://', 'mailto:', '#', 'ftp://')):
        return False
    if PLACEHOLDER_PAT.search(path):
        return False
    # 命令串 / 选项串 / 环境变量（$CAISEN_ROOT 除外）不当作路径检查
    if any(ch.isspace() for ch in path):
        return False
    if path.startswith('-'):
        return False
    if path.startswith('$') and not path.startswith('$CAISEN_ROOT/'):
        return False
    # 去锚点后判断扩展名
    p = path.split('#')[0]
    if not p.lower().endswith(EXTS):
        return False
    # 绝对路径（机器相关）不在本检查范围（BUG-6 已单独治理）
    if p.startswith('/') or p.startswith('~'):
        return False
    return True


# 特例基准：alphaear 的子技能文档保留了上游仓库的相对路径写法，
# alphaear/references/alphaear-<X>.md 中的相对引用基准为 alphaear/scripts/alphaear-<X>/
ALPHAEAR_DOC = re.compile(r'alphaear/references/(alphaear-[a-z0-9-]+)\.md$')

_SUBDIR_CACHE = None


def _root_subdirs(root: str):
    """仓库一级子目录名（带缓存，供跨技能引用解析用）。"""
    global _SUBDIR_CACHE
    if _SUBDIR_CACHE is None:
        try:
            _SUBDIR_CACHE = sorted(
                n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n))
            )
        except OSError:
            _SUBDIR_CACHE = []
    return _SUBDIR_CACHE


def resolve(p: str, md_path: str, root: str) -> bool:
    p = p.split('#')[0]
    if p.startswith('$CAISEN_ROOT/'):
        return os.path.exists(os.path.join(root, p[len('$CAISEN_ROOT/'):]))
    # 依次尝试：md 所在目录 → 各级祖先目录 → 仓库根
    base = os.path.dirname(md_path)
    while True:
        if os.path.exists(os.path.normpath(os.path.join(base, p))):
            return True
        if os.path.samefile(base, root) if os.path.exists(base) else base == root:
            break
        parent = os.path.dirname(base)
        if parent == base:
            break
        base = parent
    # alphaear 子技能文档特例：上游文档以 scripts/<x>.py / references/<y>.md 描述，
    # 实际文件位于 alphaear/scripts/<子技能名>/（scripts/* 还可能再嵌 utils/ 子目录），
    # 故去掉前导 scripts/ 并回退尝试 utils/ 子目录。
    m = ALPHAEAR_DOC.search(md_path.replace(os.sep, '/'))
    if m:
        sub = os.path.join(root, 'alphaear', 'scripts', m.group(1))
        cand_p = p[8:] if p.startswith('scripts/') else p
        if os.path.exists(os.path.normpath(os.path.join(sub, cand_p))):
            return True
        if os.path.exists(os.path.normpath(os.path.join(sub, 'utils', cand_p))):
            return True
    # 跨技能引用特例（2026-10-15 追加）：技能 A 的 SKILL.md 里写 `references/<x>.md` 时，
    # 该路径的基准可能是「A 自己的 references/」，也可能是文档中正在介绍的那个技能（B）的。
    # 实例：caisen-10-experts-analyst/SKILL.md 在「杨世光视角」节写
    # `references/13-m68-m74.md`，实际文件位于 yang-shiguang-analysis/references/，
    # 由此产生 7 处稳定误报（每次改 SKILL.md 都会淹没真断链）。
    # 保守规则：仅当**有且仅有一个**一级子目录下存在该文件时才放行；
    # 多命中（无法确定基准）或零命中仍报断链——宁可报出来让人核。
    if p.startswith('references/'):
        hits = [n for n in _root_subdirs(root)
                if os.path.isfile(os.path.join(root, n, p))]
        if len(hits) == 1:
            return True
    return False


def check_file(md_path: str, root: str, allow: set):
    errors = []
    skipped = 0
    try:
        with open(md_path, encoding='utf-8') as f:
            lines = f.readlines()
    except (UnicodeDecodeError, OSError):
        return errors
    md_dir = os.path.dirname(md_path)
    for ln, line in enumerate(lines, 1):
        if '[MISSING' in line:  # 已人工标注缺失，跳过
            continue
        candidates = MD_LINK.findall(line)
        # 反引号路径：必须含 / 才当作路径（排除裸文件名误报）
        candidates += [c for c in BACKTICK.findall(line) if '/' in c]
        for cand in candidates:
            cand = cand.strip()
            if not is_checkable(cand):
                continue
            if not resolve(cand, md_path, root):
                rel = os.path.relpath(md_path, root)
                key = f'{rel}:{ln}'
                if key in allow:
                    skipped += 1
                    continue
                errors.append(f'{rel}:{ln}: 断链 -> {cand}')
    return errors, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args()
    root = args.root

    allow = load_allowlist()
    all_errors = []
    n_files = 0
    n_skipped = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith('.md'):
                n_files += 1
                errs, sk = check_file(os.path.join(dirpath, fn), root, allow)
                all_errors += errs
                n_skipped += sk

    if all_errors:
        print(f'✗ 检查 {n_files} 个 md，发现 {len(all_errors)} 处断链'
              f'（另有 {n_skipped} 处已知缺失已在 allowlist 跳过）：')
        for e in all_errors:
            print('  ' + e)
        sys.exit(1)
    print(f'✓ 全部 {n_files} 个 md 通过断链检查'
          f'（{n_skipped} 处已知缺失已在 allowlist 跳过）')
    sys.exit(0)


if __name__ == '__main__':
    main()
