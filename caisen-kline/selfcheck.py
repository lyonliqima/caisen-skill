# -*- coding: utf-8 -*-
"""
caisen-kline 自检脚本 —— 装完先跑这个，30 秒确认环境是否就绪。

用法：
    python selfcheck.py            # 完整自检（含跑一次样本出图）
    python selfcheck.py --quick    # 只查依赖与字体，不跑图

它**不能**替你检查通达信连接（那在 WorkBuddy 连接器管理里看），
但能排掉 90% 的「装了但用不了」：依赖缺失、字体缺失、包不完整、代码跑不通。
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"
issues = []


def line(tag, msg):
    print(f"{tag} {msg}")


print("=" * 64)
print("caisen-kline 自检")
print("=" * 64)

# --- 1. Python 版本 ---------------------------------------------------------
print("\n[1/5] Python 环境")
v = sys.version_info
line(OK if v >= (3, 9) else BAD, f"Python {v.major}.{v.minor}.{v.micro}（需 >= 3.9）")
if v < (3, 9):
    issues.append("Python 版本过低，请升级到 3.9+")

# --- 2. 依赖 ----------------------------------------------------------------
print("\n[2/5] 依赖包")
for mod, hint in [("pandas", "pandas>=1.3"),
                  ("matplotlib", "matplotlib>=3.4"),
                  ("mplfinance", "mplfinance>=0.12")]:
    try:
        m = __import__(mod)
        line(OK, f"{mod} {getattr(m, '__version__', '?')}")
    except Exception as e:
        line(BAD, f"{mod} 缺失 → pip install -r requirements.txt  （{e}）")
        issues.append(f"缺少依赖 {mod}")

# --- 3. 包完整性 ------------------------------------------------------------
print("\n[3/5] 包完整性")
need = ["SKILL.md", "caisen_pipeline.py", "caisen_ab.py", "caisen_data.py",
        "caisen_narrative.py", "caisen_chart.py", "caisen_failure.py",
        # 测试样本（历史上曾漏打，导致 3 套测试在用户端直接崩）
        "data/600519_daily.csv", "data/raw/600460_d4_tq1.json"]
missing = [f for f in need if not (HERE / f).exists()]
line(OK if not missing else BAD,
     f"核心文件齐全（{len(need)} 项）" if not missing else f"缺少文件: {missing}")
if missing:
    issues.append("包不完整，请重新下载安装")

# --- 4. 中文字体 ------------------------------------------------------------
print("\n[4/5] 中文字体（自动探测）")
try:
    sys.path.insert(0, str(HERE))
    from caisen_chart import CN_FONTS
    if CN_FONTS and CN_FONTS != ["DejaVu Sans"]:
        line(OK, f"可用 CJK 字体: {', '.join(CN_FONTS[:4])}")
    else:
        line(WARN, "未探测到 CJK 字体 → 出图中文会显示为方块")
        line("      ", "macOS: 系统自带；Windows: 自带微软雅黑；Linux: apt install fonts-wqy-zenhei")
        issues.append("缺中文字体（出图中文会变方块）")
except Exception as e:
    line(BAD, f"字体探测失败: {e}")
    issues.append("字体探测失败")

# --- 5. 端到端跑一次样本 ----------------------------------------------------
print("\n[5/5] 端到端样本测试（离线数据，不依赖通达信）")
if "--quick" in sys.argv:
    line(WARN, "已跳过（--quick）")
else:
    import json
    sample = HERE / "data" / "raw" / "600460_d4_tq1.json"
    if not sample.exists():
        line(WARN, f"样本缺失（{sample.name}），跳过（不影响实际使用）")
    else:
        try:
            txt = sample.read_text(encoding="utf-8")
            raw, _ = json.JSONDecoder().raw_decode(txt[txt.find("{"):])
            import caisen_pipeline as P
            out = Path(tempfile.mkdtemp(prefix="caisen_selfcheck_"))
            res = P.run(raw, query="600460", expect_name="士兰微",
                        market_hint="CN_SH", setcode=1, out_dir=str(out), dpi=100)
            png = Path(res["png"])
            line(OK if png.exists() else BAD,
                 f"出图成功: {png}  ({png.stat().st_size // 1024} KB)" if png.exists()
                 else "流程跑完但没生成图片")
            line(OK, f"文字分析 {len(res['report'].splitlines())} 行，"
                     f"C1-C4 {'已' if all(k in res['report'] for k in ('C1', 'C2', 'C3', 'C4')) else '未'}注入")
            if not png.exists():
                issues.append("端到端出图失败")
        except Exception as e:
            line(BAD, f"端到端失败: {type(e).__name__}: {str(e)[:120]}")
            issues.append(f"端到端失败: {type(e).__name__}")

# --- 汇总 -------------------------------------------------------------------
print("\n" + "=" * 64)
if issues:
    print("自检未完全通过，需处理：")
    for i, s in enumerate(issues, 1):
        print(f"  {i}. {s}")
else:
    print("自检全部通过 ✅  本机环境可用于分析。")
print("\n⚠ 还差一步（自检查不到）：「通达信 tdx-connector」连接状态。")
print("   请到 WorkBuddy → 连接器管理 → 找到「通达信」→ 启用并点「信任」，")
print("   确认显示「已连接 / 绿色」后，再让 AI 分析具体标的。")
print("=" * 64)
sys.exit(1 if issues else 0)
