"""
Podcast deep analysis prompt template (Tier 2).

Produces investment-grade analysis from podcast transcripts,
cross-referenced with active theses, 13F holdings, and vault research.
7 sections adapted from the earnings transcript analysis framework.

v2: Enhanced via prompt-optimizer review (session 04758d6cf683).
Changes from v1:
  - Added bilingual handling rule (H9)
  - Added graceful degradation for empty portfolio context (H10)
  - Added "all 7 sections mandatory" guard with fallback for thin content (H3)
  - Added explicit "probabilities must sum to 100%" constraint (H5)
  - Added ticker prioritization for 5+ tickers (edge case)
  - Added speaker bias taxonomy (S4)
  - Added quote selection criteria (S5)
  - Added "信息增量" test — every paragraph must add value beyond restating podcast
  - Added anti-hallucination reminder at section boundaries
  - Added "CONFLICTING = highest priority" escalation rule
"""


def get_podcast_prompt(
    podcast_name: str,
    episode_title: str,
    episode_date: str,
    tickers_detected: list[str],
    portfolio_context: str = "",
    holdings_context: str = "",
    research_context: str = "",
) -> str:
    """Generate the Tier 2 deep analysis prompt for a podcast episode.

    Args:
        podcast_name: Name of the podcast show
        episode_title: Episode title
        episode_date: Publication date (YYYY-MM-DD)
        tickers_detected: List of ticker symbols found in content
        portfolio_context: Active thesis summaries for detected tickers
        holdings_context: 13F one-liner summaries for detected tickers
        research_context: Recent vault notes mentioning detected tickers

    Returns:
        Formatted prompt string for Claude to analyze the podcast
    """

    tickers_str = ", ".join(tickers_detected) if tickers_detected else "None detected"
    ticker_count = len(tickers_detected)

    # Build portfolio context block with graceful degradation
    context_block = ""
    has_portfolio_ctx = bool(portfolio_context or holdings_context or research_context)

    if has_portfolio_ctx:
        context_block = "\n### 组合上下文 (Portfolio Context)\n"
        if portfolio_context:
            context_block += f"\n**Active Theses:**\n{portfolio_context}\n"
        if holdings_context:
            context_block += f"\n**13F Institutional Holdings:**\n{holdings_context}\n"
        if research_context:
            context_block += f"\n**Recent Research Notes:**\n{research_context}\n"

    # Conditional rules based on available context
    no_ctx_note = ""
    if not has_portfolio_ctx:
        no_ctx_note = """
**【组合上下文缺失】：** 未提供 thesis/13F/研究笔记数据。请：
   - Section 2 Ticker 分析中，Thesis 对齐统一标注"无现有 thesis"，跳过"当前 thesis"和"13F 信号"行
   - Section 7 Action Flags 仅基于播客内容本身的信号强度，不做 thesis 对齐判断
   - 将更多分析精力放在 Section 1（综合评估）、3（竞争格局）、4（嘉宾可信度）
"""

    # Ticker prioritization rule for high-count episodes
    ticker_priority_rule = ""
    if ticker_count > 5:
        ticker_priority_rule = f"""
**【Ticker 优先级】：** 检测到 {ticker_count} 个 tickers，数量较多。请：
   - Section 2 中，优先详细分析有 thesis 数据或 13F 数据的 ticker（完整表格）
   - 其余 ticker 合并为一个"其他提及"小节，每个用 1-2 句话概括播客论点
   - Section 7 Action Flags 仍需覆盖所有 ticker
"""

    return f"""## 指令开始

### A. 分析目标与背景 (Input)

1. **播客信息：** {podcast_name} — "{episode_title}" ({episode_date})
2. **检测到的 Tickers ({ticker_count})：** {tickers_str}
3. **核心输入材料：** 已提供的播客全文（Summary, Takeaways, Q&A, Transcript 等 sections）
4. **组合数据状态：** {"已注入" if has_portfolio_ctx else "未提供（仅基于播客内容分析）"}
{context_block}
---

### B. 分析输出要求 (Output Required)

**[关键指令：请不要在回复中重复 A 部分的内容。直接从"1. 综合评估与投资启示"开始。]**

**[所有 7 个 section 必须出现在输出中。如果某个 section 的相关内容在播客中确实很少，用 2-3 句话说明"播客未深入讨论此维度"并给出你基于有限信息的初步判断，不要留空或跳过。]**

---

### C. 【必须遵守】关键输出规范 (Critical Output Rules)

**1. 引用来源标注（最重要）：**
   - 每个关键论点必须标注来源，格式：`[来源: Summary]`、`[来源: Takeaway #N]`、`[来源: Q&A]`、`[来源: Transcript]`
   - 不要笼统引用，尽量定位到具体 section 和条目编号
   - 如果一个论点综合了多个来源，列出所有相关来源：`[来源: Summary + Takeaway #3]`

**2. 强调"变化"而非"状态"：**
   - 重点是播客讨论了"什么在变"，而不是"现在是什么"
   - 使用变化语言：加速/减速/转折/恶化/改善/新出现/突破/见顶
   - 对比语言示例："+17% YoY vs 上季度 +15% YoY → 增长加速"
   - 投资回报来自变化，不来自静态优势。"X公司市占率30%"是状态；"X公司市占率从25%升至30%"是变化
   - 对于每个论点，问自己："这个信息的增量价值是什么？比上次我们知道的多了什么？"

**3. 投资决策导向：**
   - 用"你需要..."或"模型必须..."的语气，像在给分析师同事写备忘录
   - 每个论点要回答"so what?"——这对持仓/估值/决策有什么影响？
   - 不要停留在"信息概括"层面，必须推进到"投资启示"层面

**4. Devil's Advocate 必须量化：**
   - 列出的风险必须有具体来源引用
   - 尽量附上可验证的数据锚点，不要空泛的"可能下行"
   - 格式示例："如果 [条件]（嘉宾预测 X，但 [反面证据]），则 [具体影响]"

**5. 详细且有深度：**
   - 不要追求简洁，要追求完整和深度
   - 输出风格应该像"投行研究备忘录"而非"新闻摘要"
   - 如果播客中没有明确数据，直接写"未提及"而不是推测
   - 严禁凭空捏造播客中不存在的数据点或引用

**6. Thesis 对齐检查：**
   - 对于每个检测到的 ticker，判断播客内容与现有 thesis 的关系：
     * **ALIGNED** — 支持当前 thesis 方向
     * **CONFLICTING** — 与 thesis 矛盾，需要关注 ⚠️ **CONFLICTING 的 ticker 必须在 Section 7 标为 🔴 WARNING，这是最高优先级信号**
     * **NEW INFO** — thesis 未覆盖的新信息，需要评估
   - 如果无 thesis 数据，标注"无现有 thesis"

**7. 语言规则：**
   - 分析报告统一使用中文撰写（section 标题保留中英对照）
   - 引用原文时保持原文语言（英文播客引用英文原文，中文播客引用中文原文）
   - 专有名词/ticker/公司名保持英文
{no_ctx_note}{ticker_priority_rule}
---

请根据 A 部分的播客内容，生成一份结构化的投资分析报告。**报告必须包含以下所有 7 个部分，不可跳过任何一个。**

---

#### 1. 综合评估与投资启示 (Synthesis & Investment Implications)

- **核心结论：** 按以下维度结构化拆解（每个维度都需要具体数据/论点 + 来源标注）：
  * **增长叙事**：播客中讨论的主要增长驱动力是什么？哪些在加速/减速？[来源标注]
  * **盈利/估值影响**：讨论内容对相关公司的盈利路径或估值框架有什么影响？[来源标注]
  * **风险信号**：嘉宾提到或暗示了哪些下行风险？这些风险可验证吗？[来源标注]

- **投资启示（决策导向）：** 综合分析，用一段话总结"偏多信号"和"风险升级"两方面。结尾必须回答："基于此播客，你的下一步行动应该是___"

- **Devil's Advocate 视角：** 基于播客内容，列出 2-3 个核心风险点：
  - 每个都必须引用具体来源
  - 格式："如果 [嘉宾假设] 不成立（反面证据：[数据/逻辑]），则 [对持仓的具体影响]"

- [?] 基于综合评估，最需要验证的核心假设是什么？

- **概率化情景（三者概率必须加总 = 100%）+ 影响评估**

| 情景 | 概率 | 关键假设/触发器 | 影响方向 | 验证指标 |
|:---|:---|:---|:---|:---|
| Bull | [__]% | ①[...] ②[...] | 正面 | [指标 + 时间窗] |
| Base | [__]% | ①[...] ②[...] | 中性 | [指标 + 时间窗] |
| Bear | [__]% | ①[...] ②[...] | 负面 | [指标 + 时间窗] |

---

#### 2. Ticker 深度分析 (Per-Ticker Deep Dive)

对每个检测到的 ticker 独立分析。**如果 ticker 与现有 thesis CONFLICTING，排在最前面分析。**

**[TICKER]** — Thesis 对齐：[ALIGNED / CONFLICTING / NEW INFO / 无现有 thesis]

| 维度 | 内容 |
|:---|:---|
| 播客论点 | 嘉宾/主持人对该公司说了什么？关键数据点？[来源标注] |
| 变化信号 | 相比市场共识或此前认知，什么在变？加速/减速/转折/无变化 |
| 当前 thesis | 现有 thesis 的核心观点（如有；无则写"无现有 thesis"） |
| 13F 信号 | 机构持仓动态（如有；无则写"无数据"） |
| 投资启示 | 需要更新模型/thesis 的具体地方，或者"无需调整" |

- [?] 针对该 ticker 的后续研究问题（具体、可回答、有投资决策价值）

---

#### 3. 竞争格局 (Competitive Dynamics)

**即使播客未直接讨论竞争，也请基于播客内容推断隐含的竞争格局影响（标注为推断）。如果确实无法推断，写"播客未涉及竞争格局讨论，无法合理推断"。**

| 受益方 | 受损方 | 核心逻辑 | 信息来源 | 来源 |
|:---|:---|:---|:---|:---|
| [公司/行业] | [公司/行业] | [为什么] | 直接讨论/推断 | [来源标注] |

**份额变化方向分析：** 重点关注增量份额流向（delta），不是存量份额大小（level）。谁在赢得增量份额 = 谁的竞争力在上升。存量份额大但被蚕食的 incumbent 应排在份额加速增长的 challenger 之后。

---

#### 4. 嘉宾叙事与可信度 (Speaker Credibility & Narrative)

- **嘉宾背景：** 谁在说？其行业地位和潜在偏见
  - 常见偏见类型供参考：卖方分析师（talking their book）、VC投资人（pump portfolio companies）、公司管理层（overly optimistic）、独立研究员（可能缺少一手数据）、行业记者（偏叙事驱动）
- **叙事框架：** 嘉宾构建了怎样的故事？强调了什么？有没有过度简化复杂问题？
- **回避分析：** 有没有明显避开的话题或不愿量化的领域？被问到但未正面回答的问题？
- **可信度评估：** 论点是基于数据/一手经验，还是二手叙事/推测？可信度评级：高/中/低
- [?] 嘉宾观点中最需要独立验证的核心假设是什么？

---

#### 5. 关键引用与数据点 (Key Quotes & Data Points)

**关键引用（原文，保持播客原始语言）：**

选取标准：只选对投资决策有直接影响的引用——能改变你对某只股票看法、揭示非共识信息、或量化关键趋势的引用。不选泛泛而谈的行业观点。

> "引用内容" [来源: Section]

> "引用内容" [来源: Section]

（选取 3-5 条最有投资价值的原文引用）

**数据点汇总（仅限播客中明确提到的数据，严禁捏造）：**

| 数据点 | 数值 | 背景/对比 | 投资意义 | 来源 |
|:---|:---|:---|:---|:---|
| [指标] | [数字] | [同比/环比/行业对比] | [so what?] | [来源标注] |

---

#### 6. 催化剂与时间窗 (Catalysts & Time Horizons)

| 时间窗 | 事件 | 相关 Ticker | 方向(+/-) | 验证指标 | 来源 |
|:---|:---|:---|:---|:---|:---|
| 0-3m | [事件] | [TICKER] | [+/-] | [怎么验证 + 数据源] | [来源标注] |
| 3-12m | [事件] | [TICKER] | [+/-] | [怎么验证 + 数据源] | [来源标注] |
| >12m | [事件] | [TICKER] | [+/-] | [怎么验证 + 数据源] | [来源标注] |

- [?] 最近的催化剂事件中，哪个对当前持仓影响最大？需要什么数据来验证？

---

#### 7. Portfolio Action Flags

对每个相关 ticker 给出明确的行动信号（**CONFLICTING 的 🔴 WARNING 排在最前面**）：

- 🔴 **WARNING: [TICKER]**: [Conflicts with thesis — 具体矛盾点 + 建议下一步]
- 🟢 **[TICKER]**: [thesis reinforced — 具体原因 + 是否需要更新目标价]
- 🟡 **NEW: [TICKER]**: [Consider researching — 为什么值得关注 + 建议起始研究方向]
- ⚪ **MONITOR: [主题/指标]**: [需要持续跟踪的信号 + 触发条件]

**新研究线索：** 播客中提到但当前组合未覆盖的投资机会（如有）。每条线索附上"值得深入的理由"和"初步研究切入点"。

---

### D. Inline 研究问题规则 (Inline Research Questions)

**在分析正文中嵌入 3-5 个 `[?]` 研究问题，分散在不同 section 中（Section 1-6 各处，不要集中在一个 section）。**

规则：
- 格式：`- [?] 问题内容`，独占一行，紧跟最相关的段落之后
- 问题来源优先级：
  1. 嘉宾回避/未充分回答的关键问题
  2. 需要外部数据验证的定量假设（如增长率、市占率、成本结构）
  3. 对投资决策有价值但播客信息不足的领域
- 好的 [?] 示例：`- [?] 嘉宾称 AI inference 成本每 7 个月减半，TrendForce/SemiAnalysis 的数据是否验证？`
- 坏的 [?] 示例：`- [?] AI 行业未来会怎样？`（太宽泛，无法回答）

---

## 指令结束
"""
