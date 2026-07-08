# agent.md — 蔡森 skill 代理约定

> 本文件记录 agent（WorkBuddy）在「蔡森破底翻 / 形态学」相关任务中的固定约定，
> 用户希望以后提到相关需求时，agent 直接按此执行，无需再次确认。

## 约定 1：破底翻选股

**触发条件**：用户提到「选破底翻股票」「挑破底翻」「破底翻筛选」「找破底翻」等类似表述。

**执行动作**：直接运行脚本
`/Users/weihaoli/Desktop/蔡森 skill/蔡森破底翻量化筛选器.py`

**脚本要点（运行前须知）**：
- 数据源：
  - 上涨股列表：新浪财经列表 API（无需密钥）。
  - K线历史：**多源容错链，东方财富首选**，自动降级。
    - 优先级：**东方财富 push2his（首选）** → 新浪 K线 API → 腾讯财经 fqkline（最终兜底）。
    - 三者均返回统一结构 `list[dict(date,open,close,high,low,volume)]`，detector 无感切换。
    - 东方财富被限流/不可达时，自动落到新浪/腾讯，不会因单接口故障导致整轮失败。
    - ⚠️ 沙箱运行环境对 `push2his.eastmoney.com` 网络层拦截（RemoteDisconnected），
      故在 WorkBuddy 沙箱内跑会直接降级到新浪/腾讯；**用户本机运行东方财富可正常首选**。
- 逻辑：先拉取全市场上涨股（涨幅 ≥ 0.5%），再逐只检测「破底翻 + 长期历史低位」。
  - 长期低位过滤：历史分位 < 30% 且距一年高点跌幅 > 40%。
  - 破底翻检测：60 日窗口内存在支撑位 → 之后跌破（破底深度 > 3%）→ 现已收回支撑之上。
  - 按 confidence（60~75）评分，并输出分级（极高 ≥70 / 高 67-69 / 中 63-66 / 低 60-62）。
- 输出：
  - 控制台打印分级候选列表与统计。
  - 同时写 CSV：`/Users/weihaoli/Desktop/蔡森 skill/破底翻候选_YYYYMMDD.csv`（utf-8-sig）。
- 依赖：`requests`、`pandas`、`numpy`。建议用 managed Python 的 venv：
  `/Users/weihaoli/.workbuddy/binaries/python/envs/default/bin/python`
- 耗时：受网络与线程（8 线程）影响，通常几分钟；失败时脚本会跳过并计入失败数。

**注意**：运行后向用户展示结果（候选清单 / CSV 路径）。CSV 默认落在用户 Desktop 的蔡森 skill 目录。
