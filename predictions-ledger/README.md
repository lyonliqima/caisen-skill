# predictions-ledger · 预测台账

把「研判评分卡」变成**可证伪、可定期对答案**的闭环。每张评分卡强制追加一条记录，每周复盘判对错、算命中率 / 校准曲线 / Brier / 三色独立性。

## 为什么需要它

评分卡有了（方向 + 置信度 + 逻辑），但「震荡偏多不带期限」是永远不会错的话。本台账补上**期限 / 幅度区间 / 证伪位 / 三情景概率 / 建议仓位 / 已定价检查 / 证据类型计票**，让每条预测都能被客观判对错。

## 目录

- `soremap.json` — 记录字段定义（对齐研判评分卡全要素 + 进步建议）
- `ledger.jsonl` — 台账本体，逐行一条 JSON，追加友好
- `append.py` — 评分卡 → 台账 追加器（自动补 id/date/data_cutoff/expiry）
- `score.py` — 周度复盘引擎（待复盘清单 + 统计 + 校准 + Brier + 三色）
- `reports/` — `score-<date>.md` 复盘报告、`review-<date>.md` 待复盘清单

## 工作流

### 1. 分析时：评分卡 → 追加

每次「股票 / 期货」方向性分析，在产出评分卡后调用：

```bash
python3 predictions-ledger/append.py --json '{
  "source_skill":"caisen-10-experts-analyst",
  "methodology":"九专家综合",
  "asset_class":"A股个股","symbol":"600519 贵州茅台",
  "direction":"多","target_range":"+5%~+15%","time_window":"60D","confidence":70,
  "falsification":"跌破1400","position":"轻仓",
  "scenarios":{"bull_prob":50,"base_prob":30,"bear_prob":20,
    "bull_trigger":"Q3财报超预期","bear_trigger":"消费数据继续走弱"},
  "consensus_part":"复苏预期已部分定价","variant_part":"高端批价实际动销超预期",
  "evidence_votes":{"价量":"多","资金流":"中性","基本面":"多","政策":"中性","情绪":"多"},
  "independence_color":"🟢" }'
```

`id / date / data_cutoff / expiry` 自动补；`expiry` 由 `time_window`（如 `60D`）推算。必填缺失会报错（除非 `--lenient`）。

### 2. 每周：复盘

```bash
python3 predictions-ledger/score.py            # 写 reports/
python3 predictions-ledger/score.py --quiet   # 只打印
```

产出：到期待复盘清单 + 命中率（总 / 按专家 / 按资产 / 按置信度区间）+ 校准曲线 + Brier + 三色独立性占比。

### 3. 判对错、回填

对到期记录逐条判：

```bash
python3 predictions-ledger/score.py mark P-20260709-001 --status hit --return 8.2
python3 predictions-ledger/score.py mark P-20260709-001 --status partial --return -3.1 \
  --benchmark '{"hold_csi300":2.0,"random_dir":-1.1,"ma_rule":0.5}'
```

回填后重跑 `score.py` 即得更新后的统计。

## 进步建议落点（对应「金融预测大师」建议）

| 建议 | 落点 |
|---|---|
| 校准 > 命中率 | `score.py` 第三部分「校准曲线」：标 70 分的是否约七成兑现 |
| 跑赢基准才算有信息量 | `benchmark` 字段 + 第六部分对比槽位（持有沪深300 / 随机 / 均线） |
| 已定价检查 | `consensus_part` / `variant_part`：共识 vs variant perception |
| 方向 → 概率分布 | `scenarios`（牛/基准/熊 + 概率 + 触发路标），置信度=主情景概率，复盘用 Brier |
| 置信度 → 仓位 | `position`（<60不动 / 60-70轻仓 / >75标准仓 / 上限封顶） |
| 破底翻 walk-forward | 第七部分按期限分组经验胜率 + 前段定参后段验证纪律 |
| 审计独立性 | `independence_color` 三色占比；🔵 长期为 0 = 回声室警告 |

## 与 mx-moni 对账

`caisen-10-experts-analyst` 的「模拟组合验证」把评分卡建议转成模拟盘成交。模拟盘的实际收益 / 回撤即台账 `actual_return` 的天然来源——**把模拟盘成交当作预测的自动对账机制**，闭环即成。模拟盘须计入 A 股现实约束（T+1、涨跌停、滑点），否则验证结果虚高。

## 迁移说明

旧 `predictions/ledger.csv` + `ledger.schema.json` 为早期桩文件（CSV 为空、无 score.py）。本目录为正式台账，**以 `predictions-ledger/ledger.jsonl` 为准**；旧 `predictions/` 可删除或归档。

## 复盘节奏

- **每周一**：`python3 predictions-ledger/score.py --due` 检查到期待结算记录，逐条判对错并回填（mark 子命令）。
- **每月**：跑一次 `python3 predictions-ledger/score.py` 全量复盘；当前报告落在 `reports/`（`score-<date>.md` / `review-<date>.md`）。月度归档建议另存至 `predictions-ledger/reviews/<YYYY-MM>.md`（`reviews/` 目录已加入 git，且不会被 `.gitignore` 的 `*.csv` / `*.html` 规则误伤，仅含 `.md`）。
- 复盘时重点看：校准曲线（标 70 分是否约七成兑现）、Brier、三色独立性（🔵 长期为 0 ＝回声室）、与市场共识分歧预测的命中率（真正 alpha 读数）。
- 新记录必须通过 `append.py` 的 schema 白名单校验，且宏观 / 事件类必填 `market_prior`（约定4 第10项）；`confidence` 落点须有分布（避免全挤在 55–75 中间值，见约定4 置信度分布约束）。
