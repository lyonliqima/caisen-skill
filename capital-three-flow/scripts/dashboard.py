"""
资本三流 —— Streamlit 大屏
============================
读取 reports/ 下最新一份报告 JSON，展示三流指标卡 + 合成指数 + 共振判定。
纯展示层，无计算逻辑（计算在 monitor.py / calculator.py）。

运行：streamlit run dashboard.py
"""

import os
import json
import glob
from datetime import date

import streamlit as st

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(SKILL_DIR, "reports")


def load_latest():
    files = sorted(glob.glob(os.path.join(REPORTS_DIR, "capital_three_flow_*.json")), reverse=True)
    if not files:
        return None
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)


st.set_page_config(page_title="资本三流观测", layout="wide")
st.title("💰 资本三流实时观测系统")
st.caption("基于卢麒元资本三流框架 · 费雪方程式 M·V=P·Q 三流拆解")

data = load_latest()
if data is None:
    st.warning("尚未生成报告。请先运行 `python monitor.py --demo` 生成样例报告。")
    st.stop()

as_of = data.get("as_of", date.today())
demo = "（DEMO 样例）" if data.get("demo") else ""
st.markdown(f"**观测日期**：{as_of} {demo}")

vol = data.get("volume", {})
vel = data.get("velocity", {})
dr = data.get("direction", {})
idx = data.get("indices", {})
sc = data.get("score", {})

c1, c2, c3, c4 = st.columns(4)
c1.metric("流量 · M2(同比)", f"{vol.get('m2_yoy')}%", f"M2={vol.get('m2')}")
c2.metric("流速 · V=GDP/M2", vel.get("V_macro"), f"货币乘数={vel.get('money_multiplier')}")
c3.metric("流向 · 市场D系数", dr.get("D_market"), f"外汇D={dr.get('D_fx')}")
fxr = data.get("fx_rate") or {}
fx_disp = f"{fxr.get('rate')}" if fxr.get("rate") is not None else "缺失"
fx_delta = f"当日 {fxr.get('change_pct')}%" if fxr.get("change_pct") is not None else "—"
c4.metric("外部压力 · USD/CNY", fx_disp, fx_delta)

st.divider()
hhi = dr.get("HHI")
scnt = dr.get("sector_count")
if hhi is not None:
    hhi_label = "高度集中" if hhi >= 0.18 else ("分散" if hhi <= 0.08 else "中度集中")
    st.metric("板块资金流集中度 HHI", f"{hhi}（{hhi_label}）", f"覆盖 {scnt} 个行业")
else:
    st.metric("板块资金流集中度 HHI", "缺失", dr.get("HHI_note") or "无数据")

st.divider()
ic1, ic2, ic3 = st.columns(3)
ic1.metric("CFCI 流向综合", idx.get("CFCI"), "-100~+100")
ic2.metric("CFEI 流转效率", idx.get("CFEI"))
ic3.metric("CRI 走资风险", idx.get("CRI"), "0~100 越高越危险")

st.divider()
st.subheader("三流共振判定")
col1, col2, col3, col4 = st.columns(4)
col1.metric("流量打分", sc.get("S_flow"))
col2.metric("流速打分", sc.get("S_velocity"))
col3.metric("流向打分", sc.get("S_direction"))
col4.metric("综合 S", sc.get("S_total"))

verdict_color = {"三流同向共振" : "🟢", "三流背离紊乱" : "🔴"}.get(sc.get("verdict", "")[:6], "🟡")
st.markdown(f"### {verdict_color} {sc.get('verdict')}")

for n in sc.get("notes", []):
    st.caption(f"注：{n}")

st.divider()
st.caption("免责声明：基于方法论的量化演示，不构成投资建议。数据缺口已标注缺失。")
