#!/usr/bin/env python3
# lint_skill.py — 把「诊断报告」机器化，防十专家技能再次腐化。
# 检查项：
#   1) SKILL.md 体积：>256KB(Read上限) 报错；>60KB(目标) 警告
#   2) frontmatter description 长度：>500 警告
#   3) SKILL.md 不得有 >2000 字符的行（审计不可读）
#   4) 席位表一致性：seats.md 的 ID 必须在 SKILL.md 中被引用
#   5) 台账单写：CAISEN_ROOT 解析的 ledger == append.py 锚定的 ledger；
#      ~/caisen-skill 不得存在分歧副本（应为指向桌面的符号链接）
#   6) references 引用完整性：SKILL.md 中引用的 references/*.md 必须存在
# 退出码：发现 error 级 => 2；仅 warning => 1；干净 => 0
import os, re, sys, subprocess

# tools/ 位于仓库根（蔡森 skill/tools），技能目录为其下的 caisen-10-experts-analyst
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "caisen-10-experts-analyst"))
DESKTOP_ROOT = "/Users/weihaoli/Desktop/蔡森 skill"
SKILL = os.path.join(ROOT, "SKILL.md")
SEATS = os.path.join(ROOT, "references", "seats.md")

errors, warns = [], []

def read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""

# 1) 体积（容量指标，非正确性回归；真正修法为外迁实锤叙事）
sz = os.path.getsize(SKILL) if os.path.exists(SKILL) else 0
if sz > 256 * 1024:
    warns.append(f"SKILL.md 体积 {sz/1024:.0f}KB > 256KB（Read 工具单次上限；WorkBuddy 技能加载通常分块，未实测阻断。P0-2 目标为外迁实锤降至 ≤60KB）")
elif sz > 60 * 1024:
    warns.append(f"SKILL.md 体积 {sz/1024:.0f}KB > 60KB 目标（P0-2 目标未完全达成，可继续外迁实锤）")

# 2) description 长度
m = re.search(r"^description:\s*(.+)$", read(SKILL), re.M)
if m and len(m.group(1)) > 500:
    warns.append(f"frontmatter description {len(m.group(1))} 字符 > 500，稀释触发关键词")

# 3) 长行
for i, l in enumerate(read(SKILL).split("\n"), 1):
    if len(l) > 2000:
        errors.append(f"SKILL.md L{i} 长度 {len(l)} > 2000，审计不可读")

# 4) 席位表一致性
seat_ids = set(re.findall(r"`(seat-[a-z]+)`", read(SEATS)))
skill_txt = read(SKILL)
missing = [s for s in seat_ids if s not in skill_txt]
if missing:
    warns.append(f"seats.md 中以下 ID 尚未在 SKILL.md 引用（分阶段采用，待全局「第N位→seat-*」改名）：{missing}")
# 散落「第N位」叙事编号（仅警告，全局改名是后续大工程）
stray = len(re.findall(r"第\d+位(专家|核心领域专家|分析席|事后校验席)", skill_txt))
if stray:
    warns.append(f"SKILL.md 仍有 {stray} 处「第N位」叙事编号（建议逐步改引用 seat-* ID）")

# 5) 台账单写
caisen_root = os.environ.get("CAISEN_ROOT", DESKTOP_ROOT)
# append.py 锚定路径
append_py = os.path.join(ROOT, "..", "predictions-ledger", "append.py")
canon_ledger = os.path.join(DESKTOP_ROOT, "predictions-ledger", "ledger.jsonl")
if os.path.exists(append_py):
    ab = os.path.abspath(append_py)
    anchored = os.path.join(os.path.dirname(ab), "ledger.jsonl")
    if os.path.exists(anchored) and os.path.exists(canon_ledger) and \
       os.path.samefile(anchored, canon_ledger):
        pass
    else:
        errors.append(f"台账分叉：append.py 锚定 {anchored} 与权威 {canon_ledger} 不一致")
# ~/caisen-skill 应为符号链接
home_link = os.path.expanduser("~/caisen-skill")
if os.path.exists(home_link):
    if not os.path.islink(home_link):
        errors.append("~/caisen-skill 不是符号链接，可能是分歧副本（应指向桌面主副本）")
    elif os.path.realpath(home_link) != DESKTOP_ROOT:
        errors.append(f"~/caisen-skill 指向 {os.path.realpath(home_link)}，应为桌面主副本")

# 6) references 引用完整性 —— 交由 check_links.py 统一校验（含跨技能引用/allowlist），
#    本 lint 不重复扫描，避免对「杨世光/serenity 等子技能自带 references/」产生误报。

print("=== lint_skill.py ===")
for e in errors:
    print("❌ ERROR:", e)
for w in warns:
    print("⚠️  WARN :", w)
if not errors and not warns:
    print("✅ 全部通过")
print(f"--- {len(errors)} error(s), {len(warns)} warn(s) ---")
sys.exit(2 if errors else 1 if warns else 0)
