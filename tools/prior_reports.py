#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史研判检索器 —— 「蔡森十二专家」开工前第 0.2 条的执行器
================================================================================

解决什么问题
------------
同一标的会被**反复分析**（台账 306 条记录 / 236 个标的；output/ 35+ 篇报告）。
开工前不检索上轮，等于每次从零开始：
  ① 结论漂移无人发现（这次偏多、下次偏空，中间没有任何机制追问「为什么变了」）；
  ② 上轮 miss 的错因不传承，重复交同一份学费；
  ③ 已经打成 miss/void 的判断被当成锚继续用。

本脚本把「看看最近有没有分析过类似的」变成一条命令：
  - 扫五个源：预测台账 / output 报告 / references 方法论 / 路口大爷观点记录 / _runs 产物
  - `--brief` 直接产出「上轮研判摘要 + 本轮待回应问题清单」（俗称「跑一轮」）：
    不是罗列历史，而是**机械生成本轮必须逐条回答的问题**。

设计纪律（与框架既有铁律一致）
------------------------------
  - 「学步骤不抄结论」：方法论命中只给文件与 M 系列编号，绝不把历史方向当本轮结论；
  - 独立性铁律：本脚本只检索**框架自己的历史**，不检索外部机构观点
    （外部共识的检索在第 5.7 步、结论冻结后才允许，两者时点不可交换）；
  - 时间衰减：默认窗口 365 天；miss/partial/void 记录不受窗口限制（错因必须传承）。

用法
----
  python3 tools/prior_reports.py --query "CJ2701 红枣"                 # 人读列表
  python3 tools/prior_reports.py --query "玻璃" --json                 # 机读
  python3 tools/prior_reports.py --query "生猪 反弹" --brief           # 跑一轮产物（stdout）
  python3 tools/prior_reports.py --query "热卷" --brief --out _runs/briefing/prior-hc.md
  python3 tools/prior_reports.py --self-test                           # 自测（fixture 注入）

退出码：0 = 正常运行（有无命中都给 0，检索失败不阻断分析，纪律由报告结构把关）
        1 = 自测失败 / 参数错误        3 = 内部错误（文件损坏等）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path

# ----------------------------------------------------------------------------- 常量

DEFAULT_WINDOW_DAYS = 365          # 「最近有没有分析过」的默认窗口
MISS_STATUSES = {"miss", "partial", "void"}   # 错因必须传承，不受窗口限制
HIGH_CONF = 75                     # 上轮高置信线：反向须 ≥2 条 T1 新证据
STALE_DAYS = 90                    # 上轮距今超此天数 → 关键前提须复核

# 期货品种中文名 → 合约代码前缀（用于「红枣」命中 symbol「CJ2701 红枣」这类）
COMMODITY_ALIASES = {
    "红枣": ["CJ"], "生猪": ["LH"], "仔猪": ["LH"], "猪肉": ["LH"],
    "玻璃": ["FG"], "纯碱": ["SA"], "烧碱": ["SH"], "工业硅": ["SI"],
    "多晶硅": ["PS"], "锰硅": ["SM"], "硅铁": ["SF"], "尿素": ["UR"],
    "白糖": ["SR"], "原糖": ["SR"], "棉花": ["CF"], "棉纱": ["CY"],
    "苹果": ["AP"], "棕榈油": ["P"], "棕榈": ["P"], "菜粕": ["RM"],
    "菜油": ["OI"], "菜籽": ["R"], "豆粕": ["M"], "豆油": ["Y"],
    "豆一": ["A"], "豆二": ["B"], "玉米": ["C"], "玉米淀粉": ["CS"],
    "淀粉": ["CS"], "鸡蛋": ["JD"], "花生": ["PK"], "粳米": ["RR"],
    "热卷": ["HC"], "螺纹": ["RB"], "铁矿": ["I"], "焦煤": ["JM"],
    "焦炭": ["J"], "不锈钢": ["SS"], "沪铝": ["AL"], "沪镍": ["NI"],
    "沪锡": ["SN"], "沪锌": ["ZN"], "沪铅": ["PB"], "沪铜": ["CU"],
    "黄金": ["AU"], "白银": ["AG"], "氧化铝": ["AO"], "PVC": ["V"],
    "聚丙烯": ["PP"], "塑料": ["L"], "甲醇": ["MA"], "PTA": ["TA"],
    "乙二醇": ["EG"], "苯乙烯": ["EB"], "纯苯": ["EB"], "沥青": ["BU"],
    "燃油": ["FU"], "原油": ["SC"], "纸浆": ["SP"], "橡胶": ["RU"],
    "20号胶": ["NR"], "碳酸锂": ["LC"], "集运欧线": ["EC"],
    "沪深300": ["IF"], "上证50": ["IH"], "中证500": ["IC"],
    "中证1000": ["IM"], "上证指数": ["000001"], "沪指": ["000001"],
    "深证成指": ["399001"], "创业板指": ["399006"],
}

# 指数/个股代码：sh/sz 前缀或裸 6 位
INDEX_NAMES = {
    "000001": "上证指数", "399001": "深证成指", "399006": "创业板指",
    "000300": "沪深300", "000688": "科创50", "000016": "上证50",
    "000905": "中证500",
}

CONTRACT_RE = re.compile(r"\b([A-Z]{1,3})(\d{3,4})\b")     # CJ2701 / HC2701
CODE6_RE = re.compile(r"\b(?:(sh|sz|SH|SZ))?(\d{6})\b")    # 600722 / sh600722
CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

STATUS_CN = {
    "open": "有效·待验证", "miss": "❌已判miss", "partial": "⚠️部分命中",
    "void": "🚫已作废", "hit": "✅命中",
}


# ----------------------------------------------------------------------------- 工具

def repo_root() -> Path:
    """仓库根 = 本脚本上级目录（tools/ 的上一级）。测试用 --root 覆盖。"""
    return Path(__file__).resolve().parent.parent


def _today() -> date:
    return date.today()


def parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def days_between(d1: date, d2: date) -> int:
    return (d1 - d2).days


def slugify(query: str) -> str:
    """文件名用 slug：保留中英数字，其余折叠为 -"""
    s = re.sub(r"[\s]+", "-", query.strip())
    s = re.sub(r"[^\w\u4e00-\u9fff-]", "", s)
    return s[:40] or "query"


# ----------------------------------------------------------------------------- 查询解析

def parse_query(query: str) -> dict:
    """从检索式抽取：中文品种名 / 合约代码 / 6位代码 / 泛关键词"""
    names, codes, stocks = [], [], []

    # ① 合约代码（CJ2701 → code=CJ, full=CJ2701）
    for m in CONTRACT_RE.finditer(query):
        code, full = m.group(1), m.group(0)
        if (code, full) not in codes:
            codes.append((code, full))

    # ② 6 位代码（sh600722 / 600722）；带 sh/sz 前缀的保留全串
    for m in CODE6_RE.finditer(query):
        prefix, digits = m.group(1), m.group(2)
        token = (prefix.lower() + digits) if prefix else digits
        if token not in stocks:
            stocks.append(token)

    # ③ 中文品种名（最长优先，避免「玉米」先于「玉米淀粉」匹配）
    for name in sorted(COMMODITY_ALIASES, key=len, reverse=True):
        if name in query:
            names.append(name)
            for code in COMMODITY_ALIASES[name]:
                # 指数类别名给的是 6 位代码而非合约前缀
                if len(code) == 6:
                    if code not in stocks:
                        stocks.append(code)
                elif (code, code) not in codes:
                    codes.append((code, code))

    # ④ 泛关键词（CJK 连续串，长度 ≥2，用于文件名/正文弱匹配）
    keywords = [k for k in CJK_RE.findall(query) if len(k) >= 2]

    return {"names": names, "codes": codes, "stocks": stocks,
            "keywords": keywords, "raw": query.strip()}


def _code_hit_symbol(code: str, symbol: str) -> bool:
    """裸代码必须后接数字才算命中：CJ 命中 CJ2701，但 C 不命中 CJ2701、J 不命中 JD2701。"""
    return re.match(rf"^{re.escape(code)}\d", symbol) is not None


def _code_hit_text(code: str, upper_text: str) -> bool:
    """正文/文件名版：代码前不能是字母（防 PP2701 被 P 命中），后必须接数字。"""
    return re.search(rf"(?<![A-Za-z]){re.escape(code)}\d", upper_text) is not None


def match_symbol(symbol: str, q: dict) -> bool:
    """台账 symbol 命中判定（严格：代码前缀 / 中文名 / 6位代码）"""
    if not symbol:
        return False
    sym = symbol.strip()
    for name in q["names"]:
        if name in sym:
            return True
    for code, full in q["codes"]:
        # full 带数字（CJ2701）才允许 startswith；裸代码（CJ）只能走「前缀+数字」闸，
        # 否则 C 会命中 CJ2701、J 会命中 JD2701
        if full != code and sym.startswith(full):
            return True
        if _code_hit_symbol(code, sym):
            return True
    for st in q["stocks"]:
        digits = st[-6:]
        if digits in sym:
            return True
        # sh000001 ↔ 「000001」两种写法互通
        if sym.replace("sh", "").replace("sz", "").startswith(digits):
            return True
    return False


def match_text(text: str, q: dict, weak: bool = True) -> bool:
    """文件名/正文命中判定：强匹配（名/代码，大小写不敏感）+ 弱匹配（泛关键词）"""
    if not text:
        return False
    for name in q["names"]:
        if name in text:
            return True
    upper = text.upper()
    for code, full in q["codes"]:
        if full != code and full.upper() in upper:
            return True
        if _code_hit_text(code, upper):
            return True
    for st in q["stocks"]:
        if st[-6:] in text:
            return True
    if weak:
        # 泛关键词：任意一个 CJK 串出现即弱命中（权重低于强匹配）
        for kw in q["keywords"]:
            if kw in text:
                return True
    return False


# ----------------------------------------------------------------------------- 各源扫描

def scan_ledger(root: Path, q: dict, window_days: int, top: int) -> list:
    """预测台账：结构化上轮结论（最核心的源）"""
    path = root / "predictions-ledger" / "ledger.jsonl"
    if not path.exists():
        return []
    hits, today = [], _today()
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                sys.stderr.write(f"⚠️ ledger.jsonl 第 {ln} 行 JSON 损坏，已跳过\n")
                continue
            if not match_symbol(rec.get("symbol", ""), q):
                continue
            d = parse_date(rec.get("date"))
            age = days_between(today, d) if d else None
            in_window = age is not None and age <= window_days
            is_miss = rec.get("status") in MISS_STATUSES
            if not in_window and not is_miss:
                continue
            hits.append({
                "source": "ledger",
                "date": rec.get("date"),
                "age_days": age,
                "id": rec.get("id"),
                "symbol": rec.get("symbol"),
                "direction": rec.get("direction"),
                "target_range": rec.get("target_range"),
                "time_window": rec.get("time_window"),
                "confidence": rec.get("confidence"),
                "falsification": rec.get("falsification"),
                "status": rec.get("status"),
                "actual_return": rec.get("actual_return"),
                "review_date": rec.get("review_date"),
                "market_regime": rec.get("market_regime"),
                "methodology": rec.get("methodology"),
                "updates": rec.get("updates") or [],
                "out_of_window": not in_window,
                "path": str(path),
            })
    hits.sort(key=lambda r: (r["date"] or "", r["id"] or ""), reverse=True)
    return hits[:top]


def scan_reports(root: Path, q: dict, top: int) -> list:
    """output/ 报告与日志（标题命中）"""
    hits = []
    out_dir = root / "output"
    if not out_dir.is_dir():
        return []
    cands = []
    for sub in ("journal",):
        p = out_dir / sub
        if p.is_dir():
            cands += [x for x in p.iterdir() if x.is_file()]
    cands += [x for x in out_dir.iterdir() if x.is_file()]
    for p in cands:
        if not match_text(p.name, q):
            continue
        m = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", p.name)
        d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
        hits.append({"source": "report", "date": d, "title": p.stem,
                     "path": str(p)})
    hits.sort(key=lambda r: (r["date"] or "", r["title"]), reverse=True)
    return hits[:top]


def scan_methodology(root: Path, q: dict, top: int) -> list:
    """references/ 方法论（M 系列）：只学步骤不抄结论"""
    hits = []
    ref_dir = root / "references"
    if not ref_dir.is_dir():
        return []
    for p in sorted(ref_dir.glob("*.md")):
        try:
            head = p.read_text(encoding="utf-8")[:600]
        except (OSError, UnicodeDecodeError):
            continue
        if not match_text(p.name + "\n" + head, q):
            continue
        tags = sorted(set(re.findall(r"\bM-[A-Za-z0-9]+\b", head)))
        title = head.splitlines()[0].lstrip("# ").strip() if head else p.stem
        hits.append({"source": "methodology", "title": title,
                     "m_tags": tags[:12], "path": str(p)})
    return hits[:top]


def scan_lukou(root: Path, q: dict, top: int) -> list:
    """路口大爷观点记录（时间衰减观点的历史锚）"""
    hits = []
    d = root / "lukou-daye"
    if not d.is_dir():
        return []
    for p in sorted(d.glob("*.md")):
        try:
            head = p.read_text(encoding="utf-8")[:1500]
        except (OSError, UnicodeDecodeError):
            continue
        if not match_text(p.name + "\n" + head, q):
            continue
        hits.append({"source": "lukou-daye", "title": p.stem, "path": str(p)})
    return hits[:top]


def scan_runs(root: Path, q: dict, top: int) -> list:
    """_runs/ 运行产物（中间过程：方法痕迹）"""
    hits = []
    d = root / "_runs"
    if not d.is_dir():
        return []
    for p in sorted(d.iterdir()):
        if not match_text(p.name, q):
            continue
        m = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", p.name)
        hits.append({"source": "run", "date": f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None,
                     "title": p.name, "path": str(p)})
    hits.sort(key=lambda r: (r["date"] or "", r["title"]), reverse=True)
    return hits[:top]


# ----------------------------------------------------------------------------- 待回应问题清单（机械生成）

def build_questions(ledger_hits: list, method_hits: list) -> list:
    """
    「跑一轮」的核心产出：本轮必须逐条回答的问题。
    按**类型聚合**而非按记录逐条展开——同一纪律重复 12 遍会被专家当成噪音忽略；
    只有「错因传承」这类逐案不同的问题才逐条列。
    """
    qs = []

    # ① 错因传承（逐条：每个 miss/void 的错因都不同，最高优先）
    for r in ledger_hits:
        status = r.get("status")
        if status in MISS_STATUSES:
            ret = r.get("actual_return")
            ret_s = f"，actual_return={ret}" if ret is not None else ""
            qs.append(
                f"上轮 {r['id']}（{r['date']}·{r['symbol']}）已判 "
                f"{STATUS_CN.get(status, status)}{ret_s} → 本轮**必须先归因**："
                f"错在数据/方法/时点/纪律哪一层，并说明本轮做了什么不一样的事；"
                f"不得直接复用其结论框架。")

    # ② 证伪位核对（合并为一条，列最近 5 条）
    fals = [r for r in ledger_hits if r.get("falsification")][:5]
    if fals:
        items = "；".join(
            f"{r['id']}「{(r['falsification'] or '')[:60]}」" for r in fals)
        qs.append(
            f"开工第一步先取实时价核对以下 {len(fals)} 条证伪位是否已打穿——{items}。"
            f"已打穿的判断作废，不得作为本轮锚点。")

    # ③ 高置信反向门槛（合并）
    high = [r for r in ledger_hits
            if isinstance(r.get("confidence"), int) and r["confidence"] >= HIGH_CONF]
    if high:
        items = "、".join(f"{r['id']}({r['confidence']})" for r in high)
        qs.append(
            f"上轮高置信记录：{items} → 本轮若方向相反，须 ≥2 条 T1 级新证据；"
            f"否则按「静默翻转」处理，置信度强制 ≤60。")

    # ④ 显式回应标注（一条通用纪律）
    if any(r.get("direction") for r in ledger_hits):
        qs.append(
            f"上轮 {len(ledger_hits)} 条同标的方向记录（见上表）→ 本轮每位核心专家发言必须显式标注"
            f"「上轮回应：继承 / 修正 / 推翻」+ 理由；无标注的专家结论不计入综合。")

    # ⑤ 时间衰减（合并）
    stale = [r for r in ledger_hits
             if r.get("age_days") is not None and r["age_days"] > STALE_DAYS]
    if stale:
        items = "、".join(f"{r['id']}({r['age_days']}天)" for r in stale[:6])
        qs.append(
            f"以下记录距今超 {STALE_DAYS} 天：{items} → 数据基础可能已变，"
            f"引用前须复核关键前提是否仍成立（时间衰减）。")

    # ⑥ 台账落账方式（一条，指向窗口内最新记录）
    in_window = [r for r in ledger_hits if not r.get("out_of_window")]
    if in_window:
        qs.append(
            f"本轮落账优先用 `predictions-ledger/append.py update --id {in_window[0]['id']} "
            f"--trigger <触发条件> --new-confidence <N>`（贝叶斯更新），而非新建平行记录"
            f"——除非方向/期限/幅度发生实质变化。")

    # ⑦ 方法论（逐条：每个方法论套用与否都需单独声明）
    for m in method_hits:
        tags = "·".join(m["m_tags"]) or "（未标注 M 编号）"
        qs.append(
            f"命中方法论《{m['title']}》（{tags}）→ 本轮须声明是否套用；"
            f"套用则按步骤执行，**只学步骤不抄结论**。")

    if not ledger_hits and not method_hits:
        qs.append("无历史研判命中 → 本轮为首轮分析，报告 13.9 节写「首轮分析，无上轮对照」。")
    elif not ledger_hits and method_hits:
        qs.append("无同标的历史研判，但命中方法论 → 按上述方法论步骤执行，13.9 节注明「首轮 + 方法论套用」。")

    # 去重
    seen, out = set(), []
    for x in qs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ----------------------------------------------------------------------------- 摘要渲染

def _fmt_row(r: dict) -> str:
    conf = r.get("confidence")
    conf_s = str(conf) if isinstance(conf, int) else "—"
    tr = (r.get("target_range") or "—").replace("|", "/")
    fals = (r.get("falsification") or "—").replace("|", "/")
    st = STATUS_CN.get(r.get("status"), r.get("status") or "—")
    oow = "（窗口外·错因传承）" if r.get("out_of_window") else ""
    return (f"| {r.get('date') or '—'} | {r.get('id') or '—'} | {r.get('symbol') or '—'} "
            f"| {r.get('direction') or '—'} | {tr[:40]} | {conf_s} | {fals[:50]} | {st}{oow} |")


def render_brief(q: dict, ledger_hits: list, report_hits: list,
                 method_hits: list, lukou_hits: list, run_hits: list) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []
    L.append(f"# 上轮研判摘要与待回应清单（第0.2条·跑一轮）")
    L.append("")
    L.append(f"- 生成时间：{now}")
    L.append(f"- 检索式：`{q['raw']}`")
    L.append(f"- 命中统计：台账 **{len(ledger_hits)}** 条 / 报告 **{len(report_hits)}** 篇 / "
             f"方法论 **{len(method_hits)}** 篇 / 路口大爷 **{len(lukou_hits)}** 条 / "
             f"运行产物 **{len(run_hits)}** 项")
    L.append("")
    L.append("> 本清单由 `tools/prior_reports.py` 机械生成。**只检索框架自己的历史，不引入外部机构观点**"
             "（外部共识在第 5.7 步、结论冻结后才允许检索——两个时点不可交换）。")
    L.append("")

    L.append("## 一、台账命中（时间倒序）")
    L.append("")
    if ledger_hits:
        L.append("| 日期 | ID | 标的 | 方向 | 目标区间 | 置信度 | 证伪位 | 状态 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in ledger_hits:
            L.append(_fmt_row(r))
    else:
        L.append("（无命中）")
    L.append("")

    if report_hits or run_hits or lukou_hits:
        L.append("## 二、报告 / 运行产物 / 观点记录命中")
        L.append("")
        for r in report_hits:
            L.append(f"- 📄 {r.get('date') or '日期未知'} 《{r['title']}》 `{r['path']}`")
        for r in run_hits:
            L.append(f"- 🧩 {r.get('date') or '日期未知'} {r['title']} `{r['path']}`")
        for r in lukou_hits:
            L.append(f"- 🧓 路口大爷《{r['title']}》 `{r['path']}`")
        L.append("")

    L.append("## 三、方法论命中（只学步骤，不抄结论）")
    L.append("")
    if method_hits:
        for m in method_hits:
            L.append(f"- 📚 《{m['title']}》 M系列：{', '.join(m['m_tags']) or '—'} `{m['path']}`")
    else:
        L.append("（无命中）")
    L.append("")

    L.append("## 四、本轮待回应问题清单（必须逐条回答）")
    L.append("")
    for i, question in enumerate(build_questions(ledger_hits, method_hits), 1):
        L.append(f"{i}. {question}")
    L.append("")
    L.append("---")
    L.append("**消费纪律**：本摘要随第 0.1 条背景包一并分发给 12 位专家；"
             "报告须含 13.9 节「与上轮研判的对比」；无命中时不写对比节、写「首轮分析」声明。")
    return "\n".join(L)


def render_human(q: dict, ledger_hits: list, report_hits: list,
                 method_hits: list, lukou_hits: list, run_hits: list) -> str:
    L = []
    L.append(f"=== 历史研判检索 · 检索式「{q['raw']}」 ===")
    L.append(f"解析：品种名 {q['names'] or '—'} · 合约代码 {q['codes'] or '—'} · "
             f"6位代码 {q['stocks'] or '—'} · 关键词 {q['keywords'] or '—'}")
    L.append("")
    L.append(f"—— 台账命中 {len(ledger_hits)} 条（时间倒序）——")
    if ledger_hits:
        L.append(f"{'日期':<12}{'ID':<18}{'标的':<22}{'方向':<14}{'置信':<6}{'状态'}")
        for r in ledger_hits:
            L.append(f"{r.get('date') or '—':<12}{r.get('id') or '—':<18}"
                     f"{(r.get('symbol') or '—')[:20]:<22}{(r.get('direction') or '—')[:12]:<14}"
                     f"{str(r.get('confidence') or '—'):<6}"
                     f"{STATUS_CN.get(r.get('status'), r.get('status') or '—')}")
    else:
        L.append("（无）")
    L.append("")
    L.append(f"—— 报告命中 {len(report_hits)} 篇 ——")
    for r in report_hits[:8]:
        L.append(f"  {r.get('date') or '??'} 《{r['title']}》")
    L.append(f"—— 方法论命中 {len(method_hits)} 篇 ——")
    for m in method_hits[:8]:
        L.append(f"  《{m['title']}》 [{', '.join(m['m_tags']) or '—'}]")
    L.append(f"—— 路口大爷 {len(lukou_hits)} 条 / 运行产物 {len(run_hits)} 项 ——")
    for r in (lukou_hits + run_hits)[:8]:
        L.append(f"  {r['title']}")
    L.append("")
    L.append("提示：加 --brief 生成「上轮摘要 + 待回应问题清单」（跑一轮产物）。")
    return "\n".join(L)


# ----------------------------------------------------------------------------- 主流程

def run(query: str, root: Path, window_days: int, top: int, as_json: bool,
        brief: bool, out_path: str | None) -> int:
    q = parse_query(query)
    if not (q["names"] or q["codes"] or q["stocks"] or q["keywords"]):
        sys.stderr.write("✗ 检索式无法解析出任何标的/关键词\n")
        return 1

    ledger_hits = scan_ledger(root, q, window_days, top)
    report_hits = scan_reports(root, q, top)
    method_hits = scan_methodology(root, q, top)
    lukou_hits = scan_lukou(root, q, top)
    run_hits = scan_runs(root, q, top)

    if as_json:
        print(json.dumps({
            "query": q["raw"], "parsed": {k: q[k] for k in ("names", "codes", "stocks", "keywords")},
            "window_days": window_days,
            "counts": {"ledger": len(ledger_hits), "report": len(report_hits),
                       "methodology": len(method_hits), "lukou-daye": len(lukou_hits),
                       "run": len(run_hits)},
            "ledger": ledger_hits, "report": report_hits,
            "methodology": method_hits, "lukou-daye": lukou_hits, "run": run_hits,
            "questions": build_questions(ledger_hits, method_hits),
        }, ensure_ascii=False, indent=2))
        return 0

    if brief:
        text = render_brief(q, ledger_hits, report_hits, method_hits, lukou_hits, run_hits)
        if out_path:
            p = Path(out_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            sys.stderr.write(f"✓ 已写 {p}\n")
        else:
            print(text)
        return 0

    print(render_human(q, ledger_hits, report_hits, method_hits, lukou_hits, run_hits))
    return 0


# ----------------------------------------------------------------------------- 自测

def self_test() -> int:
    """fixture 注入：造一个假仓库根，断言匹配逻辑与 brief 生成。"""
    import tempfile
    import shutil

    tmp = Path(tempfile.mkdtemp(prefix="prior_reports_selftest_"))
    try:
        (tmp / "predictions-ledger").mkdir(parents=True)
        (tmp / "output" / "journal").mkdir(parents=True)
        (tmp / "references").mkdir()
        (tmp / "lukou-daye").mkdir()
        (tmp / "_runs").mkdir()

        recs = [
            # 命中：中文名 + 合约代码
            {"id": "P-20260901-001", "date": "2026-09-01", "symbol": "CJ2701 红枣",
             "direction": "偏多", "target_range": "[8000,8600]", "confidence": 78,
             "falsification": "跌破7600认错", "status": "open"},
            # 命中：裸 CJ 前缀
            {"id": "P-20260810-002", "date": "2026-08-10", "symbol": "CJ2609 红枣",
             "direction": "中性", "confidence": 55, "status": "miss",
             "actual_return": -3.2, "falsification": "跌破7000"},
            # 不应命中：C 是玉米，不能命中 CJ（前缀+数字闸）
            {"id": "P-20260701-003", "date": "2026-07-01", "symbol": "C2701 玉米",
             "direction": "偏空", "confidence": 60, "status": "open"},
            # 不应命中：J 是焦炭，不能命中 JD2701
            {"id": "P-20260701-004", "date": "2026-07-01", "symbol": "JD2701 鸡蛋",
             "direction": "偏多", "confidence": 60, "status": "open"},
            # 窗口外但 miss → 必须保留（错因传承）
            {"id": "P-20250101-005", "date": "2025-01-01", "symbol": "CJ2505 红枣",
             "direction": "偏多", "confidence": 70, "status": "miss"},
            # 窗口外且 open → 应被窗口滤掉
            {"id": "P-20250101-006", "date": "2025-01-01", "symbol": "CJ2501 红枣",
             "direction": "偏空", "confidence": 65, "status": "open"},
        ]
        with open(tmp / "predictions-ledger" / "ledger.jsonl", "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.write("{坏行\n")  # 损坏行必须被跳过而不崩

        (tmp / "output" / "红枣CJ2701十二专家分析_2026-10-14.html").write_text("x", encoding="utf-8")
        (tmp / "output" / "journal" / "2026-10-14_生猪红枣反弹研判.md").write_text("x", encoding="utf-8")
        (tmp / "output" / "玻璃十二专家分析_2026-10-15.html").write_text("x", encoding="utf-8")
        (tmp / "references" / "红枣换月伪跳空与持有成本拆分-20261013.md").write_text(
            "# 红枣换月伪跳空\nM-H3b M-H4 换月口径\n", encoding="utf-8")
        (tmp / "references" / "无关的方法论-20260101.md").write_text("# 无关\n", encoding="utf-8")
        (tmp / "lukou-daye" / "examples-0825.md").write_text("# 红枣观点\n时间衰减\n", encoding="utf-8")
        (tmp / "_runs" / "cj2701-20260901").mkdir()

        q = parse_query("CJ2701 红枣")
        ok = True

        def check(name, cond):
            nonlocal ok
            print(f"  {'✅' if cond else '❌'} {name}")
            if not cond:
                ok = False

        # ① 解析
        check("解析出中文名「红枣」", "红枣" in q["names"])
        check("解析出合约代码 CJ/CJ2701", ("CJ", "CJ2701") in q["codes"])

        # ② 符号匹配闸
        check("CJ2701 命中 symbol「CJ2701 红枣」", match_symbol("CJ2701 红枣", q))
        check("CJ2701 命中 symbol「CJ2609 红枣」（裸前缀）", match_symbol("CJ2609 红枣", q))
        check("C 不误命中 CJ2701", not match_symbol("CJ2701 红枣", parse_query("玉米 C2701")))
        check("J 不误命中 JD2701", not match_symbol("JD2701 鸡蛋", parse_query("焦炭 J2701")))
        check("6位代码命中个股", match_symbol("600722 金牛化工", parse_query("600722")))

        # ③ 台账扫描：3 条命中（含窗口外 miss），窗口外 open 被滤
        hits = scan_ledger(tmp, q, DEFAULT_WINDOW_DAYS, 50)
        ids = {h["id"] for h in hits}
        check("台账命中 3 条", len(hits) == 3)
        check("窗口外 open 被滤掉", "P-20250101-006" not in ids)
        check("窗口外 miss 保留（错因传承）", "P-20250101-005" in ids)
        check("玉米/鸡蛋未误命中", "P-20260701-003" not in ids and "P-20260701-004" not in ids)
        check("损坏 JSON 行被跳过不崩", True)
        check("按日期倒序", [h["date"] for h in hits] == sorted([h["date"] for h in hits], reverse=True))

        # ④ 其他源
        check("报告命中 2 篇（标题+日志）", len(scan_reports(tmp, q, 50)) == 2)
        check("玻璃未误命中", len(scan_reports(tmp, parse_query("玻璃 FG"), 50)) == 1)
        mh = scan_methodology(tmp, q, 50)
        check("方法论命中 1 篇", len(mh) == 1)
        check("M 标签提取", "M-H3b" in mh[0]["m_tags"])
        check("路口大爷命中 1 条", len(scan_lukou(tmp, q, 50)) == 1)
        check("_runs 命中 1 项", len(scan_runs(tmp, q, 50)) == 1)

        # ⑤ brief 生成与问题清单
        brief_text = render_brief(q, hits, scan_reports(tmp, q, 50), mh,
                                  scan_lukou(tmp, q, 50), scan_runs(tmp, q, 50))
        check("brief 含四节结构", all(s in brief_text for s in
              ["一、台账命中", "二、报告", "三、方法论命中", "四、本轮待回应问题清单"]))
        check("miss 触发归因问题", any("先归因" in x for x in build_questions(hits, mh)))
        check("证伪位触发核对问题", any("证伪位" in x for x in build_questions(hits, mh)))
        check("高置信触发反向门槛", any("T1 级新证据" in x for x in build_questions(hits, mh)))
        check("方向触发显式回应", any("继承 / 修正 / 推翻" in x for x in build_questions(hits, mh)))
        check("时间衰减触发复核", any("时间衰减" in x for x in build_questions(hits, mh)))
        check("update 落账提示", any("append.py update" in x for x in build_questions(hits, mh)))
        check("方法论只学步骤提示", any("只学步骤不抄结论" in x for x in build_questions(hits, mh)))
        check("无命中时给首轮提示",
              any("首轮分析" in x for x in build_questions([], [])))
        # 聚合验证：同类问题只出现一次（3 条记录不得生成 9 条重复问题）
        qs3 = build_questions(hits, mh)
        check("证伪位问题聚合为一条", sum("证伪位" in x for x in qs3) == 1)
        check("显式回应问题聚合为一条", sum("继承 / 修正 / 推翻" in x for x in qs3) == 1)
        check("update 提示聚合为一条", sum("append.py update" in x for x in qs3) == 1)
        check("问题总数受控（≤8）", len(qs3) <= 8)

        print()
        print("自测结果：" + ("全部通过 ✅" if ok else "存在失败 ❌"))
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description="历史研判检索器（第0.2条·跑一轮）：检索框架自己的上轮研判，生成待回应问题清单")
    ap.add_argument("--query", help="检索式，如 'CJ2701 红枣' / '玻璃' / '600722'")
    ap.add_argument("--root", default=None,
                    help="仓库根目录（默认=本脚本上级目录；测试用）")
    ap.add_argument("--days", type=int, default=DEFAULT_WINDOW_DAYS,
                    help=f"回溯窗口天数（默认 {DEFAULT_WINDOW_DAYS}；miss/partial/void 不受窗口限制）")
    ap.add_argument("--top", type=int, default=12, help="每个源最多返回条数（默认 12）")
    ap.add_argument("--json", action="store_true", help="机读 JSON 输出")
    ap.add_argument("--brief", action="store_true",
                    help="生成「上轮摘要 + 待回应问题清单」（跑一轮产物，markdown）")
    ap.add_argument("--out", default=None, help="brief 输出文件路径（缺省打印到 stdout）")
    ap.add_argument("--self-test", action="store_true", help="运行自测")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if not args.query:
        ap.error("必须给 --query（或用 --self-test）")

    root = Path(args.root).resolve() if args.root else repo_root()
    if not (root / "predictions-ledger").is_dir():
        sys.stderr.write(f"✗ {root} 下找不到 predictions-ledger/，--root 指错了吗？\n")
        sys.exit(3)
    try:
        sys.exit(run(args.query, root, args.days, args.top,
                     args.json, args.brief, args.out))
    except Exception as e:  # 检索失败不静默
        sys.stderr.write(f"✗ 内部错误：{type(e).__name__}: {e}\n")
        sys.exit(3)


if __name__ == "__main__":
    main()
