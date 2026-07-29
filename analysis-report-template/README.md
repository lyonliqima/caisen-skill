# analysis-report-template · 分析报告 HTML 模板

固定一套外壳（`shell.html` 含全部 CSS + Chart.js helper），分析类 skill 只填内容槽位，token 量砍半。

## 文件
| 文件 | 谁读 | 作用 |
|---|---|---|
| `shell.html` | 仅 render.py | 外壳：全部 CSS + 图表 JS + `{{TITLE}}{{DATE}}{{BODY}}` 槽位 |
| `render.py` | agent 调用 | body 片段 → 完整 HTML（自动清掉未用槽位） |
| `components.md` | **agent 必读** | 可用 class / 图表 helper 参考 |

## 用法
```bash
python3 analysis-report-template/render.py \
  <主题>-报告.body.html \
  <主题>-报告.html \
  --title="<主题> · 整合市场分析报告"
```
body 片段写法见 `components.md`。

## 接入的 skill
- `integrated-market-analysis` —— L2/L3 报告套用本模板
- `caisen-10-experts-analyst` —— L3/L4 报告套用本模板

> 圆桌报告（腾讯自选股投研专家团）仍用 `stock-partner-team/skills/md-to-html`，结构不同，不复用本模板。
