---
name: research
description: "股票研究统一入口，整合知识库、网络搜索、多 AI 验证。Use when user says 'research', '研究', 'look up ticker', or wants to investigate a stock with multi-source verification."
metadata:
  version: 1.0.0
---

# /research - 一键研究命令

股票研究的统一入口，整合知识库、网络搜索、多 AI 验证。

## 执行步骤

1. **解析输入**
   - 提取 TICKER 或研究主题
   - 识别 --deep 标志
   - 提取具体问题（如有）

1.5 **检查历史 Open Questions**
   - 调用 `task_manager.py questions TICKER` 查看该 ticker 的未解决问题
   - 如果有 open questions，在报告开头展示：
     ```
     > 📌 **上次研究遗留问题：**
     > 1. [HIGH] 问题描述...
     > 2. [MED] 问题描述...
     > 本次研究将优先尝试回答这些问题。
     ```
   - 本次研究中如果回答了旧问题，调用 answer_question() 更新状态

2. **市场数据快照**（仅个股 Ticker，主题研究跳过）
   ```bash
   cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/market_snapshot.py TICKER
   ```
   - 自动拉取: 价格/52周区间/市值、估值指标(P/E/PEG/EV)、盈利能力(毛利率/ROE)、分析师目标价与评级、内部人交易、机构持仓 Top 10
   - 输出直接嵌入报告的 `公司概况` 和 `估值参考` 部分
   - 来源标注: `[YF]` (Yahoo Finance via yfinance)
   - 可选按模块调用: `--section price`, `--section analysts` 等
   - JSON 模式: `--json` 输出机器可读格式

### Step 2b: Sector Context Loading

Resolve sector for targeted research:
1. Check `shared/entity_dictionary.yaml[TICKER].sector` → map to `shared/references/sector_metrics.yaml`
2. Load `canonical_kpis` for the resolved sector
3. In the 估值参考 table, replace generic metrics with sector-appropriate ones:
   - SaaS: ARR, NRR, RPO, EV/ARR, Rule of 40
   - Semiconductors: GM%, Inventory Days, Book-to-Bill, Data Center Revenue %
   - Financials: NII, NIM, NCO Rate, CET1, P/TBV
   - Consumer Staples: Volume vs Price, Market Share, Scanner Data
   - Healthcare: Pipeline status, TRx/NRx trends, Formulary access %
   - (See `shared/references/sector_metrics.yaml` for full list)
4. Use `research_queries` from sector_metrics.yaml to supplement the web search queries in Steps 3-4

3. **知识库检索**
   - 查询 knowledge_index: `kb_ingestion.py search --ticker TICKER`
     获取所有已入库的研报/纪要，来源标注 [KB]
   - 搜索 `PORTFOLIO/portfolio_monitor/research/companies/{TICKER}/`
   - 搜索 Obsidian `收件箱/` 相关文章
   - 读取现有 thesis.md（如有）

3. **Supply Chain Context**
   - 查询 `~/.claude/skills/supply-chain/data/supply_chain.db`：
     `SELECT * FROM mentions WHERE mentioned_ticker = '{TICKER}' ORDER BY date DESC`
   - 或读取 `~/Documents/Obsidian Vault/研究/供应链/{TICKER}_mentions.md`
   - 展示：哪些公司在财报中提到了该 ticker，说了什么（前瞻性信号）

4. **13F Institutional Activity**
   - 搜索 `~/13F-CLAUDE/output/*/` 中的 CSV 文件，查找包含该 ticker 的持仓记录
   - 展示：哪些知名基金经理持有该 ticker，季度变动趋势
   - 这是 "smart money" 验证——机构是在买入还是卖出

5. **Podcast Mentions**
   - 搜索 `~/Documents/Obsidian Vault/信息源/播客/` 中提到该 ticker/公司名的播客
   - 提取关键论点和数据点

6. **ChatGPT Prior Analysis**
   - 搜索 `~/Documents/Obsidian Vault/ChatGPT/Investment Research/` 中提到该 ticker 的对话
   - 提取之前的分析观点，避免重复研究

7. **NotebookLM 查询**（如果有相关 notebook）
   - 调用 `/notebooklm` 查询相关内容
   - 获取 citation-backed 答案

8. **网络搜索**（--deep 模式）
   - WebSearch 最新新闻、财报
   - 搜索竞争对手动态

4.5 **Data Freshness Verification (3-Month Rule)**

After gathering data from all sources (vault, web, multi-AI), verify freshness before synthesis:

### Verification Checklist
1. **Earnings data:** Is the latest quarter's data included? If the most recent 10-Q/K is >90 days old, flag: "⚠️ Latest filing is from {date} — a newer quarter may be available"
2. **Stock price / valuation:** Must be from today (pull fresh via yfinance). Never use cached prices for valuation context.
3. **Consensus estimates:** Check date of consensus data. If >7 days old for active coverage, note the date: "Consensus as of {date}"
4. **Industry data:** Market share, TAM, competitive data >6 months old should be flagged: "⚠️ Industry data from {date} — may be outdated"
5. **Vault sources:** For each Obsidian note referenced, check the note's date. If >90 days old, note: "Based on {date} analysis — verify current relevance"

### Staleness Flags in Output
When any data source is flagged, add a warnings block near the top of the report:
```
⚠️ Data Freshness Warnings:
- Earnings: Latest is Q3 2025 (filed Nov 2025) — Q4 may be available
- Industry report: From Aug 2025 — market conditions may have changed
```

**Sector-Specific Data Sources:**
When verifying data freshness (Step 4.5), use the `data_source` hints from `sector_metrics.yaml[sector].canonical_kpis` to identify authoritative sources for each KPI.

### Auto-Refresh Triggers
If staleness is detected AND the research mode is `--deep` or `--coverage`:
- Automatically search for newer filings: `WebSearch "{TICKER} 10-Q 2026 site:sec.gov"`
- Check for recent earnings: `WebSearch "{TICKER} Q4 2025 earnings results"`
- Update vault note dates in the source attribution table

5. **生成研究报告**
   - 按输出格式整合信息
   - 按 Source Attribution 规则为每条事实性陈述添加来源标签
   - 定量数据必须有具体来源标签（不允许 [Model]）
   - 标记需要进一步验证的假设

6. **提取并记录 Open Questions**
   - 从报告中识别标记为 "❓ 待研究" 的问题和数据缺口
   - 将新 open questions 写入 SQLite:
     ```python
     from shared.task_manager import add_open_question
     add_open_question(ticker, question, priority="medium", context="...", source_note="{research_note_path}")
     ```
   - 同时写入研究笔记的 frontmatter `open_questions:` 字段（仅问题文本列表）
   - 如果本次回答了之前的 open question，更新 DB status 为 answered:
     ```python
     from shared.task_manager import answer_question
     answer_question(question_id, answered_in="{research_note_path}", answer_summary="...")
     ```

7. **保存到 Obsidian**
   - 路径: `Documents/Obsidian Vault/研究/研究笔记/{TICKER}_YYYY-MM-DD.md`
   - 更新 thesis 文件（如适用）

## Important Rules

- **MUST** tag every factual statement with a source label (e.g., `[YF]`, `[Vault]`, `[Web]`). No untagged facts.
- **NEVER** use `[Model]` for quantitative data — model knowledge is not a valid source for numbers.
- **MUST** cross-reference contradictory information: when sources conflict, explicitly note the discrepancy and tag all sides.
- **NEVER** make buy/sell recommendations — only provide analysis framework and data.
- **MUST** timestamp all valuation data (P/E, price targets, etc.).
- **MUST** display open questions from previous sessions at the top of the report before starting new analysis.
- When multiple sources confirm the same fact, tag all of them: e.g., `[Vault][Transcript]`.

## 使用方式

```
/research TICKER                    # 快速研究（用现有知识）
/research TICKER --deep             # 深度研究（9 维度框架输出）
/research TICKER --coverage         # 框架覆盖度分析
/research TICKER "具体问题"          # 针对性研究
```

## 示例

```
/research NVDA                      # NVDA 快速概览
/research NVDA --deep               # NVDA 9 维度框架深度研究
/research NVDA --coverage           # NVDA 覆盖度矩阵 + 研究盲区
/research NVDA "AI 芯片竞争格局"     # 针对性问题
/research "数据中心电力"             # 主题研究（非个股）
```

## 配置
- 研究偏好：`shared/research_preferences.yaml`（投资风格、写作格式、来源标签）
- 分析框架：`shared/analysis_framework.yaml`（9 维度定义）

## 研究流程

```
输入 Ticker/主题
       ↓
┌──────┴──────┐
│ 市场数据快照 │ → yfinance: 价格、估值、分析师、内部人 [YF]
└──────┬──────┘
       ↓
┌──────┴──────┐
│  知识库检索  │ → 读取 Obsidian 笔记、历史 thesis
└──────┬──────┘
       ↓
┌──────┴──────┐
│  NotebookLM │ → 查询已有研报、纪要（如有）
└──────┬──────┘
       ↓ (--deep 模式)
┌──────┴──────┐
│  网络搜索   │ → WebSearch 最新信息
└──────┬──────┘
       ↓
┌──────┴──────┐
│  生成报告   │ → 结构化输出，标注来源
└──────┬──────┘
       ↓
┌──────┴──────┐
│  保存笔记   │ → Obsidian Research Notes
└─────────────┘
```

## 输出格式

```markdown
# {TICKER} 研究笔记
日期: YYYY-MM-DD

## 📋 核心观点 (TLDR)
- 一句话总结 [source tag]

## 🏢 公司概况
- 业务模式 [Vault]
- 竞争格局 [Web]
- 核心指标 [YF] (市值、P/E、营收、利润率等)

## 📊 投资逻辑
- 核心假设 1 [Thesis]
- 核心假设 2 [NLM]

## ⚠️ 风险因素
- 风险 1 [Transcript]
- 风险 2 [Web]

## 📈 估值参考
- 当前估值 [YF] (P/E, PEG, EV/EBITDA, P/B)
- 分析师目标价与评级 [YF]
- 历史区间 [YF]
- 可比公司 [Web]

## 🔗 来源

| Source | Type | Date | Key Finding | Last Verified |
|--------|------|------|-------------|---------------|
| [YF] Yahoo Finance | Primary | {today} | Price, valuation, analysts | {today} ✅ |
| [Vault] Obsidian KB | Primary | {note_date} | Prior analysis | {note_date} ✅ or ⚠️ >90d |
| [NLM] NotebookLM | Secondary | {query_date} | Research reports, transcripts | {query_date} ✅ |
| [13F] Institutional | Secondary | {filing_date} | Smart money positioning | {filing_date} ✅ or ⚠️ >90d |
| [SC] Supply Chain | Secondary | {sc_date} | Cross-company mentions | {sc_date} ✅ or ⚠️ >90d |
| [Web] Web Search | Primary | {today} | Latest news, filings | {today} ✅ |
| [Thesis] Thesis file | Primary | {thesis_date} | Core assumptions | {thesis_date} ✅ or ⚠️ >90d |
| [Transcript] Earnings call | Primary | {transcript_date} | Mgmt guidance, KPIs | {transcript_date} ✅ or ⚠️ >90d |
| [ChatGPT] Prior analysis | Secondary | {chat_date} | Historical notes | {chat_date} ✅ or ⚠️ >90d |
| [Model] Model knowledge | Tertiary | N/A | General context only | N/A — no quant data |

> ✅ = verified fresh (within threshold). ⚠️ >90d = stale, treat with caution.
```

## Source Attribution

研究报告中的每一条事实性陈述都必须附带来源标签，标注信息的出处。

来源标签定义和标注规则见 `shared/research_preferences.yaml`。

### 标注示例

```markdown
## 📊 投资逻辑
- ZYN 出货量 Q4 2025 同比增长 35%，管理层上调全年指引至 9 亿罐 [Transcript]
- 19 家机构在 Q4 13F 中报告持有 PM 头寸，较 Q3 净增 3 家 [13F]
- 供应链数据显示 PM 在意大利扩建 IQOS 生产线，新增 2 个合同制造商 [SC]
- 管理层信誉评分：EPS 指引准确率 A+，ZYN 库存预测准确率 D+ [NLM]
- 当前 P/E 22.3x，高于 5 年均值 18.1x，PEG 1.8x [YF]
- 上周 Barclays 上调目标价至 $145，基于 smoke-free 转型加速 [Web]
- 此前 thesis 中的核心假设"ZYN 将成为第二增长曲线"已得到验证 [Thesis]
- Robin 在 11 月 ChatGPT 对话中分析过 PM 的定价权，结论为强定价权 [ChatGPT]
- 烟草行业监管风险仍在，FDA 政策变动可能影响 IQOS 审批时间线 [Model]

## ⚠️ 风险因素
- FDA 对 IQOS 的 PMTA 审批存在不确定性，最新进展未明 [Web]
- 竞争对手 BAT 的 Vuse 在美国市占率提升至 38% [Transcript][Vault]
```

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/thesis` | 读取/更新 thesis 文件 |
| `/notebooklm` | 查询已有研报知识库 |
| `/portfolio` | 获取持仓信息 |
| `/supply-chain` | 查询供应链提及（谁在财报中提到该 ticker） |
| `/13f` | 查询机构持仓变动（smart money 验证） |
| `/podcast` | 搜索播客中的 ticker 相关讨论 |
| `/chatgpt-organizer` | 搜索历史 ChatGPT 投资分析 |
| `/wechat-hao` | 导入的文章可被检索 |

## 配置

研究偏好在 `CLAUDE.md` 中定义：
- 投资风格: Long-biased, fundamental research
- 输出风格: 数据驱动，表格对比

## 注意事项

- 所有事实性陈述必须标注来源标签（见 Source Attribution 章节），定量数据不允许使用 [Model]
- 多来源交叉验证的信息标注所有来源，如 `[Vault][Transcript]`
- 遇到矛盾信息时明确指出，并标注各方来源
- 估值数据标注时间戳
- 不做买卖建议，只提供分析框架

## 🪞 反思检查站

> 每次 /research 输出末尾自动追加。问题来自 `shared/reflection_questions.yaml`。

研究报告生成后，在末尾追加：

```markdown
## 🪞 反思检查站
> 以下问题旨在对抗 confirmation bias。请逐一思考后再做投资决策。

1. **核心假设脆弱性：** [回答 R1]
2. **市场隐含预期：** [回答 R2]
3. **改变看法的信号：** [回答 R3]
4. **反面最强论点：** [回答 R4]
5. **Base Rate 参照：** [回答 R5]
6. **近因偏误检查：** [回答 R6]
7. **持仓偏误检查：** [回答 R7]
```

Claude 应基于研究过程中收集到的信息尝试回答每个问题，而非留空。如果无法回答，标注 "❓ 需要进一步研究"。

## `--coverage` 模式：框架覆盖度分析

当用户使用 `/research TICKER --coverage` 时：

1. 运行覆盖度扫描：
   ```bash
   cd ~/.claude/skills && python shared/framework_coverage.py scan TICKER
   ```
2. 展示 9 维度覆盖矩阵（covered/partial/gap）
3. 展示研究盲区和建议的研究问题：
   ```bash
   cd ~/.claude/skills && python shared/framework_coverage.py questions TICKER
   ```
4. 输出覆盖度分数和下一步行动建议

**Sector Coverage Gap Detection:**
After standard framework coverage scan, check whether sector-canonical KPIs (from `sector_metrics.yaml`) have data in the vault:
- For each `importance: primary` KPI → search vault for evidence
- Report: "Sector KPI Coverage: X/Y primary KPIs have vault data"
- Flag missing primary KPIs as actionable research gaps

## `--deep` 模式：9 维度框架结构化输出

当用户使用 `/research TICKER --deep` 时：

1. 读取中央框架定义：
   ```python
   import yaml
   from pathlib import Path
   fw_path = Path.home() / ".claude" / "skills" / "shared" / "analysis_framework.yaml"
   with open(fw_path, encoding="utf-8") as f:
       framework = yaml.safe_load(f)
   ```
2. 执行正常的数据收集步骤（KB + web + NLM + 13F + supply chain）
3. 输出改为 9-section 结构，每个 section：
   - 使用 `key_questions` 作为研究引导
   - 使用 `data_source_mapping` 定向搜索对应数据源
   - 已回答的问题附来源标注
   - 未能回答的问题标记为 "❓ 待研究"
   - 末尾附 coverage confidence（High/Medium/Low/Gap）

**Sector-Enhanced S4 (Company & Financials):**
When generating S4 analysis in `--deep` mode, inject sector-canonical KPIs as mandatory investigation targets. For each primary KPI from `sector_metrics.yaml[sector].canonical_kpis`:
- Find the most recent value in vault (search `研究/财报分析/` for TICKER)
- Compare to sector `beat_miss_guide` thresholds
- Flag as "⚠️ Data Gap" if no vault data exists for a primary KPI
4. 报告最后附 Coverage Matrix 总结：
   ```
   ## 📐 Coverage Summary
   Score: 78% (6/9 covered, 2 partial, 1 gap)
   Gap: S5 管理层, Partial: S6 估值, S7 风险
   建议: /research TICKER "management incentives" 填补 S5
   ```
5. 保存到 `研究/研究笔记/{TICKER}_YYYY-MM-DD.md`（使用 9 维度标题结构）
