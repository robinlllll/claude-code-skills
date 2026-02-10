# PromptSpec

## Goal
Optimize the Devil's Advocate (pushback) prompt for the Socratic Writer skill. The current prompt produces surface-level, generic challenges. We need deep, specific, multi-layered pushbacks that genuinely stress-test investment theses and analytical arguments.

## 任务一句话
Given a user's evolving argument (topic + summary + Q&A dialogue), generate deep, specific, multi-layered adversarial challenges that expose hidden assumptions, logical gaps, and overlooked risks — at a level that would satisfy a skeptical fund manager.

## 输入
- 输入格式：Three text fields injected via `{topic}`, `{content}`, `{dialogue}`
  - `topic`: Short topic string (e.g., "PM Philip Morris ZYN growth thesis")
  - `content`: Session summary — the user's evolving argument
  - `dialogue`: Formatted Q&A history, each entry as `Q (type): ... / A: ...`
- 输入示例：
  ```
  主题：NVDA is overvalued relative to its AI infrastructure moat
  内容：NVDA's dominance in AI training GPUs is priced in at 35x forward earnings...
  问答历史：
  Q (clarification): What do you mean by "priced in"? ...
  A: The current multiple assumes continued 50%+ growth...
  Q (evidence): What data supports the 50% growth ceiling? ...
  A: Historical semiconductor cycles show...
  ```

## 输出
- 输出格式：Structured JSON with multi-layered challenges
- 输出示例：
  ```json
  {
    "challenges": [
      {
        "type": "假设质疑",
        "target_claim": "The exact user claim being challenged (quoted)",
        "surface_challenge": "The obvious pushback",
        "deeper_challenge": "The second-order implication the user probably hasn't considered",
        "steel_man_counter": "The strongest possible version of the opposing argument",
        "evidence_request": "What specific data would resolve this — be concrete (name the dataset, source, metric)",
        "historical_parallel": "A specific historical case where similar reasoning failed (with outcome)",
        "severity": "critical|major|minor"
      }
    ],
    "structural_critique": {
      "reasoning_pattern": "Name the reasoning pattern used (e.g., anchoring, survivorship bias, base rate neglect)",
      "missing_stakeholders": "Whose perspective is absent from this analysis?",
      "time_horizon_mismatch": "Does the argument confuse short-term and long-term dynamics?",
      "unfalsifiability_check": "Is there any evidence that would make the user change their mind? If not, the thesis is unfalsifiable."
    },
    "kill_scenario": "Describe ONE concrete, plausible scenario where this thesis is completely wrong — with specific trigger events and timeline",
    "confidence_calibration": {
      "devil_rating": 1-10,
      "weakest_link": "The single claim that, if wrong, collapses the entire argument",
      "suggested_bet": "If you believe this thesis, what falsifiable prediction would you make for the next 6 months?"
    }
  }
  ```

## 硬约束（必须满足）
- Every challenge MUST quote or reference a SPECIFIC claim from the user's dialogue — no generic pushbacks
- Must include at least one historical parallel with a concrete outcome (company name, year, what happened)
- The `steel_man_counter` must be genuinely strong — not a strawman dressed as steel
- The `kill_scenario` must be plausible (>5% probability), not a black swan fantasy
- Must identify the reasoning pattern/cognitive bias by name
- Output must be valid JSON parseable by Python's json.loads()
- Response in Chinese (中文)

## 软约束（尽量满足）
- Challenges should escalate in severity (start with minor, build to critical)
- Reference specific data sources the user could check (e.g., "check NVDA's capex/revenue ratio vs AMD's in 2018")
- Include cross-domain analogies when helpful (e.g., comparing tech moats to pharma patent cliffs)
- The `suggested_bet` should be genuinely falsifiable within 6 months
- 4-6 challenges is ideal (fewer than 3 is too shallow, more than 8 is noise)

## 必须避免
- Generic pushbacks that could apply to any thesis ("but what if the market crashes?")
- Challenges that only restate the user's own uncertainty ("you said you're not sure about X")
- Vague severity ratings without justification
- Strawman arguments labeled as "steel man"
- Recency bias in historical parallels (don't always cite 2020-2024 events)
- Challenge types that are just labels with no analytical substance
- Repeating the same challenge in different words

## 评估标准
1. **Specificity** (30%): Does every challenge reference a concrete claim, data point, or reasoning step from the user's input?
2. **Depth** (25%): Do challenges go beyond surface-level to reveal second-order implications and structural weaknesses?
3. **Actionability** (20%): Can the user actually respond to each challenge with research or reasoning? (vs. unfalsifiable philosophical objections)
4. **Intellectual honesty** (15%): Are the steel-man counters genuinely strong? Would a smart person on the other side actually make this argument?
5. **Structural analysis** (10%): Does the meta-analysis (reasoning patterns, kill scenario, calibration) add value beyond individual challenges?

## 测试用例
见 tests/ 目录
