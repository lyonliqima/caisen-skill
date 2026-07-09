# Serenity Method — Glossary

Plain-language definitions for the jargon that recurs in this domain. **Define a term on first use** in any deliverable. Keep definitions this short.

## CPO / 光通信链
- **CPO（Co-Packaged Optics，共封装光学）** — 把光引擎直接和交换/计算芯片封在一起，减少铜线损耗。AI 服务器里"用光搬数据"的方案。
- **Photonics / 光子学** — 用光（而非电）来传输/处理信息的器件与技术。
- **激光器 / 光源（laser / light source / ELS, external light source）** — CPO 里发光的源头；常是供给瓶颈。
- **光互连（optical interconnect）** — 芯片间/机架间用光来连接。
- **光模块 / 收发器（transceiver）/ 可插拔（pluggable）** — 把电信号转成光信号收发的部件；1.6T 指带宽等级。
- **LRO（linear receive optics 等）** — 一类光模块产品线（如"1.6T LRO"）。
- **光引擎（optical engine）/ ELS / 光收发栈** — 光模块内部的功能模块，常被并购整合的对象。
- **FAU（Fiber Array Unit，光纤阵列单元）** — 把多根光纤精确对齐封装的关键被动件；CPO 放量时易成瓶颈。
- **封测（packaging & test，封装与测试）** — 把芯片/光器件封装并测试；供应链里容易被忽略、却可能卡脖子的环节。
- **基底 / 衬底（substrate）/ 外延片（epiwafer）** — 上游材料；如 SOI 衬底、化合物半导体外延片。

## 功率半导体 / 电源
- **800VDC** — 数据中心用更高直流电压来降低电力损耗；AI 耗电飙升后变重要。
- **功率半导体（power semi）** — 处理高电压/大电流的芯片。
- **SiC / GaN（碳化硅 / 氮化镓）** — 更适合高压高效电源的宽禁带（wide-bandgap）材料。
- **Foundry（代工厂）** — 替别人制造芯片的工厂；资本开支重。

## 估值 / 财务
- **TAM（Total Addressable Market，潜在总市场）** — 一个产品/公司理论上能触达的总市场规模。
- **ASP（Average Selling Price，平均售价）** — 单位产品平均卖价；ASP 提升=提价能力线索。
- **毛利率（gross margin）** — (收入−成本)/收入；高毛利常意味定价权。
- **P/B（市净率，price-to-book）** — 股价/每股净资产；低 P/B **不**等于便宜，foundry 尤其要看 ROIC/利用率。
- **ROIC（投入资本回报率）** — 资本开支重的公司必看。
- **owner earnings（所有者收益）** — Buffett 的"真实可分配现金流"概念；估值的根。
- **ATM（At-The-Market offering，随行就市增发）** — 公司随时按市价增发新股换现金；**稀释**现有股东、短期股价压力。
- **稀释（dilution）** — 新增股份摊薄每股价值。
- **ramp（量产爬坡）** — 产能/收入从小批量走向规模量产的过程。

## 护城河 / 风险
- **护城河（moat）** — 让公司长期保持高回报、难被抢走的结构性优势。
- **切换成本（switching cost）** — 客户更换供应商的代价（认证、重设计、停产风险）。
- **二供 / 第二供应商（second source）** — 大客户通常会培养备选供应商，降低被单一供应商卡住的风险 → 抬高"客户替换风险"。
- **认证周期（certification cycle / qualification）** — 客户验证并把某供应商正式设计进产品的过程；过了认证=切换成本上升。
- **sole source / primary source（独家 / 主供）** — 客户只用/主要用某一家；强卡位信号（仍需合同验证）。

## 资金 / 叙事（非基本面）
- **指数纳入（MSCI / Nasdaq inclusion）** — 被纳入指数后指数基金被动买入；真实催化，但**非基本面**。
- **uplisting / 双重上市（dual-listing）** — 升板/到另一交易所上市，提升流动性。
- **gamma / 逼空（short squeeze）** — 期权对冲/空头回补引发的非基本面急涨。
- **FUD（Fear, Uncertainty, Doubt）** — 散布恐慌/质疑的负面叙事；是情绪，不是分析。
- **OSINT（开源情报）** — 用公开信息（监管文件、年报、客户官网、转录）拼出供应链真相。

## 分类标签（本方法专用）
- **研究地图（research map / research lead）** — 值得跟踪的线索；默认结论。
- **可投资结论（investable conclusion）** — 只有在完成护城河 + 财务 + 估值 + 安全边际后才成立；**绝不**仅凭推文得出。
- **unverified / 证据不足** — Buffett 各字段的默认值；没有引用证据就不上调。
