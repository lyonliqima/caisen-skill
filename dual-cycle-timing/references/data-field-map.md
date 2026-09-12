# 双周期数据源字段映射（westock data_macro / data_finance 实测）

> 2026-09 实测。字段名以实际返回为准，**不要凭名称猜语义**。

## 一、调用方式

`data_macro` 的 `names` **不接受中文指标名**（传 "PPI" 会报"未识别的宏观指标"）。
必须先 `mode=list` 拿目录，再用返回的 **shortName / listCode** 取值。

```
mode=list                        → 拿 56 个指标目录
names=cn_cpi_ppi,cn_pmi          → 传 shortName 逗号分隔
limit=N                          → 每个指标返回最近 N 条，默认 3，做趋势要给 8-10
```

高频使用的四个 shortName：

| shortName | 覆盖 |
|---|---|
| `cn_cpi_ppi` | CPI / PPI / PPIRM（购进价格）|
| `cn_pmi` | 制造业 & 非制造业 PMI 全分项 |
| `cn_core_p1` | 最新核心指标(1)：消费、CPI、货币 M0/M1/M2、社融、GDP、投资、PMI、工业利润、增加值 |
| `cn_core_p2` | 最新核心指标(2)：产能利用率、出口交货值、企业景气、财政、产量、用电、国债收益率 |

## 二、字段清单

### 价格（cn_cpi_ppi）
| 字段 | 含义 |
|---|---|
| `PPI_PPI_YOY` | PPI 当期同比（%）← 主用 |
| `PPI_PPI_YOY_PRODUCE` | 生产资料同比 |
| `PPI_PPI_YOY_LIVE` | 生活资料同比 |
| `PPIRM_PPIRM_MOM` | **工业生产者购进价格环比** ← 判动能，主用 |
| `PPIRM_PPIRM_YOY` | 购进价格同比 |
| `PPIRM_YOY_NONFERROUS_METAL` | 有色金属购进同比 |
| `PPIRM_YOY_CHEMICAL_METAL` | 化工原料购进同比 |
| `PPIRM_YOY_BUILDING` | 建筑材料购进同比 |
| `CPI_PRICE_SCISSORS_CPI_PPI` | **CPI-PPI 剪刀差**（负 = PPI 高于 CPI = 上游挤压中下游）|

⚠️ PPI 没有环比字段，**用 PPIRM 环比代理**。

### PMI（cn_pmi）
| 字段 | 含义 |
|---|---|
| `PMI_PMI_MANU` | 制造业 PMI（季调）|
| `PMI_PMI_MANU_ORDER_NEW` | **新订单** ← 四阶段判定主用 |
| `PMI_MANU_PRODUCT_INVENTORY` | **产成品库存** |
| `PMI_MANU_RAW_INVTRY` | **原材料库存** |
| `PMI_MANU_RAW_PURCH` | **主要原材料购进价格** ← 判成本压力 |
| `PMI_PMI_MANU_PRODUCE` | 生产 |
| `PMI_PMI_MANU_PURCHASE` | 采购量（≠新订单）|
| `PMI_PMI_MANU_ORDER_INHAND` | 在手订单 |
| `PMI_PMI_MANU_ORDER_EXPORT` | 新出口订单 |

⚠️ 三个命名陷阱：
1. 库存两项前缀是 `PMI_MANU_`（无 PMI_ 重复），价格项也是 `PMI_MANU_RAW_PURCH`；订单/生产项前缀是 `PMI_PMI_MANU_`。极易取错。
2. `PMI_PMI_MANU_MOM` 实际返回的是**当期同比**，`PMI_PMI_MANU_CUR_YOY` 实际是**环比**——字段名与语义错位，取数前核对 `listSchema` 描述。
3. 数值是**季调**口径，与新闻里常见的未季调数值可能有出入。

### 货币（cn_core_p1 → CURV）
| 字段 | 含义 |
|---|---|
| `CURV_M1_YOY` / `CURV_M2_YOY` | M1 / M2 同比 |
| `CURV_SCISSORS_M1_M2` | **口径是 M1−M2**（负值表示 M2 快于 M1）|
| `CURV_M0_YOY` | M0 同比，高企（>10%）通常不是活跃信号 |

M2−M1 需要自己算：`CURV_M2_YOY - CURV_M1_YOY`。

### 产能利用率（cn_core_p2 → CAPU，季度）
`CAPU_CAPU` 总体、`CAPU_CAPU_MFG` 制造业、`CAPU_CAPU_CHG` 环比变动。
分行业：`_CHEM` 化工 `_COAL` 煤炭 `_FERR` 黑色 `_NFERR` 有色 `_ICT` 电子 `_AUTO` 汽车 `_ELEC` 电气 `_NMET` 非金属 `_PHARM` 医药 `_PETRO` 石油加工 `_FIBER` 化纤 `_FOOD` 食品 `_TEXTL` 纺织。
各行业带 `_CHG` 后缀为环比变动。

### 投资（cn_core_p1 → INV，累计同比）
`INV_INV_MANU_CUM_YOY` **制造业投资整体** ← 做相对口径的分母。
分行业：`INV_INV_MANU_CAR_CUM_YOY` 汽车、`INV_MANU_ELEC_CUM_YOY` 电气、`INV_MANU_DEDIC_MACH_CUM_YOY` 专用设备、`INV_INFRA_COM_MACH_CUM_YOY` 通用机械、`INV_INV_MANU_TMT_CUM_YOY` TMT、`INV_INV_MANU_RAIL_CUM_YOY` 铁路船舶。
地产：`INV_RE_*`（新开工/竣工/销售/到位资金）。

### 工业利润（cn_core_p1 → PROFIT，累计同比）
`PROFIT_PROFIT_CUM_YOY` 总体。
分行业后缀：`_META` 有色 `_COAL` 煤炭 `_CHEM` 化工 `_OIL` 石油 `_ELC_` 电气机械 `_INST` 仪器仪表 `_PLAS` 塑料 `_FURN` 家具 `_FOOD` 食品 `_MEDI` 医药 `_DEDI` 专用 `_COM_` 通用。

### 产量（cn_core_p2 → PROD，当月/累计同比）
`PROD_OUT_<品类>_YOY` 当月、`_YTD_YOY` 累计。
常用：`PV` 光伏 `CEMENT` 水泥 `CSTEEL` 粗钢 `REBAR` 螺纹 `GLASS` 平板玻璃 `TGLASS` 光伏玻璃 `AUTO` 汽车 `NEV` 新能源车 `EXCAV` 挖掘机 `ROBOT` 机器人 `IC` 集成电路 `AC` 空调 `LIQUOR` 白酒 `NAOH` 烧碱 `FERT` 化肥 `COAL` 煤炭。

### 出口交货值（cn_core_p2 → EDV）
`EDV_EDV_<行业>_YTD_YOY`，如 `_AUTO` 汽车 `_NFERR` 有色 `_CHEM` 化工 `_PHARM` 医药。用来区分内需与外需驱动。

## 三、财报字段（data_finance，type=balance，fields=all）

| 字段 | 含义 |
|---|---|
| `TConstruInProcess` | **在建工程** ← 产业周期供给侧主指标 |
| `ContractLiability` | **合同负债** ← 需求侧先行指标 |
| `Inventories` | 存货 |
| `TotalFixedAsset` | 固定资产（算在建/固资比的分母）|
| `BillAccReceivable` | 应收票据及应收账款 |
| `InventoryTRate` | 存货周转率 |
| `EBIT` / `NPDeductNonRecurringPL` | EBIT / 扣非净利（判是否净利为负）|

调用：`data_finance code=sh601012 type=balance num=8 fields=all`
⚠️ 同比要**自己按报告期对齐计算**（拿 8 期覆盖两年），接口不给同比。
⚠️ 现金流量表是 `type=cashflow`，经营现金流在那里，不要从 balance 里找。
