---
name: caisen-kline
slug: caisen-kline
version: 1.0.3
displayName: 蔡森K线分析
description: 蔡森《多空轉折一手抓》K 线形态分析（已实测支持 A股/港股/商品期货/中证指数/沪深ETF，含跨境QDII；债券、美股、外汇暂不支持）。用户给出带 K 线的标的代码或名称，自动取数→颈线识别(A招)+等幅满足(B招)+失败识别(K招)→出 K 线标注图 + 中文文字分析，含 C1-C4 风险约束，不构成投资建议。当用户给出股票/指数/期货/ETF 代码并希望做形态分析、找买卖点、识别假突破/破底翻、判断多空转折时使用。
---

# 蔡森 K 线分析 Skill

把蔡森方法论（A 招颈线识别 + B 招等幅满足 + K 招失败识别）做成一条「说一个标的 → 出图 + 文字」的自动流水线。**所有结论均为几何观察，非投资建议。**

## 🔧 本机接入状态（2026-09-18 · 已并入「蔡森 skill」体系）

- **归属**：本引擎已作为 **`caisen-10-experts-analyst`（蔡森十二专家）中 🟠 蔡森席位的技术形态出图执行器**接入，调用协议见该技能 SKILL.md 的「📉 caisen-kline 技术形态出图引擎」专章。
- **主副本**：`/Users/weihaoli/Desktop/蔡森 skill/caisen-kline`（即 `$CAISEN_ROOT/caisen-kline`）；镜像 `~/.workbuddy/skills/caisen-kline/`。
- **本机 Python（已验证可用，勿另建 venv）**：`/Users/weihaoli/.workbuddy/binaries/python/envs/default/bin/python` —— 内含 pandas 3.0.3 / matplotlib 3.11.0 / mplfinance 0.12.10b0。
- **自检结果（2026-09-18 实机）**：`selfcheck.py` **5/5 全通过**（Python 3.13.12 / 三依赖齐 / 包完整 / CJK 字体探测到 Hiragino Sans GB, STHeiti, PingFang SC, Arial Unicode MS / 离线端到端出图成功）；**回归测试 15 套全绿**（2026-09-20 新增 `test_caisen_trend.py` 45 项后复跑）。
- **统一输出目录**：`$CAISEN_ROOT/output/caisen-kline/`（与 HTML 报告同根，便于报告内嵌引用）。
- **硬前置**：`tdx-connector`（通达信）已连接。

## 适用范围
- **实测走通（可用）**：沪市A股 / 深市A股 / 创业板 / 中证系列指数 / 沪·深 ETF（含跨境 QDII）/ 港股 / 商品期货（上期所·大商所·郑商所·**广期所**）。
- ✅ **广期所（工业硅 SI / 碳酸锂 LC / 多晶硅 PS）：2026-09-20 实测通过，setcode=66**。实测 `tdx_kline(code="SI2610", setcode=66, period=4)` 返回完整 30 根日 K（20260810–20260918），`AttachInfo.Name` 正常为「工业硅2610」。可免传 `market`（`SI/LC/PS` 已在 `_FUT_EXCHANGE` 注册）。v1.0.2 的硬拒绝已解除。
- ⚠ **债券：实测不可用（2026-09-11 复核）**。tdx 对可转债（如 113050）返回空 `Rows` + 空 `AttachInfo`（名称显示「未知」），取不到 K 线。**不要再对用户声称本技能支持债券**；遇债券需求按 S6 明确拒绝并说明数据源未覆盖。
- **不支持（一律明确拒绝，绝不静默出图）**：美股 / 外汇·汇率 / 中金所（IF·IC·IH）/ 上期能源（原油 SC）/ 债券。
  - 判定信号：`tdx_kline` 返回空 `Rows`，或 `AttachInfo` 无 `Name`。此时按 S6 抛 `UnsupportedMarketError`，告知用户「此品种数据源未覆盖」，**不得出图**。
  - 后续可接 westock-data 兜底源扩展覆盖。
- 做空（C2）按市场分支：A股个股不可开空（只能减仓/离场/避险）；期货/外汇/可融券ETF/期权可按机制开空（输出「可做空，需独立确认机制」）。

## ⚠ 前置条件（必读 · 不满足则本技能完全无法运行）

本技能**强依赖外部数据源**，第一次使用请逐项确认：

**1. 必须连接「通达信 tdx-connector」（硬前置，无替代方案）**
- 本技能所有 K 线数据来自通达信 MCP 连接器；**未连接 = 取不到数据 = 完全无法工作**，不要尝试硬跑。
- 开启路径：WorkBuddy →「连接器管理」→ 找到「**通达信 tdx-connector**」→ 启用并点「信任」→ 确认状态显示「已连接 / 绿色」。
- 判定未连接的信号：调用报 `tool not found` / `not found in deferred tools index` / `disconnected` / `ECONNREFUSED`。
- **未连接时的标准话术**（直接对用户说这句，不要把原始报错丢给用户）：
  > 这个技能要靠通达信数据源才能取 K 线。请打开 WorkBuddy 的连接器管理，把「通达信 tdx-connector」启用并信任，显示已连接后跟我说一声，我立刻重跑。

**2. Python 依赖**：`pandas` / `matplotlib` / `mplfinance`（见包内 `requirements.txt`）
- 安装：`pip install -r requirements.txt`

**3. 中文出图字体（无需手动配置）**：`caisen_chart._resolve_cn_fonts()` 在运行时**探测系统可用 CJK 字体**，候选链覆盖 macOS（Hiragino Sans GB / STHeiti / PingFang SC / Arial Unicode MS / Songti SC）、Windows（Microsoft YaHei / SimHei）、Linux（WenQuanYi Zen Hei·Micro Hei / Noto Sans CJK SC / Source Han Sans SC）；若全无则扫描字体表兜底。
   - 仅在**完全没有 CJK 字体的英文系统**上才退回 `DejaVu Sans`（中文显示为方块）→ 装任一 CJK 字体即可。
   - **勿改成 `monospace`**，也**勿硬编码单一字体名**（会破坏换机兼容，这是历史坑）。

> 美股 / 外汇：tdx-connector 不支持（S6 硬编码拒绝，绝不静默出图），见「适用范围」。

## 安装位置与调用方式（用户怎么用）

本技能为**自包含分发包**：所有 `.py` 脚本与本 `SKILL.md` 同级，装到任意机器都能跑。可被扫描的安装位置：

- 用户级：`~/.workbuddy/skills/caisen-kline/`（客户端市场安装后可能是 `caisen-kline__skillhub/`）
- 项目级：`{项目根}/.workbuddy/skills/caisen-kline/`

> ⚠ **安装避坑（实测，重要）**：用 **SkillHub CLI** 安装会落到**两层**目录
> `skills/@命名空间/caisen-kline/`，而 WorkBuddy 只认**单层** `skills/<技能名>/SKILL.md` —— 两层会**扫不到**，表现为「装了但技能列表里没有」。
> 修复：`mv ~/.workbuddy/skills/@user_df4693f0/caisen-kline ~/.workbuddy/skills/caisen-kline && rmdir ~/.workbuddy/skills/@user_df4693f0`
> 用 WorkBuddy 客户端「技能市场」按钮安装则无此问题（会自动落成单层 `___skillhub` 命名）。

装好后有两种触发方式：

1. **自然语言直接说**（最常用）：直接告诉我一个标的，我会自动触发本技能跑完整流水线。例如：
   - 「分析 600519 茅台」
   - 「看看 00700 腾讯现在怎么走」
   - 「螺纹 RB2610 后市怎么看」
   - 「上证指数 000001 现在什么结构」
2. **显式点名**：对话里说「用 caisen-kline 技能分析 xxx」或「/caisen-kline xxx」。

> ⚠ **撞码必须带市场**（设计上的消歧，非 bug）：像 `000001` 这种代码，深市是平安银行、又是上证指数代码。
> - 指数 → 说「上证指数」「000001 指数」或显式 `market_hint="INDEX_CN"`
> - 平安银行 → 说「000001 平安银行」「000001 深市」
> 不区分时技能默认按深市A股解析，会判为「未识别到形态」而非报错。

## 工作流（6 步）
1. **识别标的**：用户给代码或名称。若模糊，先调 `mcp__tdx-connector__tdx_lookup_stock(query)` 拿到准确 code / name / setcode / 市场。
2. **取数（S1 + S6 守卫）**：调 `mcp__tdx-connector__tdx_kline(code, setcode, period="4", wantNum="300", tqFlag="1")`。
   - ⚠ **不要再传 `target` 参数**：2026-09-08 实测连接器 schema **已移除**该字段，传了直接报 `additionalProperties` 错。旧版「setcode∈{0,1,2}→target=0」铁律**已作废**，照旧文档写必挂。
   - 落盘文件含文本前缀（如「【士兰微】600460 | 现价...」）与尾部函数清单，**须用 `json.JSONDecoder().raw_decode` 从首个 `{` 截取 JSON**，直接 `json.loads` 会报 Extra data。
   - 日线 wantNum 建议 ≥250（窗口边界效应，P1-9）；**四色层开启后建议 300~400**（EMA50 暖机需 116 根，
     前 116 根颜色低置信并会淡化标注；合约上市不足 116 根时图例会出红字【警讯】要求加大取数）。
     新上市合约（如 SR2701 天然只有 165 根）取不到更多时**如实保留淡化 + 警讯，不要为了好看把暖机标注去掉**。
   - 取到的 JSON 交 `caisen_data.parse_kline_json` 校验：标的名 / Unit / 复权 / 未收盘；不支持市场或空数据直接抛错，禁止静默返空。
   - 💡 tdx 大结果超出 token 上限时**会自动落盘**（`~/.workbuddy/projects/<项目>/<会话>/tool-results/*.txt`），
     直接把该文件喂给 `run()` 即可，**无需手工转写 JSON**（2026-09-20 实测白糖 165 根走此路）。
3. **分析（S2 + S5）**：`caisen_ab.analyze(df)` 已内嵌失败识别（假突破翻空 / 假跌破破底翻翻多 / 量价背离 / 异常量 / 逃命线）。
4. **出图 + 文字（S3）**：`caisen_narrative.render_signal(sig, df, meta, out)` 出 K 线标注图；`build_report(sig, meta)` 出五块文字分析。
5. **呈现**：用 present_files 把 png 与文字报告交给用户。
6. **免责**：C1-C4（幸存者偏差 / 做空约束 / 方法矛盾 / 仓位管理）由 S3 强制注入，输出末尾必带「不构成任何投资建议」。

## 执行核心

**模块目录 = 本 SKILL.md 所在目录**（自包含，路径随安装位置变化，**不要写死开发机路径**）。第一步先自定位：

```python
import sys, os
SKILL_DIR = os.environ.get("CAISEN_SKILL_DIR", os.path.expanduser("~/.workbuddy/skills/caisen-kline"))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)
```
> 若技能装在项目级，把 `CAISEN_SKILL_DIR` 换成 `{项目}/.workbuddy/skills/caisen-kline` 即可。
> 探测办法：脚本找不到时，先 `ls ~/.workbuddy/skills/` 确认实际目录名（客户端安装可能带 `__skillhub` 后缀）。

### 第 1 步：把 MCP 返回值变成 `raw_json`
`tdx_kline` 的返回值**带文本前缀与尾部函数清单**，不是纯 JSON。标准做法：

```python
import json
from pathlib import Path
raw_text = """<把 tdx_kline 的返回原文粘贴/写盘到这里>"""
Path("/tmp/tdx_raw.json").write_text(raw_text, encoding="utf-8")
d, _ = json.JSONDecoder().raw_decode(raw_text[raw_text.find("{"):])   # 从首个 { 截取
```
直接用 `json.loads` 会报 `Extra data`（尾部有额外内容）——这是历史坑，别踩。

### 第 2 步：跑全链路（`caisen_pipeline.py`）
```python
from caisen_pipeline import run
res = run(d, query="600519", expect_name="贵州茅台",   # expect_name 必传（语义防线，拦错标的）
          market_hint="CN_SH",        # 指数须用 "INDEX_CN"；ETF 用 "ETF_SH"/"ETF_SZ"
          setcode=1,                  # 撞码或特殊标的显式传，消歧更准确
          out_dir="/绝对路径/out")     # ⚠ 建议传绝对路径，避免落到不确定的 cwd
print(res["png"])     # 出图路径（已含 _market 后缀，避免重名覆盖）
print(res["report"])  # 五块文字分析（含 C1-C4）
```
- 签名：`run(raw_json, query, expect_name, market_hint=None, period=4, out_dir=".", setcode=None, tq_flag=1, out_name=None, dpi=250)` → `{png, report, sig, meta}`。
- 已解析 df 的复用内核：`analyze_and_render(df, meta, out_dir=".", title=None, out_name=None, dpi=250)`。
- 数据不足时**不抛异常**，而是返回 `sig.ok=False` + `reason`（如「仅 20 根 K 线，不足以判定形态（需 ≥40）」）→ 照 `reason` 如实转告用户，不要硬编结论。

### 离线入口（`run_from_tdx.py`）
已有落盘 JSON 时可直接读文件出图，无需实时取数：
```python
from run_from_tdx import run, load_raw
raw = load_raw("/path/to/tdx_result.json")
res = run(raw, query="600718", expect_name="东软集团", market_hint="CN_SH", out_dir="/绝对路径/out")
```
命令行：`python run_from_tdx.py`（默认读脚本同级 `outputs/`，见脚本内 `HERE`/`main`）。

## 🎨 四色K线趋势层 + 量价层（2026-09-20 作者定稿 · **默认开启**）

> 作者原话：「蔡森每次画图，用这个 <Pine v5 四色K线指标>，要看量价」。
> 落地模块：**`caisen_trend.py`**（计算 + 文字块）＋ **`caisen_chart.py` 的四色渲染层**（mplfinance
> 不支持逐根任意配色，故 K 线/量柱改为自绘）。

### 四色语义（**严格照抄 Pine 脚本，不改语义**）

```
fast = ema(close,12)   slow = ema(close,50)
红 R = close>=fast and close>=slow   → 多头强势区（连续红）
黄 Y = close< fast and close>=slow   → 多头回调
蓝 B = close>=fast and close< slow   → 空头反弹
绿 G = close< fast and close< slow   → 空头弱势区（连续绿）
```

- **色号微调（语义不变、只为白底可读）**：Pine 的 `yellow #FFFF00` / `green #00FF00` 在白底几乎看不见 →
  改 `黄 #e8a33d` / `绿 #12a13f`；红 `#d81e06`、蓝 `#1565c0`。
- **EMA50 线用紫色 `#7b1fa2`**（Pine 原为 blue）—— 避免与「空头反弹蓝」同色混淆；EMA12 橙 `#ff9800`。
- **实体填充 = 涨跌维度**：**实心 = 收阴，空心（白底+同色描边）= 收阳**。四色管「阵营」，涨跌管「方向」，
  两个维度不互相吞掉。想退回全实心：`render(..., hollow_up=False)`。

### 量价层（「要看量价」的落地）

- **量柱与 K 线同色**（同一套四色语言，一眼看出「黄/蓝过渡区的量能怎么变」）。
- **量 MA5（灰虚线）** = 放量/缩量的当期基准；**区间均量（灰点线）** = 全窗口基准。两条都在图上。
- 文字副图新增 **【六、四色K线节奏】** 块（挂右栏）：现状（含该色/该阵营已延续几根）＋最近侧切换（含上一次）
  ＋量价读数（`最新量 x.xx×量MA5`、近 5 根量能 ±%、价格 ±% → 量价配合四象限结论）。

### 暖机区（EMA 无真值，如实标注，不装可信）

- EMA 靠递推衰减，种子影响衰减到 **1%** 需要：**EMA50 → 116 根**、EMA12 → 28 根（`warmup_bars()`）。
- 前 116 根 **轻淡化 alpha=0.72** + 虚线分隔 + 图例说明「颜色仅供参考」；
  **数据根数 <116 根时全图重淡化 0.45 + 图例红字【警讯】要求加大取数**。
  → **取数建议 `wantNum ≥ 240`**（116 暖机 + 120 可读），实务用 300~400。日线仍建议 ≥250。
- 想彻底避开暖机：先用更长历史算 EMA，再 `render(trend=...)` 传入（接口已留）。

### 侧切换三角（多空阵营翻转）

- 阵营：**R/Y = 多头侧**（收盘在 EMA50 上）、**B/G = 空头侧**。
- 翻转需 **连续 ≥3 根确认**才标记（滤掉 1~2 根的假穿）；▲ 画在下方留白带、▼ 画在上方留白带，
  **绝不压 K 线**。

### ⚠️ 展示层纪律（硬约束，不得违背）

1. **四色与量价读数不参与 A/B/K 招判定** —— 颈线识别 / 等幅满足 / 失败识别仍是纯形态几何，
   掺进均线交叉会污染方法论（属 C3「方法论内部矛盾」范畴）。
2. 它只做**一致性交叉校验**：四色在空头侧而形态偏多 → 提示「量价未转强前视为反弹，突破需量能确认」；
   四色在多头侧而形态偏空 → 提示「下方仍有承接，缩量破位易假摔」。**只提示，不自动改判方向**。

### 接口与兼容

```python
render(df, meta, levels, events, text_left, text_right, out,
       four_color=True,     # False → 退回原 mplfinance 红绿路径（旧图/回归测试用）
       ema_fast=12, ema_slow=50,
       hollow_up=True,      # False → K 线实体全实心（Pine 原样）
       vol_ma=5,            # 量能均线周期；0/None 关闭
       trend_flips=True,    # 侧切换三角
       trend=None)          # 可传 caisen_trend.compute() 结果（更长历史算的 EMA）
```

- `caisen_trend.py` 导出：`compute()` / `summary_text()` / `consistency_note()` / `warmup_bars()` /
  `classify()` / `side_flips()` / `vol_price_read()` / `state_span()`。
- 依赖缺失或传入异源 trend（长度不匹配）→ **自动退回老路径，不崩**。

### 版式微调（同一改动引入，已换算校验）

`figsize 15.5 → 16.2`、`panel_ratios (6.4,1.5,6.0) → (6.3,1.5,6.5)`：
换算后 **主图绝对高度不变**（6.4/13.9×15.5 ≈ 6.3/14.3×16.2 = 6.67in），只是文字副图加高 10%、
画布加高 4.5% —— 为了装下【六】量价块而不压缩主图。**「标注绝不覆盖 K 线」的约定不受影响**
（`verify_events_layout.py` 复核：要点框重叠 0 / 压 K 线 0 / 价位标签重叠 0）。

### 回归测试

`test_caisen_trend.py`（**45 项，全绿**）：Pine 语义逐根比对、EMA 逐根手算比对、暖机根数、
噪声过滤、量价四象限、阳线空心/阴线实心、暖机淡化档位、图例不重叠、三角数=侧切换数、
`four_color=False` 兼容、异源 trend 退回、数据不足报警。

> ⚠️ **别给 `savefig` 加 `pil_kwargs={'compress_level':9}`**：实测 PNG 从 1.59MB 抬到 1.81MB
> （matplotlib 自带 `_png` 压缩滤镜更适配这种大量色块的图）。

## 标注铁律（出图合规，不得擅自改）
- 标注绝不覆盖 K 线：水平线标签放右侧空白区，K线关键点文字放图内空白区，箭头可斜穿 K 线（作者 2026-08-04 定稿）。
- 每个标注说清：哪个点 / 哪个价位 / 什么线 / 什么作用。
- 改任何出图逻辑后，须跑 `verify_events_layout.py` 确认「要点框重叠=0 / 压K线=0 / 价位标签重叠=0」。

## 出图格式与清晰度
- **格式 = PNG**（无损、跨平台）：macOS / Android / Windows / 网页原生都能直接打开，不依赖任何苹果专属格式（HEIC/TIFF 等）。
- **高分辨率**：`render` 默认 `dpi=250`，出图约 **4274×4082 px（4K 级）**。字体由 matplotlib 矢量渲染，无论放大多少倍都不糊。
- **缩放清晰度看「像素」不是「文件大小」**：dpi=250 已能 10 倍放大清楚观看（在手机/电脑视口里放大 10 倍仍锐利）。
- **实测文件大小（2026-09-20 加入四色层后重测，白糖2701·165根）**：
  dpi=250 → **4274×4082 px / 1.59 MB**；dpi=220 → 3727×3592 / 1.31 MB；dpi=180 → 3086×2938 / 1.05 MB。
  四色层把 artist 数翻倍（逐根 K 线实体 + 逐根量柱），比旧红绿版（0.4MB）大 —— **dpi=250 仍 <2MB 上限**；
  若要微信/手机友好（<1MB）用 `dpi=180`。
- 想更大头：调 `run(..., dpi=300)` 即可（5125×4898，约 2.1MB，**已超 2MB 上限，慎用**）。

## 强制约束 C1-C4（每次输出必带）
- **C1 幸存者偏差 / 无回测**：等幅满足是几何外推，非保证。
- **C2 做空招式 A股不可开仓**（按市场分支，见适用范围）。
- **C3 方法论内部矛盾**：分歧时拉基本面 / 估值交叉校验。
- **C4 仓位管理 + 试错频率**：反推仓位 + 试错标注 + 频率纪律 + 来源声明。

## 数据源说明
主源 tdx-connector（已连接）。覆盖：A股 / 港股 / 上期所 / 大商所 / 郑商所 / **广期所（setcode=66）** / 基金 / 中证指数。未覆盖：中金所、上期能源、美股、外汇。缺口部分按 S6 拒绝并告知，不静默返空。

## 已知局限（后续迭代，非本次必修）
- **S9 已修复（2026-08-06）**：量能封顶（无量突破不得给「高」、缩量封「低」）、破位降级（现价跌破颈线≥5%或破停损→判破位、置信度降「低」、目标线置灰失效）、现价 R:R 并列（风险报酬段展示「按现价进场」真实风报比）。这三处原会误导输出，现已锁进 `test_caisen_s9.py`（15 项）。
- **S10 已修复（2026-08-06）**：颈线对齐。颈线不是一条 hairline，而是触点形成的「带」(lo~hi)。突破须脱离带远边（上沿/下沿）才算干净突破；仅过中位未脱离上沿→`clear_band=False`、置信度软封顶（高→中）、提示「未脱离颈线带上沿」，使「突破」与图上可见颈线带对齐。图上线中额外画浅色带区（破位同步置灰）。锁进 `test_caisen_s10.py`（12 项）。
- **S11 已修复（2026-08-06）**：套牢区检测。目标②若落入或现价逼近前高套牢区（up）/下方密集成交区（down），置信度软降级并提示解套卖压/承接卖压。识别采用成交量密度而非停留时间：峰值桶 ≥ 非空桶中位数×2.5、区间量 ≥ 历史成交 15%、区间单根均量 ≥ 全历史均量 1.5。锁进 `test_caisen_s11.py`（33 项）。
- **S12 已修复（2026-08-06）**：大周期定位。用日线 `resample` 出周线/月线，不额外拉数据。日线方向与周线趋势同向则顺势，逆向则降一级并按「下跌中继的反弹 / 上涨中继的回调」提示；周线震荡则按区间操作；周线不足 20 根判「数据不足」。锁进 `test_caisen_s12.py`（43 项）。
- **S13 已修复（2026-09-08）**：形态完成度判别 + 形态极点窗口。
  - **S13-A** 形态底须在「完整基底」内找，不能只从颈线首触点起——W底/头肩底的第二谷常早于颈线首触点，旧窗口把它切在外面，使 H 与等幅目标系统性偏小（600460：取 31.74 而非真实双谷 24.62，目标①给 46.15 而实际到过 57.02）。
  - **S13-B** 破位时先问「形态走完没有」：曾达目标① 再回落 = **完成后回撤**（获利回吐/反转，不叫失败）；从未达目标① 就回落 = **假突破失败**。旧版一律写「形态可能失败」，误导。新增字段 `completed / completed_at / t2_reached / extreme_after / retrace_kind`；S5 翻转路径同步传递原形态完成度（此前 `build_reversal_signal` 漏传，致 `extreme_after=0`）。
  - 锁进 `test_caisen_s13.py`（27 项，含真实数据实证 + 合成样本覆盖两个分支 + S5 翻转不丢字段）。
## 出问题时的排查顺序（照这个来，别自己猜）
1. **技能没出现在列表 / 找不到脚本** → 十有八九是安装成了两层目录，见「安装位置与调用方式」的避坑说明。
2. **报依赖错、出图中文方块、脚本导入失败** → 让用户跑一行：`python <技能目录>/selfcheck.py`，按它列出的待办逐条处理（它会用内置样本离线跑通全链路，不需要通达信）。
3. **取数报 `tool not found` / `disconnected` / `ECONNREFUSED`** → 通达信未连接，按「前置条件」第 1 条的**标准话术**引导，不要把原始报错丢给用户。
4. **返回「未识别到可交易形态」/ `sig.ok=False`** → **不是故障**：该窗口确实没有有效形态，或数据不足（会带 `reason`，如「仅 20 根 K 线，需 ≥40」）。如实转告，不要硬编结论。
5. **债券 / 北交所 / 美股 / 外汇** → 数据源不覆盖（返回空 `Rows`）。明确告知不支持，**不要出图**。

### 尚未实现（如实告知，勿对用户掩盖）
- **S14 · 形态进行中的分批提示（未实现）**：当前只在**破位时**才提示操作（S9/S13）。若形态仍在进行中、价格**已到目标①但未破位**，输出仍会显示「目标②」而**不会主动提示「可分批 / 移止损到成本」**。这是已知缺口，实盘参考时请人工补上这一判断。
- **形态识别本身被误判会连锁错**：颈线选错 → H 错 → 目标错。复杂整理结构请人工复核颈线触点是否落在同一水平带。
- **未覆盖品种**：美股 / 外汇 / 中金所 · 上期能源 / **债券（2026-09-11 实测不可用）**；需接兜底源或扩展市场注册表。（广期所已于 2026-09-20 解除限制。）
- **无回测、无胜率**：全部结论为几何外推（C1）。
