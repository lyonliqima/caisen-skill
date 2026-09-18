# 取数规程 SOP（S1 交付）

> 适用：蔡森 K 线分析全链路的数据获取环节
> 强制级别：**违反任意一条 → 禁止出图**
> 实现：`caisen_data.py`　自检：`test_caisen_data.py`（44 项全过）

---

## 零、为什么要有这份规程

tdx-connector 有两个**静默失败**（不报错、格式完整、数字齐全，但结论完全错）：

| 现象 | 后果 |
|---|---|
| 不传 `target` 查港股 00700 → 返回 A 股【模塑科技】 | 你以为在分析腾讯，其实在分析一只 10 块钱的 A 股 |
| 不声明 `tqFlag` → 默认前复权 | 图上价位与客户端盘面差一个分红额，形态位置对不上 |

静默失败比报错危险得多 —— 报错你会去查，静默失败你会**照着错的下单**。

---

## 一、四步流程（Agent 必须按此执行）

```
1. Python : req = build_request(code, market, expect_name=..., want_num=300, tq_flag=1)
2. Agent  : 调 mcp__tdx-connector__tdx_kline(**req["tool_args"])
3. Agent  : 原始 JSON 原样落盘 → data/raw/<code>_<period>_tq<flag>.json
4. Python : df, meta = load_and_validate(path, req)   ← 校验不过直接抛错
```

**为什么要落盘原始 JSON**：可复现、可复查、可追溯。前复权价位会随日后分红漂移，
不存原文，三个月后没人能验证今天的结论是怎么来的。

---

## 二、三条铁律

### 铁律 1 · `target` 必须显式传

| setcode | 市场 | target |
|---|---|---|
| 0 / 1 / 2 | 深A / 沪A / 北交所 | `"0"` |
| **其余全部** | 港股、期货、基金、指数 | `"1"` |

实测证据：

```
tdx_kline(00700, setcode=31)            → 【模塑科技】10.69   ← 错！不报错！
tdx_kline(00700, setcode=31, target=1)  → 【腾讯控股】490.40  ← 对
tdx_kline(RB2610, setcode=30)           → Rows: []           ← 空
tdx_kline(RB2610, setcode=30, target=1) → 【螺纹2610】        ← 对
```

工具文档写"系统通常自动推导 target" —— **实测不成立，别信**。
`build_request()` 已自动处理，手工调用时务必自己带上。

### 铁律 2 · 标的名必须交叉校验（`expect_name` 已改为**必填**）

先看这个实测样本为什么可怕：

```
请求：code=00700  setcode=31（港股）
返回：Code=00700  Setcode=31   ← 与请求完全一致，代码校验、setcode 校验统统放行
     AttachInfo.Name = 模塑科技   ← 只有这里露馅（A股 000700）
     AttachInfo.Unit = 100        ← 以及这里（A股专有量纲，港股应为 0.01）
```

所以防线只有两道，且必须同时开：

| 防线 | 机制 | 是否依赖人工 |
|---|---|---|
| **语义防线** | `expect_name` ↔ `AttachInfo.Name` | 依赖调用方传名字 |
| **结构防线** | `AttachInfo.Unit` ↔ 市场量纲 | **不依赖人工，无人值守兜底** |

规则：
- `build_request()` **不传 `expect_name` 直接抛 `DataError`**，请求都发不出去。
  确实无法预知名称时，显式 `allow_unnamed=True`，届时只剩结构防线。
- 名称比对分三档：完全相等放行；简称/全称之别放行但留警告；
  **差异含数字一律拒**（「东方财富」≠「东方财富转3」），期货合约月份例外（「螺纹」≈「螺纹2610」）。
- Unit 校验双向：非 A 股却返回 `Unit=100` → 拒；市场已实测量纲不符 → 拒。

> 取数前先用 `tdx_lookup_stock` 查到准确名称，再填 `expect_name`。这是标准动作。

### 铁律 3 · `tqFlag` 必须显式传并在图上声明

| tqFlag | 含义 | 用途 |
|---|---|---|
| 1（默认，推荐） | 前复权 | 形态分析。历史价格连续，颈线/等幅才有意义 |
| 0 | 不复权 | 对照客户端盘面、算真实挂单价 |
| 2 | 后复权 | 长期收益率计算，本项目不用 |

**复权双取**：涉及具体挂单价时，同一标的取两次（tqFlag=1 和 0），
用 `build_adjust_bridge()` 算出 offset：

```
茅台实测：2026-06-26 除息 28.02 元/股
  06/25 收盘   前复权 1184.08  ↔  不复权 1212.10
  06/26 之后   两序列重合
```

三类风险要分开说，别混为一谈：

1. **挂单价风险** —— 只看当前段 offset。为 0 时照图挂单无误。
2. **形态错位风险** —— 只要区间内有除权日，客户端设为「不复权」时，
   除权前那段 K 线整体高 `max_offset` 元，看图对不上。
3. **可复现性风险** —— 日后再分红，今天的前复权坐标整体下移，历史结论不可复现。
   → 必须记录 `snapshot` 快照时间。

---

## 三、市场覆盖矩阵（2026-08-03 实测）

| 市场 | setcode | 状态 | 量单位 | T+N | 涨跌停 | 做空（C2） |
|---|---|---|---|---|---|---|
| 上交所A股 | 1 | ✅ | 手 | T+1 | 10%（ST 5%，科创 20%） | 禁止开空 → 只作减仓/离场 |
| 深交所A股 | 0 | ✅ | 手 | T+1 | 10%（创业板 20%） | 禁止开空 |
| 北交所 | 2 | ✅ | 手 | T+1 | 30% | 禁止开空 |
| 港股 | 31 | ✅ | **股** | T+0 | 无（有 VCM） | 可做空，须可沽空名单+券源 |
| 上期所 | 30 | ✅ | 手 | T+0 | 停板+熔断 | 可双向，注意杠杆 |
| 大商所 | 29 | ✅ | 手 | T+0 | 停板 | 可双向 |
| 郑商所 | 28 | ✅ | 手 | T+0 | 停板 | 可双向 |
| 基金/ETF | 33 | ✅ | 份 | T+0 | 视品种 | 部分可融券 |
| 中证指数 | 62 | ✅ | 点 | — | 无 | 需经 ETF/期货 |
| **美股** | 74 | ❌ | — | — | — | — |
| **外汇/汇率** | — | ❌ | — | — | — | — |
| 中金所 IF/IC/IH | — | ❌ 未覆盖 | | | | |
| 上期能源 原油SC | — | ❌ 未覆盖 | | | | |
| 广期所 | — | ❌ 未覆盖 | | | | |

❌ 项调 `build_request()` 会直接抛 `UnsupportedMarketError`，**不发请求、不静默返空**。
项目要求的"全市场"，美股和外汇是真缺口 → 留给 S6 接兜底源。

### 成交量单位陷阱（P1-8）

```
Volume = RawVolume / Unit
  A股  Unit=100    RawVolume=7187261 股  → Volume=71872.61 手
  港股 Unit=0.01   RawVolume=317920 手   → Volume=31792000 股
```

**同一个 `Volume` 字段，A 股是「手」，港股是「股」，方向相反。**
图上标注一律取 `meta.vol_unit`，禁止硬编码「手」。

---

## 四、自动校验清单（`parse_kline_json` 内置）

| # | 检查 | 不过时的行为 |
|---|---|---|
| C1 | 顶层字段 Rows / AttachInfo / Setcode / Code 齐全 | `IntegrityError` |
| C2 | Rows 非空 | `EmptyDataError`（提示查 target） |
| C3 | Code、setcode 与请求一致 | `SymbolMismatchError` |
| C4 | **AttachInfo.Name 与 expect_name 匹配** | `SymbolMismatchError` |
| C5 | 日期可解析、无重复、升序 | `IntegrityError` |
| C6 | high ≥ max(o,c,l)、low ≤ min(o,c,h)、价格为正、量非负 | `IntegrityError` |
| C7 | 最后一根是否收盘（HqTime vs 市场收盘时刻） | 警告 + `preflight` 阻断 |
| C8 | 日线窗口 ≥ 250 根 | 警告（窗口边界效应） |
| C9 | tqFlag 已记录 | 警告 |

**阻断 vs 警告**：抛错 = 数据不可信，绝不出图；警告 = 结论要打折扣，必须写进图上文字。

---

## 五、参数建议

| 参数 | 建议值 | 理由 |
|---|---|---|
| `want_num` | 日线 **300**（上限 1000） | 蔡森看大结构。100 根太短，区间极值可能是窗口边界值而非真实高低点 |
| `period` | 4（日线）为主 | 形态分析主战场；J 招多周期协同时再加 5（周）/6（月） |
| `tq_flag` | 1（前复权） | 形态连续性优先；需报挂单价时再补一份 0 |

---

## 六、已知遗留（不属 S1 范围）

- **期货主力合约会过期**：RB2609 已返空、RB2610 有数据。合约按月滚动，硬编码代码几个月后必失效 → 需主力合约自动解析
- **美股 / 外汇覆盖缺口** → S6 处理
- 盘中数据的分钟级延迟未实测（本项目以日线收盘后分析为主，影响有限）

---

## 七、快速上手

```python
import caisen_data as cd

req = cd.build_request("600519", "CN_SH", expect_name="贵州茅台", want_num=300)
# → Agent 用 req["tool_args"] 调 MCP，JSON 存到 data/raw/600519_d300_tq1.json

df, meta = cd.load_and_validate("data/raw/600519_d300_tq1.json", req)
df, meta = cd.drop_unclosed(df, meta)          # 盘中运行时剔除未收盘那根

if blocks := cd.preflight(meta):               # 非空即禁止出图
    raise SystemExit("；".join(blocks))
for w in meta.warnings:
    print("警告：", w)

print(meta.title())      # 贵州茅台 600519 · 上交所A股 日线
print(meta.footer())     # 数据：通达信…（前复权，快照…）| 方法论：蔡森… | 不构成任何投资建议
print(cd.regime(meta))   # {t_plus: T+1, price_limit: 10%…, short: 禁止开空…} → 供 C2 自动注入
```
