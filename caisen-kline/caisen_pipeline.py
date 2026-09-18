# -*- coding: utf-8 -*-
"""蔡森方法论 · S8 全链路编排（正式 skill 的执行核心）
=================================================================
把分散的模块串成一条「说一个标的 → 出图 + 文字」的流水线：

  用户输入(标的)
       │  [tdx_lookup_stock + tdx_kline]  ← Agent 调 MCP 取数
       ▼
   raw_json
       ├─ caisen_data.build_request + parse_kline_json   (S1 解析 + S6 守卫)
       ├─ caisen_ab.analyze                              (S2 颈线/等幅 + S5 失败识别已内嵌)
       ├─ caisen_narrative.render_signal + build_report  (S3 出图 + 文字 + C1-C4)
       └─ 返回 {png, report, sig, meta}

设计要点：
  - run(raw_json, query, expect_name, ...) 负责「原始 JSON → 成品」整段；
    S6 守卫在 parse_kline_json 内：不支持市场 / 空数据 / 标的错位一律上抛异常，
    绝不静默返空（见 caisen_data）。
  - analyze_and_render(df, meta, ...) 是「已解析 df → 成品」的可复用内核，
    便于测试与后续接 westock-data 等兜底源。

所有结论均为几何观察、非投资建议；C1-C4 由 caisen_narrative 强制注入。
"""
from __future__ import annotations
import os
from pathlib import Path
import pandas as pd

from caisen_data import build_request, parse_kline_json
from caisen_ab import analyze, ABParams
from caisen_narrative import render_signal, build_report


def analyze_and_render(df: pd.DataFrame, meta, out_dir: str = ".",
                       title: str | None = None, out_name: str | None = None,
                       dpi: int = 250) -> dict:
    """已解析 df → 出图 + 文字。返回 {png, report, sig, meta}。"""
    sig = analyze(df, ABParams())                 # S2 + S5(失败识别) 已内嵌
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    # D4 文件名必须带市场键：上证指数与平安银行同为 000001，
    #    只用 code 命名会让后跑的那张 **静默覆盖** 前一张（跑批时实测复现）。
    if out_name is None:
        out_name = f"{meta.code}_{meta.market}_caisen.png"
    out = os.path.join(out_dir, out_name)
    if title is None:
        title = (f"{meta.name} {meta.code} · {meta.period_label}"
                 f"（{meta.adjust_label} {meta.snapshot} 非实时）\n"
                 f"蔡森《多空轉折一手抓》A招·颈线识别 + B招·等幅满足")
    render_signal(sig, df, meta, out, title=title, dpi=dpi)   # S3
    report = build_report(sig, meta)
    return dict(png=out, report=report, sig=sig, meta=meta)


def run(raw_json: dict, query: str, expect_name: str, market_hint=None,
       period: int = 4, out_dir: str = ".", setcode: int | None = None,
       tq_flag: int = 1, out_name: str | None = None, dpi: int = 250) -> dict:
    """原始 tdx JSON → 成品。S6 守卫在 parse_kline_json 内上抛异常。

    query       : 用户输入的代码或名称（用于 build_request 推导市场）
    expect_name : tdx_lookup_stock 查到的准确名称（语义防线，拦错标的，必填）
    market_hint : 如 "CN_SH" / "HK" / "INDEX_CN" / "ETF_SH"，可加速或纠正市场判定
    setcode     : 同一市场内还需区分时显式指定（如深证系列指数 399xxx 在 setcode=0）
    tq_flag     : 复权，1=前复权（默认）/ 0=不复权 / 2=后复权，须与取数时一致
    """
    req = build_request(query, market_hint, expect_name=expect_name,
                        period=period, setcode=setcode, tq_flag=tq_flag)
    # D5：必须传 req["expect"] 子字典，传整包会让四道语义校验静默失效。
    # （parse_kline_json 已做兼容兜底，这里仍显式取，保持调用语义清晰。）
    df, meta = parse_kline_json(raw_json, req["expect"])   # 不支持 / 空 / 错位 → 异常
    return analyze_and_render(df, meta, out_dir=out_dir, out_name=out_name, dpi=dpi)
