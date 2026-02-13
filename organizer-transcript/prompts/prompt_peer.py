"""
Peer comparison prompt template for cross-company earnings transcript analysis.
Optimized via prompt-optimizer sessions 38f4ead41293 + 39a22c00e0f4.
v2: Shifted from financial-table-driven to competitive-intelligence-driven.
"""


def get_peer_prompt(
    companies: list[dict],
    quarter: str,
    focus_areas: str = "",
) -> str:
    """
    Generate peer comparison analysis prompt.

    Args:
        companies: List of dicts with 'ticker' and 'company' keys
                   e.g. [{"ticker": "GOOG-US", "company": "Alphabet"}, ...]
        quarter: Quarter label e.g. "Q4 2025"
        focus_areas: Optional user-specified focus areas

    Returns:
        Formatted prompt string for peer comparison analysis
    """
    # Build dynamic elements based on company count
    tickers = [c["ticker"] for c in companies]
    names = [c["company"] for c in companies]

    companies_str = " vs ".join(f"{c['company']} ({c['ticker']})" for c in companies)
    companies_list_str = "\n".join(
        f"   - {c['company']} ({c['ticker']})" for c in companies
    )

    # Table header and separator adapt to company count
    table_header = " | ".join(f"**{t}**" for t in tickers)
    table_separator = " | ".join(":---" for _ in tickers)

    # Focus areas section
    focus_areas_str = ""
    if focus_areas:
        focus_areas_str = f"\n5. **用户自定义关注点：** {focus_areas}\n"

    return f"""## 指令开始

### A. 分析目标与背景 (Input)

1. **对比分析：** {companies_str}，{quarter} 同季度横向对比
2. **公司列表：**
{companies_list_str}
3. **核心输入材料：** 每家公司的 {quarter} earnings call transcript（已上传）
4. **分析重点：** 聚焦这些公司直接竞争的业务领域，深入对比管理层叙事与分析师质疑，不是各家分别总结财务数据
{focus_areas_str}
---

### B. 分析输出要求 (Output Required)

**[关键指令：请不要在您的回复中重复A部分的任何内容。您的回复应直接从"1. 竞争业务版图"开始。]**

### C. 【必须遵守】关键输出规范 (Critical Output Rules)

- **格式要求：** 输出为结构化 Markdown 报告。
- **字数要求：** 报告总字数 5000-10000 字。2 家公司目标 5000-6000 字，3-4 家公司目标 7000-10000 字。
- **语言要求：** 报告主体为中文，专业术语（GAAP, EBITDA, YoY, FCF, CapEx, RPO 等）使用英文原文。
- **分析导向：** 这是竞争情报分析，不是财务报表横向对比。数据服务于竞争判断，而非报告主体。

**以下规则对输出质量至关重要，必须严格遵守：**

**1. 引用来源页码（最重要）：**
   - 每个关键数据点和管理层引述必须标注来源，格式：`(TICKER p.X)`
   - 多公司对比时，每个引用都标注是哪家公司的 transcript
   - 管理层原话引用使用引号 + 页码：`"原文" (TICKER p.X)`
   - 若某指标 transcript 未披露，标注 `N/A（未披露）`，禁止估算或编造

**2. 竞争对比优先，公司描述其次：**
   - 每个维度必须围绕"竞争关系"组织，不是"公司A财务、公司B财务"的拼接
   - 正确方式：先识别竞争领域，再在每个领域内对比所有公司的表现、管理层态度和分析师反应
   - 差异最大、竞争最激烈的领域应获得最长篇幅

**3. 必须有锋利的判断：**
   - 每个竞争领域必须有明确的"谁在赢/谁在输"的判断
   - 不允许出现"各有千秋"、"难以比较"等回避性结论
   - 判断必须基于数据 + 管理层言行 + 分析师反应三重证据

**4. 管理层叙事是核心：**
   - 不只是引用数字，更重要的是管理层怎么说、语气如何、回避了什么
   - 对比同一议题下不同管理层的措辞差异
   - 区分"主动披露"（prepared remarks）和"被动回应"（Q&A中被追问才说的）

**5. 数字规范：**
   - 增长率必须标注 YoY%
   - 增速变化方向必须标注：加速↑ / 减速↓ / 持平→
   - 利润率对比用绝对值 + 环比变化 (pp)

**6. 动态适应公司数量：**
   - 2 家公司：直接 A vs B 深度对比
   - 3 家公司：三方对比 + 排名
   - 4 家公司：象限分类（如"高增长高利润" vs "低增长低利润"）

**7. 竞争信息完整性：**
   - 不要遗漏 transcript 中管理层或分析师明确提及的任何竞争对手相关信息（包括不在本次对比中的公司）
   - 如果某家公司的 transcript 中提到了其他公司，务必引用并分析竞争意图

---

请根据上传的 transcript，生成一份结构化的跨公司竞争分析报告。报告必须包含以下全部 6 个部分：

#### 1. 竞争业务版图 (Competitive Business Map)

**A. 识别直接竞争领域：**

首先识别这些公司之间所有直接竞争的业务领域。例如：
- Cloud/AI 基础设施（如 Google Cloud vs AWS）
- 数字广告（如 Google Search/YouTube vs Meta Ads vs Amazon Ads）
- AI 应用/模型（如 Gemini vs Meta AI vs Bedrock）
- 其他重叠领域

**B. 竞争业务关键指标速览：**

针对每个竞争领域，列出关键指标对比表：

| [竞争领域名称] | {table_header} |
|:---|{table_separator}|
| 该业务营收 | [值+YoY%] (p.X) | [值+YoY%] (p.X) | ... |
| 增速方向 | 加速↑/减速↓ | ... | ... |
| 该业务利润率 | X% (p.X) | X% (p.X) | ... |
| 前瞻指标 (backlog/RPO) | [值] (p.X) | ... | ... |

**每个竞争领域用独立的表格。** 非竞争业务（如 Amazon 零售、Meta Reality Labs）仅在影响竞争格局时提及。

**C. 竞争态势一句话判断：**
- 每个竞争领域：谁在赢？基于什么证据？趋势在加速还是收窄？

---

#### 2. 管理层竞争叙事对比 (Management Competitive Narrative)

**这是报告最核心的部分，应占总篇幅 25-30%。**

**A. 共同议题叙事对比表：**

识别 4-6 个所有公司管理层都谈到的共同议题（如 AI 投入战略、CapEx 合理性、竞争定位、增长可持续性），逐一对比：

| 议题：[议题名称] | |
|:---|:---|
| **[TICKER A]** | "[管理层原话摘要]" (p.X) — 语气：[自信/谨慎/回避/激进]，场合：[prepared remarks/Q&A] |
| **[TICKER B]** | "[管理层原话摘要]" (p.X) — 语气：[自信/谨慎/回避/激进]，场合：[prepared remarks/Q&A] |
| **[TICKER C]** | "[管理层原话摘要]" (p.X) — 语气：[自信/谨慎/回避/激进]，场合：[prepared remarks/Q&A] |
| **一致之处** | [各家说法相同的部分是什么？] |
| **分歧之处** | [各家说法不同的部分是什么？] |
| **为什么不一致** | [是因为业务阶段不同？竞争位置不同？战略选择不同？还是有人在回避？] |

**对每个共同议题都必须完成上述对比。若某公司未涉及该议题，注明"该公司未在本季度讨论该议题"。**

**B. 管理层互相提及：**
- 如果某家管理层在 transcript 中直接或间接提到了其他公司（包括不在本次对比中的竞争对手），必须完整引用
- 分析这些提及背后的竞争意图

**C. 管理层"没说什么"：**
- 各家管理层刻意回避或轻描淡写的话题是什么？
- 回避本身说明了什么？

---

#### 3. 分析师关注点交叉验证 (Analyst Focus Cross-Check)

**A. 分析师共同关心的重点：**

找出被多家公司分析师同时关注的议题（如 AI CapEx 回报、竞争格局变化、利润率趋势），这些代表市场共识关注点：

| 共同关注议题 | {table_header} |
|:---|{table_separator}|
| [议题A] | 分析师怎么问 (p.X) → 管理层怎么答 (p.X) | 分析师怎么问 (p.X) → 管理层怎么答 (p.X) | ... |
| [议题B] | [同上格式] | [同上格式] | ... |

**B. 分析师质疑与 Push-back：**

| 公司 | 分析师最尖锐的质疑 | 管理层回应质量 |
|:---|:---|:---|
| [TICKER] | "[质疑摘要]" (p.X) | [直面回答/部分回避/完全回避] + 分析 |

**C. 各家独有的分析师关注点：**
- 只出现在某一家 Q&A 中的议题，说明什么？
- 市场对各家公司的核心担忧差异是什么？

**D. 分析师情绪温度：**
- 基于提问语气、追问频率、关注方向，判断分析师群体对各家公司的态度差异

---

#### 4. 竞争业务深度对比 (Competitive Segment Deep Dive)

针对第 1 部分识别的每个竞争领域，深入分析：

**对每个竞争领域重复以下结构：**

**[竞争领域名称]（如：Cloud/AI 基础设施）**

**A. 增长质量对比：**
- 各家该业务增速 + 加速/减速方向
- 有机增长 vs 并购贡献
- 前瞻指标（backlog、RPO、pipeline）对比
- 增速差异的核心驱动：为什么某家更快？是市场份额、产品周期、还是行业 tailwind？

**B. 盈利能力对比：**
- 该业务的利润率对比（如果 transcript 有 segment 数据）
- CapEx intensity 在该业务上的差异
- 可比性陷阱（一次性项目、会计口径差异、财年差异）

**C. 竞争优势判断：**
- "谁在这个领域更强？" — 必须给出明确判断
- 竞争优势是在扩大还是缩小？
- 1-2 个季度后谁更可能领先？

---

#### 5. 战略分歧与趋势判断 (Strategic Divergence & Trends)

**A. 战略优先级对比：**

| 公司 | 最强调的 3 件事 | 战略姿态 |
|:---|:---|:---|
| [TICKER] | 1.[事项] 2.[事项] 3.[事项] | 进攻/防守/转型 |

**B. 关键战略分歧：**
- 在哪些方面，各家选择了截然不同的路径？（如开源 vs 闭源、自研芯片 vs 买 NVIDIA、CapEx 激进 vs 保守）
- 这些分歧的根源是什么？（业务结构？竞争位置？管理层理念？）
- 谁的选择更可能被证明正确？

**C. 趋势外推：**
- 基于本季度的数据和管理层表态，各竞争领域的力量对比在未来 2-3 个季度可能如何演变？
- 哪些竞争领域的格局最可能发生变化？

---

#### 6. 投资决策启示 (Investment Implications)

**A. 综合竞争力排名：**

| 维度 | 排名（最优→最弱） | 关键证据 |
|:---|:---|:---|
| [竞争领域1] 竞争力 | [排名] | [一句话] |
| [竞争领域2] 竞争力 | [排名] | [一句话] |
| 增长动能 | [排名] | [一句话] |
| 管理层质量 | [排名] | [一句话] |
| **综合** | **[排名]** | |

**B. "如果只能买一家"：**
- 选择：[TICKER]
- 核心论据（3 点），每点必须结合竞争分析 + 管理层表态 + 数据支撑
- 最大风险：[风险描述]

**C. Pair Trade 逻辑（如适用）：**
- Long [TICKER A] / Short [TICKER B] 的理由
- 催化剂和时间框架

**D. 各家未来 1-2 个季度的关键催化剂：**

| 公司 | 催化剂 | 时间窗 | 方向 (+/-) | 来源 |
|:---|:---|:---|:---|:---|
| [TICKER] | [事件] | 0-3m | +/- | (p.X) |

**E. 风险对比：**
- 各家面临的最大竞争风险排名
- 哪些风险是行业共有的（系统性），哪些是个股独有的（特异性）

---

### D. Inline 研究问题规则 (Inline Research Questions)

**在分析正文中嵌入 3-5 个 `[?]` 研究问题，直接放在最相关的段落之后。** 不要集中放在文末或单独 section。

规则：
- 格式：`- [?] 问题内容`，独占一行，紧跟相关段落
- 问题来源：竞争格局中的关键不确定性、需要外部数据验证的对比假设、对投资决策有实质影响但 transcript 信息不足的领域
- 分散在不同 section 中（Section 1-6 各至少考虑是否需要），不要扎堆
- 问题应具体、可回答、有投资决策价值

---

## 指令结束
"""
