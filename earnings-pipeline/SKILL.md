# Earnings Pipeline — Batch Transcript Analysis with Dual-AI

## When to Use

- User says "earnings pipeline", "批量分析", or mentions 2+ tickers with a quarter for earnings analysis
- If only 1 ticker → route to `/organizer-transcript` instead

## Pre-flight (Steps 1-4)

### Step 1: Parse tickers

```python
import sys
sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
from shared.entity_resolver import resolve_entity
```

For each ticker the user provides, call `resolve_entity(ticker)`. Collect the resolved `ticker` (e.g., "HOOD-US") and `canonical_name`. If resolution fails, inform the user and skip that ticker.

### Step 2: Create run workspace

Create the run directory:
```
C:\Users\thisi\.claude\skills\earnings-pipeline\runs\{YYYYMMDD_HHMM}\
```

And a subdirectory per ticker:
```
runs\{YYYYMMDD_HHMM}\{TICKER}\
```

### Step 3: Find transcripts

Run:
```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe \
  C:/Users/thisi/.claude/skills/earnings-pipeline/scripts/find_transcripts.py \
  --tickers HOOD-US META-US GOOGL-US \
  --quarter "Q4 2025" \
  --run-dir C:/Users/thisi/.claude/skills/earnings-pipeline/runs/{timestamp}/
```

This creates `manifest_{TICKER}.json` per ticker in the run directory. Check output for errors — if a ticker has no transcript PDFs found, report it to the user and ask if they want to proceed without it.

### Step 4: Load insights

Run:
```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe \
  C:/Users/thisi/.claude/skills/earnings-pipeline/scripts/load_insights.py \
  --tickers HOOD-US META-US GOOGL-US \
  --run-dir C:/Users/thisi/.claude/skills/earnings-pipeline/runs/{timestamp}/
```

This patches each manifest JSON with insight context (or null if no insights exist).

### Step 5: Check existing analyses

For each ticker, check if an analysis already exists in the vault at:
`~/Documents/Obsidian Vault/研究/财报分析/{TICKER}/`

If any exist for the same quarter, list them and ask the user: "Skip or re-analyze?"

## Dispatch (Step 6)

Launch one `Task` sub-agent per ticker, all in parallel (up to 5 concurrent). Use `subagent_type="general-purpose"`.

**Sub-agent prompt template** (fill in `{manifest_path}` and `{skill_dir}`):

```
You are analyzing an earnings transcript as part of a batch pipeline. Follow these steps exactly. Do not ask for user confirmation at any step. Proceed automatically.

MANIFEST: Read the manifest file at: {manifest_path}
It contains: ticker, company, quarter, prev_quarter, curr_pdf, prev_pdf, workdir, insights

STEP 1 — Read manifest
Read {manifest_path} to get all paths and context.

STEP 2 — Read transcript PDFs
Read the PDF files specified in curr_pdf and prev_pdf from the manifest. If prev_pdf is null, proceed in single-quarter mode (analyze only current quarter, skip QoQ comparisons).

STEP 3 — Run Gemini analysis
Execute:
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe {skill_dir}/scripts/gemini_analyzer.py --manifest {manifest_path}

This writes gemini_output.md to the ticker's workdir. Allow up to 5 minutes timeout.

STEP 4 — Read Gemini output
Read {workdir}/gemini_output.md. If the file starts with "STATUS: FAILED", note "Gemini unavailable" and proceed with Claude-only analysis (skip the divergence section later).

STEP 5 — Produce unified analysis
You must use this exact prompt template to structure your analysis. Import it:

The analysis prompt template requires 7 sections:
1. 综合评估与投资启示 (Synthesis & Implications)
2. 业绩概览 (Performance Snapshot)
3. 核心业绩驱动 (Segment & Geographic Drivers)
4. 管理层叙事演变 (Management Narrative Evolution)
5. 分析师Q&A透视 (Q&A Deep Dive)
6. 季度间主题演变 (Thematic Evolution)
7. 前次 Insight 验证追踪 (Prior Insight Tracking) — only if insights provided

Read the prompt template at: C:/Users/thisi/.claude/skills/organizer-transcript/prompts/prompt_claude.py
Use the get_claude_prompt() function's output as your structural guide. Fill in the company name, ticker, current quarter, previous quarter.

If insights were provided in the manifest, include Section 7 (Prior Insight Tracking).

Your analysis is the PRIMARY analysis. Use your own reading of the transcripts as the authoritative source.

If Gemini succeeded, ALSO read the Gemini output and append this section at the end:

## 双AI对比笔记 (Dual-AI Divergence Notes)

Compare your analysis with Gemini's analysis across these dimensions:

| 维度 | Claude 观点 | Gemini 观点 | 差异分析 |
|:---|:---|:---|:---|
| Bull/Base/Bear 概率 | [your probabilities] | [Gemini's probabilities] | [explain differences] |
| 核心风险 | [your top risks] | [Gemini's top risks] | [any risks one missed] |
| Q&A 覆盖 | [your Q count] | [Gemini's Q count] | [coverage gaps] |
| 关键分歧 | — | — | [material disagreements and your reasoning] |

Where you and Gemini diverge materially, explain your reasoning for why your view is more accurate, citing specific transcript evidence.

IMPORTANT: After producing your analysis, do NOT re-read the PDF files.

STEP 6 — Save draft
Write your complete analysis to: {workdir}/analysis_draft.md
Use encoding='utf-8'.

STEP 7 — Validate
Run:
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe {skill_dir}/scripts/validate_analysis.py --content-file {workdir}/analysis_draft.md

If validation fails: review the issues in the output, fix your analysis, save again to analysis_draft.md, and re-validate. Max 2 fix attempts. If still failing after 2 tries, proceed anyway.

STEP 8 — Save to Obsidian
Run:
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe {skill_dir}/scripts/save_analysis.py --manifest {manifest_path} --content-file {workdir}/analysis_draft.md

Capture the output (saved file path).

STEP 9 — Write result.json
Write this JSON to {workdir}/result.json:
{
  "ticker": "<TICKER>",
  "status": "success",
  "analysis_path": "<path from save_analysis output>",
  "gemini_status": "success|failed|skipped",
  "validation_scores": <paste validation output>,
  "summary": "<Two-line summary of the key findings from your analysis>"
}

If ANY step fails with an unrecoverable error, write result.json with "status": "failed" and "error": "<description>".

CRITICAL RULES:
- Do not ask for user confirmation at any step. Proceed automatically.
- After producing your analysis, do not re-read the PDF files.
- If Gemini fails, proceed with Claude-only analysis (no divergence section).
- If any Python script fails, capture the error and write it to result.json.
- Use encoding='utf-8' for all file writes.
```

## Monitor (Step 7)

After dispatching all sub-agents:

1. Wait for sub-agents to complete (they will return naturally)
2. For each ticker, read `{workdir}/result.json`:
   - If file exists and `status: "success"` → ticker complete
   - If file exists and `status: "failed"` → report error, ask user to retry
   - If sub-agent returned but no result.json → report as stalled
3. For failed tickers, offer to retry (max 2 retries per ticker)

## Dashboard (Step 8)

Once all tickers are complete (or max retries exhausted), run:

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe \
  C:/Users/thisi/.claude/skills/earnings-pipeline/scripts/generate_dashboard.py \
  --run-dir C:/Users/thisi/.claude/skills/earnings-pipeline/runs/{timestamp}/ \
  --quarter "Q4 2025"
```

Report the dashboard path and a summary table to the user.

## Output Format

Present final results as:

```
## Earnings Pipeline Complete

| Ticker | Status | AI Provider | Sections | Citations | Path |
|:---|:---|:---|:---|:---|:---|
| HOOD-US | ✅ | claude+gemini | 7/7 | 45 | [[HOOD-US Q4 2025 vs Q3 2025 Analysis]] |
| META-US | ✅ | claude+gemini | 7/7 | 52 | [[META-US Q4 2025 vs Q3 2025 Analysis]] |
| GOOGL-US | ⚠️ | claude-only | 6/7 | 38 | [[GOOGL-US Q4 2025 vs Q3 2025 Analysis]] |

Dashboard: [[2026-02-12 1430 Q4 2025 Pipeline Dashboard]]

Next actions:
- Review individual analyses for accuracy
- Check 双AI对比笔记 sections for material divergences
- Run `/rq {TICKER}` for any research questions generated
```

## Skill Lessons

Before running, check lessons:
```python
from shared.skill_lessons import read_lessons
print(read_lessons("earnings-pipeline"))
```

After completion, if anything noteworthy happened (error, workaround, surprising result):
```python
from shared.skill_lessons import write_lesson
write_lesson("earnings-pipeline", "Summary line\nDetail...")
```
