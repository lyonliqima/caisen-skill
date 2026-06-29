# 因果推断工具箱（Causal Inference Toolkit）

> 来源：Stanford AERS `aer-identification` + `Full-empirical-analysis-skill` + StatsPAI 因果推断引擎
> 用途：为第七专家提供严格的因果识别、估计与稳健性检验方法论

---

## 一、双重差分（DiD）

### 1.1 经典 2×2 DiD

**适用条件**（全部满足才可用 TWFE）：
- 处理时点对所有处理单位**同时**
- 对照组**从未被处理**
- 处理效应异质性**不成立**

**TWFE 模型**：
$$Y_{it} = \alpha_i + \gamma_t + \beta \cdot Treat_i \times Post_t + \epsilon_{it}$$

- $\alpha_i$：个体固定效应
- $\gamma_t$：时间固定效应
- $\beta$：双重差分估计量（ATT）
- 标准误：聚类到处理单位层面

### 1.2 交错采纳 DiD（现代默认）

**禁止**在交错采纳数据上直接使用 TWFE。TWFE 会产生"禁止比较"（forbidden comparisons），导致估计偏误甚至符号翻转。

**现代估计量选择**：

| 估计量 | 核心思想 | 实现 | 优势 |
|--------|---------|------|------|
| Callaway-Sant'Anna (2021) | 组-时间 ATT：$ATT(g,t) = E[Y_t(g) - Y_t(0) \| G=g]$ | Stata `csdid` / R `did` | 双重稳健，支持事件研究聚合 |
| Borusyak-Jaravel-Spiess (2024) | 插补估计量：估计反事实 $Y_t(0)$ 填补 | Python `differences` | 高效，处理任意处理模式 |
| de Chaisemartin-D'Haultfœuille (2020) | $\delta^S$：可异质性的平均处理效应 | Stata `did_multiplegt` | 对异质性稳健 |
| Sun-Abraham (2021) | 交互加权事件研究估计量 | Stata `eventstudyinteract` | 事件研究系数无偏 |

### 1.3 Goodman-Bacon 分解

**目的**：揭示 TWFE 中各种"2×2 比较"的权重构成，暴露"禁止比较"。

$$\hat{\beta}^{TWFE} = \sum_k s_k \cdot \hat{\beta}_k^{2\times2}$$

- 后处理组 vs 先处理组（"禁止比较"）→ 权重为**负**，符号翻转风险
- 报告：禁止比较的权重占比，若 >30% 则 TWFE 结果不可信

### 1.4 平行趋势检验

**必要但不充分**：
1. **视觉**：事件研究图，前期系数应接近 0
2. **正式检验**：前期系数联合检验 $H_0: \beta_{-1} = \beta_{-2} = ... = 0$，报告 p 值
3. **Honest DiD**（Rambachan-Roth 2023）：允许平行趋势在 $\bar{M}$ 范围内偏离时的敏感性界

### 1.5 市场分析应用实例

**"关税对出口企业利润的影响"**：
- 处理组：被加征关税的行业
- 对照组：未被加征关税的类似行业
- 处理时点：关税生效日
- 方法：交错 DiD（不同行业关税时点不同）
- 诊断：Goodman-Bacon 分解 + 事件研究图 + Honest DiD
- 输出：关税导致出口企业利润变化 X%（95% CI: [Y%, Z%]）

---

## 二、工具变量（IV）

### 2.1 经典 2SLS

**两阶段**：
- 第一阶段：$X_i = \pi_0 + \pi_1 Z_i + \pi_2 W_i + u_i$
- 第二阶段：$Y_i = \beta_0 + \beta_1 \hat{X}_i + \beta_2 W_i + \epsilon_i$

**关键假设**：
1. **相关性**：$Cov(Z, X) \neq 0$（第一阶段 F 统计量）
2. **排他性**：$Z$ 只通过 $X$ 影响 $Y$
3. **独立性**：$Z \perp\!\!\!\perp$ 潜在结果

### 2.2 弱工具现代标准

| F 统计量 | 推断方法 | 可靠性 |
|---------|---------|--------|
| F > 50 | 2SLS 标准推断 | 可靠 |
| 10 < F < 50 | 报告 AR 置信集 | 中等 |
| F < 10 | **必须**用 AR / Anderson-Rubin | 最低要求 |

**Anderson-Rubin (AR) 检验**：
$$AR(\beta) = \frac{(Y - X\beta)' P_Z (Y - X\beta)}{\hat{\sigma}^2}$$

- AR 统计量对任意工具强度都有正确 size
- F < 50 时，AR 是**主推断**而非稳健性检验

### 2.3 Shift-Share / Bartik IV

$$b_i = \sum_s \frac{L_{is,t_0}}{L_{i,t_0}} \cdot g_s$$

- $L_{is,t_0}$：地区 $i$ 在基础期对部门 $s$ 的暴露
- $g_s$：部门 $s$ 的全国增长率（"冲击"）

**两条识别路径（必须选一条）**：
1. **外生份额**（Goldsmith-Pinkham 2020）：份额条件外生 → 报告 Rotemberg 权重，检查 top-5 识别行业
2. **外生冲击**（Borusyak-Hull-Jaravel 2022）：冲击近似随机 → 报告冲击层面推断

### 2.4 市场分析应用实例

**"利率对房价的因果效应"**：
- 内生性：房价上涨→需求强→央行加息→利率上升（反向因果）
- 工具变量：货币政策冲击（意外加息幅度 = 实际 − 预期）
- 第一阶段 F：检验工具强度
- 2SLS 估计：因果效应 vs OLS 偏误对比
- 排他性辩护：意外加息只通过实际利率影响房价

---

## 三、断点回归设计（RDD）

### 3.1 精确断点（Sharp RDD）

**模型**：
$$Y_i = \alpha + \tau \cdot \mathbf{1}[X_i \geq c] + f(X_i - c) + \epsilon_i$$

- $c$：断点
- $\tau$：断点处的处理效应
- $f(\cdot)$：运行变量的多项式（**阶数 ≤ 1**，Gelman-Imbens 2019 反对高阶）

### 3.2 模糊断点（Fuzzy RDD）

**相当于断点处的 IV**：
- 第一阶段：$D_i = \alpha + \pi \cdot \mathbf{1}[X_i \geq c] + f(X_i) + u_i$
- 第二阶段：用 $\hat{D}_i$ 作为 $D_i$ 的工具

### 3.3 现代默认设置

| 要素 | 推荐选择 | 理由 |
|------|---------|------|
| 核函数 | 三角核 | 边界权重最大 |
| 带宽 | MSE 最优（Calonico-Cattaneo-Titiunik 2014） | 偏差-方差权衡 |
| 多项式阶数 | ≤ 1（局部线性） | Gelman-Imbens 反对高阶 |
| 推断 | 稳健偏差校正 CI | `rdrobust` 默认 |
| Donut RDD | 如存在断点附近操纵 | 排除 [c-δ, c+δ] 区间 |

### 3.4 必须报告的诊断

1. **密度检验**（McCrary 2008 / Cattaneo-Jansson-Ma 2020）：运行变量在断点附近是否被操纵
2. **协变量平衡**：断点两侧预定协变量是否平衡
3. **安慰剂断点**：在非真实阈值处检验效应
4. **带宽敏感性**：至少 3 种带宽下的估计
5. **视觉 RD 图**：`rdplot`，明确标注 binning 方法

### 3.5 市场分析应用实例

**"纳入沪深300指数对个股收益的影响"**：
- 运行变量：排名（按市值/流动性）
- 断点：第 300 名
- 方法：精确/模糊 RDD
- 诊断：McCrary 检验（大基金是否操纵排名）、协变量平衡
- 效应：指数纳入带来的指数基金被动买入效应

---

## 四、合成控制法（SCM）

### 4.1 经典 Abadie-Diamond-Hainmueller (2010)

**构建**：
$$Y^{synth}_t = \sum_{j \in J} w_j \cdot Y_{jt}$$

权重 $w_j$ 通过最小化前期 MSPE 选择：
$$\min_{w} \sum_{t=1}^{T_0} (Y_{1t} - \sum_j w_j Y_{jt})^2$$

约束：$w_j \geq 0$，$\sum w_j = 1$

### 4.2 现代扩展

| 方法 | 核心创新 | 适用 |
|------|---------|------|
| 广义 SCM（Xu 2017） | 因子模型 + 交互固定效应 | 多处理单位 |
| 增强 SCM（Ben-Michael 2021） | 偏差校正 | 前期拟合不完美 |
| 合成 DiD（Arkhangelsky 2021） | SCM 权重 × DiD 时间权重 | 结合双重差分优势 |
| SDID（synthetic DiD） | 同时选择单位权重和时间权重 | 更稳健的 ATT |

### 4.3 必须报告的诊断

1. **时间安慰剂**：将干预日提前到前期，检验是否有效应
2. **空间安慰剂**：对每个对照单位做合成控制，报告安慰剂效应分布
3. **排列推断**：Fisher 精确 p 值 $= \frac{1}{J+1} \sum \mathbf{1}[MSPE_j \geq MSPE_{treated}]$
4. **权重报告**：附录中报告完整权重向量，>10% 的对照单位需讨论

### 4.4 市场分析应用实例

**"如果没有俄乌冲突，欧洲天然气价格会怎样"**：
- 处理单位：欧洲天然气市场
- 对照池：其他天然气市场（美国Henry Hub、亚洲LNG等）
- 前期：冲突前的价格走势
- 合成：用其他市场加权拟合"虚拟欧洲天然气"
- 后期：真实 vs 合成的差额 = 冲突的因果效应

---

## 五、双重机器学习（DML）

### 5.1 部分线性模型

$$Y = \theta D + g(X) + \epsilon, \quad E[\epsilon | D, X] = 0$$
$$D = m(X) + \nu, \quad E[\nu | X] = 0$$

**DML 三步**：
1. 用 ML 交叉拟合估计 $\hat{g}(X)$ 和 $\hat{m}(X)$（ nuisance 函数）
2. 计算残差：$\tilde{Y} = Y - \hat{g}(X)$，$\tilde{D} = D - \hat{m}(X)$
3. 对残差做回归：$\tilde{Y} = \theta \tilde{D} + \eta$

**交叉拟合（Cross-fitting）**：将样本分 K 折，用 K-1 折估计 nuisance，在第 K 折预测，避免过拟合偏差。

**保证性质**：$\sqrt{n}$ 一致性 + 渐近正态（即使 $g, m$ 以慢于 $\sqrt{n}$ 速率估计）。

### 5.2 异质处理效应（CATE）

| 元学习器 | 方法 | 优势 |
|---------|------|------|
| S-Learner | $Y \sim D + X$，CATE = $\hat{\mu}(1,X) - \hat{\mu}(0,X)$ | 简单 |
| T-Learner | 分别估计 $\hat{\mu}_1(X)$ 和 $\hat{\mu}_0(X)$ | 直观 |
| X-Learner | T-Learner + 伪结果 + 加权 | 不平衡数据好 |
| R-Learner | 最小化 R-loss | 理论最优 |
| DR-Learner | 双重稳健评分 | 双重稳健 |

**因果森林（GRF）**：
- 树结构分割样本，每片叶子估计局部 CATE
- 提供 CATE 分布和置信区间
- 实现：`econml.grf` / `grf` (R)

### 5.3 市场分析应用实例

**"某补贴政策对不同类型企业的异质效应"**：
- 处理变量：是否获得补贴
- 控制变量：数百个财务/行业/地区变量
- 方法：DML（随机森林 nuisance）+ 因果森林 CATE
- 发现：补贴对小企业效应大、对大企业效应不显著

---

## 六、稳健性大考完整检查清单

### 6.1 安慰剂检验

| 类型 | 方法 | 判断标准 |
|------|------|---------|
| 时间安慰剂 | 将干预时点提前 | 安慰剂处无显著效应 |
| 空间安慰剂 | 对对照单位做处理 | 效应分布接近 0 |
| 结果安慰剂 | 换一个不应受影响的结果 | 无效应 |

### 6.2 推断稳健性

| 检验 | 方法 |
|------|------|
| 替代聚类 | 单位聚类 vs 行业聚类 vs 双聚类 |
| 野自助法 | `boottest`（小样本） |
| Conley 空间 SE | 考虑地理相关性的标准误 |
| 替代 FDR | Romano-Wolf 多重检验校正 |

### 6.3 规格曲线分析（Specification Curve）

- 枚举所有合理的控制变量组合
- 画出系数分布
- 判断：主结果是否在大多数合理规格下稳定

### 6.4 Oster (2019) 不可观测选择界

$$\beta^* = \hat{\beta}_{full} - \delta \cdot (\hat{\beta}_{full} - \hat{\beta}_{partial})$$

- $\delta$：不可观测因素需要比可观测因素强多少倍才能将效应归零
- $\delta > 1$：结论对不可观测选择稳健
- $\delta < 1$：结论脆弱

### 6.5 Honest DiD

$$\Delta^{Honest}(\bar{M}) = \{\beta^{post} : |\beta_t^{trend} - \beta_{t-1}^{trend}| \leq \bar{M} \cdot |\beta_{-1}^{trend}|\}$$

- $\bar{M}$：允许的平行趋势偏离倍数
- 报告：在 $\bar{M}$ 多大时效应不再显著
