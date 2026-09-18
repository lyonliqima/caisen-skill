# ocmacro-feed · MacroMargin 公开数据抓取器

抓取 [ocmacro.com](https://ocmacro.com)（宏观边际 / MacroMargin）的**公开数据源**，落地为本地 JSON/CSV，
供蔡森十二专家框架、预测台账、复盘流程直接调用。

只读、无需登录、遵守站点 robots.txt。

---

## 1. 站点是什么

**MacroMargin（宏观边际）** 是一个中文付费宏观研究平台，X 账号 `@MacroMargin`。
定位：聚焦中国宏观政策 + 美联储风向的**前瞻性简报 + 数据库**，自述「跟踪经济部委动态、会议与完整讲话，
日复一日积累近十年」，「外资研报库 AI 中文速读」，「图表库比彭博 CHART 库质量更高」，站内 120000+ 页。

14 个栏目：每周简报 / 每日简报 / 中国政策 / 政策智囊 / 美联储 / 资讯评论 / 外资观点 / 图表库 /
宏观日历 / 小道消息 / 政策工具箱 / AI 助手 / 中美专题跟踪 / **川普及其内阁**。

**其中只有 2 个栏目对外公开**（robots.txt 显式 `Allow`，其余全 `Disallow`）：

| 公开栏目 | URL | 价值 |
|---|---|---|
| 川普及其内阁 | `/dashboard/trump` | TACO 压力指数（自研）+ 支持率 + Truths 实时流 |
| 中国地产数据拆解 | `/dashboard/data-breakdown` | 70城房价 253 期 + BIS 全球房价周期 + 30城高频成交 |

> 注意：`/api/` 在 robots.txt 中被 `Disallow`。本工具仅访问 robots 允许的两个公开页面及其页面自身使用的公开数据接口。
> 若对方收紧权限，本工具会明确报错而非绕过。

---

## 2. 用法

```bash
cd "/Users/weihaoli/Desktop/蔡森 skill/ocmacro-feed"

python3 ocmacro_feed.py brief                 # 只打印 TACO 当前读数（最快，不落盘）
python3 ocmacro_feed.py trump                 # TACO 指数 + 六因子 + 全历史 + 支持率 + 30条事件复盘
python3 ocmacro_feed.py truths --pages 3      # Trump Truth Social 帖文（含中文翻译），每页20条
python3 ocmacro_feed.py housing               # 地产核心：70城四口径 + 涨跌广度
python3 ocmacro_feed.py housing --deep        # 地产全量：+BIS全球 +30城高频 +中原领先
python3 ocmacro_feed.py snapshot              # 全部抓一遍 → data/<YYYY-MM-DD>/
```

依赖：仅 Python 标准库（urllib），无需 requests/pandas。

### 输出文件

`data/<日期>/` 下：

| 文件 | 内容 |
|---|---|
| `trump_dashboard.json` | TACO 指数块（含完整方法论参数）+ 六因子明细 + 366 日历史 + 支持率序列 |
| `taco_index_history.csv` | 宽表：日期 × 指数值 × 5 类贡献 × 6 因子（共 37 列），可直接透视 |
| `trump_approval.csv` | 净支持率日序列（599 点，2025-01-21 起） |
| `taco_events.json` | TACO 事件复盘 30 条结构化（时间/强度/主题/威胁/回撤/分析/含义） |
| `truths.json` | Truth Social 帖文流（含中文翻译、互动数、媒体标记） |
| `housing.json` | 地产全部数据集 |

---

## 3. 数据源地图（逆向工程结果）

### 3.1 川普面板 `/dashboard/trump` —— 无需令牌

页面是 Next.js App Router，**完整数据直接内嵌在 RSC 飞行载荷里**（`self.__next_f.push([1,"..."])`），
纯 GET 页面 HTML 再解析即可，不需要任何接口调用。解析要点：

```
chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html)   # 每段是 JSON 字符串字面量
payload = "".join(json.loads('"' + c + '"') for c in chunks)          # 反转义拼接
block   = 载荷里含 "methodologyVersion" 的最外层大括号对象              # 即 TACO 数据块
```

TACO 事件复盘是**服务端渲染的 HTML 列表**（`id="taco-event-log-list"`），不在 RSC 块里，需从 HTML 正则解析。

### 3.2 Truths `/api/trump/truths` —— 无需令牌

`GET /api/trump/truths?offset=0&limit=20`，只需带 `Referer: /dashboard/trump`。
上游数据源是 **CNN 的 Truth Social 公开归档** `https://ix.cnn.io/data/truth-social/truth_archive.json`
（站点自己声明 `source.url` 即此），因此即使 ocmacro 挂了也可以直接从 CNN 取。

返回结构：`{account, generatedAt, source:{...}, truths:[{content, translation, headline,
createdAtLabel, favouritesCount, repliesCount, reblogsCount, media, ...}]}`

### 3.3 地产数据 `/dashboard/data-breakdown` —— 需签名令牌

页面 RSC 里给出 `initialManifest` + `dataBasePath` + `dataAccessToken`（**JWT，TTL 2 小时**，`scope=house-prices`）。
数据请求需**两个自定义头**（这是关键，用普通 query token 会 403）：

```
GET {dataBasePath}/{path}?v={cacheKey}
X-MM-Data-Access: <dataAccessToken>
X-MM-Request-Intent: chart-data
```

可用路径（均为**远端接口路径**，需拼接令牌返回的 `dataBasePath`，不是本地文件）：

| 路径 | 内容 |
|---|---|
| `{dataBasePath}/manifest.json` | 清单：最新期、城市能级划分、1708 条序列的可用性矩阵 |
| `{dataBasePath}/compact/series/{market}-{metric}-{area}.json` | 主序列。market∈{second_hand,new_house}，metric∈{yoy,mom,ytd_yoy}，area∈{all,le_90,m90_144,gt_144} |
| `{dataBasePath}/compact/breadth.json` | 涨跌广度（up/flat/down count 与均值、扩张/收缩计数） |
| `{dataBasePath}/charts/phase/{...}.json` / `charts/divergence/{...}.json` | 象限图、背离图预计算 |
| `{dataBasePath}/external/zhongyuan-leading-index.json` | 中原领先指数（Wind） |
| `{dataBasePath}/external/bis-real-house-price-index.json` | BIS 58 国实际房价指数 + 143 个历史周期 |
| `{dataBasePath}/external/china-30-city-property-sales.json` | 30 大中城市高频成交（Wind，周频，2021 起） |

主序列是**紧凑数组格式** `[key, entity, entityType, cityTier, values]`，需按 `scale`（通常 100）还原。
`periods[0]` 是最新期，数组**倒序**（由新到旧）——这一点极易搞错。

令牌每次运行现取，无需手工维护。

---

## 4. 已识别的坑

1. **地产令牌 TTL 仅 2 小时**，过期返回 403 且页面提示「数据访问已过期，请刷新页面后重试」。本工具每次运行重新取。
2. **限流**：站点会返回 429「请求过于频繁，请稍后再试」。工具内置 1.2s 请求间隔 + 指数退避重试。
3. **序列数组倒序**：`values[0]` 是最新值，`values[1]` 是上一期。算 diff 时务必注意。
4. **`scale` 字段**通常为 100；`broadth` 的 `down_count` 原始值是 7000 = 70 城 × 100。
5. **TACO 指数"较20个交易日前"** 是总指数点位之差，**不是**分项基数公式里的 15~25 日等权旧基数。两者不同，勿混用。
6. **预热期不伪造数据点**：图表从 2025-03-26 开始（而非任期起点 2025-01-20），因为需要满足"完整变化基数 + ≥20 个先验样本"。所以历史只有 366 点，不是 400+。
7. `/api/data-breakdown/house-prices` **裸调 404**——它只接受上述带头的子路径访问，不是 REST 根。
