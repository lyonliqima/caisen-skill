#!/usr/bin/env python3
# check_env_drift.py — 蔡森技能「唯一权威副本」纪律的机器化校验
#
# 背景：2026-10-30 诊断发现台账出现双向分叉——CAISEN_ROOT 环境变量曾指向
# ~/caisen-skill，而活副本通过符号链接读桌面的 references/tools，却把账本写进了
# ~/caisen-skill，与桌面主副本（git 管理、台账最全）分叉，两边各自新增、互不同步。
#
# 本脚本检测「权威副本是否唯一」，出现竞争副本 → exit 2（阻断级）。
# 正常情况 exit 0；仅非阻断类提示（如账本有未提交改动）exit 0 + 警告。
import os, sys, json

DEFAULT_ROOT = "/Users/weihaoli/Desktop/蔡森 skill"

def real(p):
    return os.path.realpath(p)

def fail(msg):
    print("❌ DRIFT:", msg)
    sys.exit(2)

def warn(msg):
    print("⚠️  WARN:", msg)

def main():
    root = os.environ.get("CAISEN_ROOT", DEFAULT_ROOT)
    root_real = real(root)
    if not os.path.isdir(root_real):
        fail(f"CAISEN_ROOT 解析结果不存在：{root} -> {root_real}")

    print(f"✓ CAISEN_ROOT = {root} -> {root_real}")

    # 1) 已知镜像路径 ~/caisen-skill：必须是符号链接且指向 root_real，否则视为竞争副本
    home = os.path.expanduser("~")
    mirror = os.path.join(home, "caisen-skill")
    if os.path.lexists(mirror):
        if os.path.islink(mirror):
            if real(mirror) != root_real:
                fail(f"~/caisen-skill 是指向错误目标的符号链接：{real(mirror)} != {root_real}")
            else:
                print("✓ ~/caisen-skill 是指向权威副本的符号链接")
        else:
            # 真实目录 = 竞争副本（曾造成分叉的根因）
            fail(f"~/caisen-skill 仍是真实目录（竞争副本），应改为指向 {root_real} 的符号链接")

    # 2) 活副本技能目录：其数据子目录若以真实目录（非符号链接）存在且指向别处，即为分叉
    live_skill = os.path.expanduser("~/.workbuddy/skills/caisen-10-experts-analyst")
    for sub in ("predictions-ledger", "references", "tools", "market-data-cache", "analysis-report-template"):
        p = os.path.join(live_skill, sub)
        if os.path.lexists(p) and not os.path.islink(p) and os.path.isdir(p):
            rp = real(p)
            if rp != root_real and not rp.startswith(root_real + os.sep):
                fail(f"活副本的数据目录 {sub} 是真实目录且不在权威副本内：{rp}")

    # 3) 账本可读性 + 主键唯一性 + 与权威副本一致
    ledger = os.path.join(root_real, "predictions-ledger", "ledger.jsonl")
    if not os.path.exists(ledger):
        fail(f"权威账本不存在：{ledger}")
    ids = []
    bad = 0
    with open(ledger, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line); ids.append(d.get("id"))
            except Exception:
                bad += 1
    if bad:
        fail(f"权威账本有 {bad} 行无法解析")
    dup = len(ids) - len(set(ids))
    if dup:
        fail(f"权威账本有 {dup} 个重复 id（上次分叉的残留）")
    if os.path.islink(ledger):
        warn(f"权威账本是符号链接 -> {real(ledger)}（可接受，但请确认最终落点唯一）")
    print(f"✓ 账本校验通过：{len(ids)} 条唯一记录，0 解析失败，0 重复")

    # 4) git 未提交改动仅警告（不阻断，避免每次分析都撞墙）
    git_dir = os.path.join(root_real, ".git")
    if os.path.isdir(git_dir):
        try:
            import subprocess
            out = subprocess.run(["git", "-C", root_real, "status", "--porcelain",
                                  "predictions-ledger/ledger.jsonl"],
                                 capture_output=True, text=True)
            if out.stdout.strip():
                warn("账本有未提交改动（建议定期 git commit，勿阻断运行）")
            else:
                print("✓ 账本已纳入 git 版本控制且无未提交改动")
        except Exception:
            pass

    print("\n✅ 无权威副本分叉，环境一致。")
    sys.exit(0)

if __name__ == "__main__":
    main()
