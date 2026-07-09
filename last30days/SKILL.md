---
name: last30days
version: "3.3.1"
description: "近30天多平台舆情研究工具。研究任何话题在过去30天内Reddit/X/YouTube/TikTok/HackerNews/Polymarket/GitHub/网络上的讨论和互动数据。在四方法论框架中作为辅助参考，提供舆情背景数据。"
argument-hint: 'last30days nvidia earnings reaction | last30days AI video tools | last30days what users want in react'
allowed-tools: Bash, Read, Write, AskUserQuestion, WebSearch
homepage: https://github.com/mvanhorn/last30days-skill
repository: https://github.com/mvanhorn/last30days-skill
author: mvanhorn
license: MIT
user-invocable: true
metadata:
  openclaw:
    emoji: "📰"
    requires:
      env: []
      optionalEnv:
        - SCRAPECREATORS_API_KEY
        - OPENAI_API_KEY
        - XAI_API_KEY
        - OPENROUTER_API_KEY
        - PARALLEL_API_KEY
        - BRAVE_API_KEY
        - APIFY_API_TOKEN
        - AUTH_TOKEN
        - CT0
        - BSKY_HANDLE
        - BSKY_APP_PASSWORD
        - TRUTHSOCIAL_TOKEN
      bins:
        - node
        - python3
    primaryEnv: SCRAPECREATORS_API_KEY
    files:
      - "scripts/*"
    homepage: https://github.com/mvanhorn/last30days-skill
    tags:
      - research
      - deep-research
      - reddit
      - x
      - twitter
      - youtube
      - tiktok
      - instagram
      - hackernews
      - polymarket
      - digg
      - bluesky
      - truthsocial
      - trends
      - recency
      - news
      - citations
      - multi-source
      - social-media
      - analysis
      - web-search
      - ai-skill
      - clawhub
---

# last30days：近30天多平台舆情研究工具
> **核心定位**：这是一个有严格输出契约的固定研究工具，必须运行 `scripts/last30days.py` 引擎并遵守下方的工作流程与 LAW 契约。详细的步骤、契约与合成模板已拆至 `references/`，本文件只保留流程骨架与索引。

## 工作流程 / 使用步骤

## 工作流程 / 使用步骤

`/last30days` 是一个固定研究工具，必须按 SKILL.md 的契约自上而下执行，切勿当作普通搜索关键词即兴发挥。核心步骤概览（每个步骤的完整细节见下方 references）：

0. **STALE-CLONE 自检 + SKILL CONTRACT + OUTPUT CONTRACT(LAWS)**：首次读取先做陈旧克隆自检；输出必须遵守 8 条 LAW（无 `Sources:` 块、无臆造标题、无破折号、无 `##` 正文小标题、引擎页脚透传、不 dumping 原始证据、命名实体必须 `--plan`、引用一律内联链接）。详见 `references/00-contract-laws.md`。
1. **HOW TO INVOKE**：每次调用第一个工具必须是 `ToolSearch select:WebSearch`；随后必须运行 `scripts/last30days.py`（WebSearch 只是补充，不能替代引擎）。详见 `references/01-howto-invoke.md`。
2. **Parse User Intent**：解析 TOPIC / TARGET_TOOL / QUERY_TYPE（PROMPTING / RECOMMENDATIONS / NEWS / COMPARISON / GENERAL）。详见 `references/02-parse-intent.md`。
3. **Step 0.45 查询质量预检**：识别关键词陷阱（人口送礼/数字碰撞/字面教程语/单名词），必要时先澄清再跑引擎。详见 `references/03-query-preflight.md`。
4. **Step 0.5 / 0.5b / 0.5c 预检解析**：解析 X handle、GitHub 用户名(人物)、GitHub 仓库(项目)、subreddits 等，清单内适用项全部必填。详见 `references/04-preflight-resolution.md`。
5. **Agent Mode / COMPARISON / Competitor mode**：`--agent` 静默报告；`X vs Y` 与 `--competitors` 走逐实体解析 + `--competitors-plan`。详见 `references/05-agent-comparison.md`。
6. **Step 0.55 研究前情报**：解析社群与 handle（含品类 peer 扩展）。详见 `references/06-step-055.md`。
7. **Step 0.75 生成查询计划**：你是规划器，生成 JSON 计划经 `--plan` 传入引擎。详见 `references/07-step-075.md`。
8. **Research Execution**：满足前置门后运行 `scripts/last30days.py`（含 `--plan`、`--save-dir` 等）。详见 `references/08-research-execution.md`。
9. **Step 2 / 2.5 WebSearch 补充**：脚本跑完后再做 WebSearch 补充，并追加到保存的原始文件。详见 `references/09-step2-websearch.md`。
10. **Judge Agent 综合(synthesis)**：按查询类型套用模板（RECOMMENDATIONS / COMPARISON 等），遵守 VOICE CONTRACT。详见 `references/10-judge-synthesis.md`。
11. **呈现与收尾**：内部化研究 → 输出合成 → 摘要+邀请；含 PRE-PRESENT 自检、可分享 HTML、追问处理、提示词专家模式、安全与权限。详见 `references/11-presentation.md` 与 `references/12-security.md`。

## 参考索引（references）

| 文件 | 内容 |
|------|------|
| references/00-contract-laws.md | STEP 0 陈旧克隆自检、SKILL CONTRACT、OUTPUT CONTRACT(BADGE+LAW 1-8)、VOICE CONTRACT LAW |
| references/01-howto-invoke.md | HOW TO INVOKE、Runtime Preflight、Configuration、Step 0 首次设置向导 |
| references/02-parse-intent.md | CRITICAL: Parse User Intent（TOPIC/TARGET_TOOL/QUERY_TYPE 解析与确认） |
| references/03-query-preflight.md | Step 0.45 查询质量预检(4类关键词陷阱) 与 Step 0.5 预检解析清单 |
| references/04-preflight-resolution.md | Section A 解析 X handle、Step 0.5b GitHub 用户名、Step 0.5c GitHub 仓库 |
| references/05-agent-comparison.md | Agent Mode(`--agent`)、COMPARISON(`X vs Y`)、Competitor mode(`--competitors`) |
| references/06-step-055.md | Step 0.55 研究前情报(解析社群/handle，含品类 peer 扩展与自查) |
| references/07-step-075.md | Step 0.75 生成查询计划(你是规划器，输出 JSON 经 `--plan` 传入) |
| references/08-research-execution.md | Research Execution 与 PRECONDITION GATE（引擎调用前置条件） |
| references/09-step2-websearch.md | Step 2 脚本完成后做 WebSearch、Step 2.5 追加到保存的原始文件 |
| references/10-judge-synthesis.md | Judge Agent 综合合成、各类来源指引、查询类型模板(FIRST 内部化/摘要) |
| references/11-presentation.md | 呈现与收尾：PRE-PRESENT 自检、可分享 HTML、追问处理、提示词专家模式、CONTEXT MEMORY |
| references/12-security.md | Security & Permissions（权限与凭据说明） |
