"""
Default prompt template for earnings transcript analysis.
Used for ChatGPT and as fallback.
This is the original prompt - do not modify.
"""

def get_default_prompt(company_name: str, ticker: str, curr: str, prev: str,
                       quarters_comparison: str, company_specific_notes: str = "") -> str:
    """Generate default analysis prompt (original template for ChatGPT)."""

    return f"""## 指令开始

### A. 分析目标与背景 (Input)

1. **公司与季度：** {company_name} ({ticker}), {quarters_comparison}

2. **核心输入材料 - 当前季度 (Current Quarter - {curr}):**
   - 已上传 earnings release 和 earnings transcript
   - [可选：粘贴当前季度的分析师一致预期 (Consensus Estimates)]

3. **核心输入材料 - 上一季度 (Previous Quarter - {prev}):**
   - 已上传 earnings release 和 earnings transcript
   - [可选：粘贴上一季度的分析师一致预期 (Consensus Estimates)]

4. **分析师问答分析和季度间对比是重点**
{company_specific_notes}
---

### B. 分析输出要求 (Output Required)

**[关键指令：请不要在您的回复中重复A部分的任何内容。您的回复应直接从"1. 综合评估与投资启示"开始。]**

请根据A部分两个季度的输入材料，生成一份结构化的对比分析报告。报告必须包含以下所有部分：

#### 1. 综合评估与投资启示 (Synthesis & Implications)

- **核心结论 (Key Takeaway)：** [综合对比{curr}和{prev}，总结本季度的核心结论...]
- **"Devil's Advocate" 视角：** [基于{curr}分析...]
- **对估值/模型的影响：** [基于{curr}分析...]

**A. 概率化情景（合计=100%）+ 价格影响区间**

| 情景 | 概率 | 关键假设/触发器 | 价格影响 | 验证指标 |
|:---|:---|:---|:---|:---|
| Bull | [__]% | ①[…] ②[…] ③[…] | +[]%–[]% | [指标A \\| 时间窗] |
| Base | [__]% | ①[…] ②[…] ③[…] | []%–[]% | |
| Bear | [__]% | ①[…] ②[…] ③[…] | −[]%–[]% | |

**B. 催化板 (Catalyst Board)**

| 时间窗 | 事件 | 概率(%) | 方向(+/−) | 验证数据/来源 | 备注 |
|:---|:---|:---|:---|:---|:---|
| 0–3m | [如：价格上调/招标结果] | []% | | | |
| 3–12m | [如：产线投产/监管落地] | []% | | | |
| >12m | [如：新市场准入] | [__]% | | | |

---

#### 2. 业绩概览 (Performance Snapshot) - [对比版]

**A. 当季业绩表现 (Current Quarter Performance)**

| 指标 | {curr} 报告值 | {prev} 报告值 | QoQ 变化 | {curr} YoY | {prev} YoY |
|:---|:---|:---|:---|:---|:---|
| 营收 | | | | | |
| 毛利率 | | | | | |
| 营业利润 | | | | | |
| EPS | | | | | |

**B. 未来业绩指引 (Forward-Looking Guidance)**

| 指引指标 | {curr}发布的新指引 | {prev}发布的旧指引 | 指引变动 | 斜率 (Slope) | 隐含下一季 |
|:---|:---|:---|:---|:---|:---|
| [FY营收] | | | | | |
| [FY EPS] | | | | | |
| [FY Capex] | | | | | |

*计算口径说明：*
- 斜率 (单位时间) = (新指引中点 − 旧指引中点) ÷ Δt；单位写 %/季 或 pp/季
- 隐含下一季 = FY 指引中点 − 已披露季度之和

---

#### 3. 核心业绩驱动 (Segment & Geographic Drivers)

**A. 数据口径与非GAAP调整：** [基于{curr}最新披露...]

**B. 按业务线 (By Segment):**
- [业务线 1]: {curr}表现: [...]。对比{prev}: [...]

**C. 按地域 (By Geography):**
- [地域 1]: {curr}表现: [...]。对比{prev}: [...]

---

#### 4. 管理层叙事演变 (Management Narrative Evolution)

| 方面 | {curr} 叙事重点 | {prev} 叙事重点 | 演变分析 |
|:---|:---|:---|:---|
| 战略优先级 | | | |
| 竞争定位 | | | |
| 资本配置 | | | |

---

#### 5. [本季]分析师Q&A透视 ({curr} Q&A Deep Dive)

**回应评分标准 (Response Scoring Standard):**
- 回应直接性 (Directness) [0–3]: 3=给数值/区间；2=给方向+量级；1=抽象/转移；0=未答
- 数据量 (Data Level) [0–3]: 3=具体数；2=区间/公式；1=仅定性；0=无新信息

**A. 关键主题识别:** [列出{curr} Q&A中的主要主题]

**B. 按主题分类的Q&A详细分析:**

*主题一：[主题名称]*

| 问题 | 分析师/机构 | 管理层回应摘要 | Directness | Data Level | 议题性质 |
|:---|:---|:---|:---|:---|:---|
| [问题摘要] | [姓名, 机构] | [回应摘要] | [0-3] | [0-3] | [短期建模/长期竞争力/合规与政策] |

---

#### 6. 季度间主题演变 (Thematic Evolution)

**A. Q&A主题量化对比:**

| 主题 | {curr} 问题数 | {curr} 占比 | {prev} 问题数 | {prev} 占比 | 趋势 |
|:---|:---|:---|:---|:---|:---|
| [主题A] | | | | | [升温/降温/新增] |
| [主题B] | | | | | [升温/降温/新增] |

**B. 关键议题回应演变:**

| 议题 | {prev}回应总结 | 评分 | {curr}回应总结 | 评分 | 变化分析 |
|:---|:---|:---|:---|:---|:---|
| [议题1] | | D/DL | | D/DL | |

---

#### 7. 前次 Insight 验证追踪 (Prior Insight Tracking)

**【条件性输出】仅在 A 部分提供了 "前次分析 Insights 跟踪" 时输出此 section。如果没有 prior insights，跳过此 section。**

**对每条 prior insight 逐一回应：**

| ID | Insight | 判定 | 本季度关键证据 | 建议操作 |
|:---|:---|:---|:---|:---|
| INS-XXX | [标题] | ✅/❌/⏳/🔄 | [transcript 中的具体证据 + 页码] | [结案/保持/修正为"..."] |

**判定标准：**
- ✅ 已验证：transcript 中有**明确、可引用的证据**支持该假设。**必须附带页码引用，否则禁止判定为 ✅。**
- ❌ 推翻：transcript 中有明确证据否定该假设
- ⏳ 证据不足：本次 transcript 未涉及或证据不明确。**这是默认判定——当你犹豫时，选 ⏳ 而非 ✅。**
- 🔄 需修正：假设方向正确但需要更新细节（如时间线、幅度）

**对每条 🔄 修正的 insight，给出建议的修正后表述。**
**对每条 ❌ 推翻的 insight，提炼一条教训（lesson learned）。**

**注意：此 section 的判定仅为 AI 建议。最终状态更新由分析师手动完成。**

---

## 指令结束
"""
