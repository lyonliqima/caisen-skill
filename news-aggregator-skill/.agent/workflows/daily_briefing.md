---
description: Generate comprehensive daily briefing reports
---

1. Execute the daily briefing script for the specified profile (general, finance, tech, social, ai_daily, reading_list):
   // turbo
   `python3 scripts/daily_briefing.py --profile {{profile}}`

2. Read the generated JSON file from the default output directory `reports/YYYY-MM-DD`.

3. Read the relevant instruction file in `instructions/` (e.g., `briefing_general.md`).

4. Generate the final Markdown report as per SKILL.md:
   - Translate content to Simplified Chinese.
   - Provide Deep Dive insights.
   - Format using the strict template.
   - Save to `reports/YYYY-MM-DD/{{profile}}_briefing_report.md`.

5. Notify the user of completion.
