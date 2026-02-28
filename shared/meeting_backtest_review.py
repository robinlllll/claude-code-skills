"""
Meeting Backtest Review: Time-period comparison + Multi-AI evaluation.
Sends backtest results to GPT and Gemini for independent review.
"""
import json
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── API Keys ──────────────────────────────────────────────
CHATGPT_CONFIG = Path.home() / ".claude" / "skills" / "chatgpt" / "data" / "config.json"

def load_keys():
    keys = {}
    if CHATGPT_CONFIG.exists():
        with open(CHATGPT_CONFIG, "r", encoding="utf-8") as f:
            keys["openai"] = json.load(f).get("openai_api_key", "")
    keys["gemini"] = os.environ.get("GEMINI_API_KEY", "")
    if not keys["gemini"]:
        cfg_path = Path.home() / ".claude" / "skills" / "prompt-optimizer" / "data" / "config.json"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                keys["gemini"] = json.load(f).get("GEMINI_API_KEY", "")
    return keys

# ── Backtest Summary (updated from 2026-02-25 run v3 — parser fix + summary table validation) ──
BACKTEST_SUMMARY = """
# 周会选股回测结果 (2026-02-25, v3 修复版)

## 概况
- **周会数:** 49场 (2025-01-25 至 2026-02-21)
- **总提及:** 766次，231只不同股票
- **执行率:** 32% (246/766)
- **v3变更:** 修复了情绪分类器。新增摘要表验证层（一句话汇报摘要表作为权威来源覆盖关键词假阳性），
  支持H3/H4节标题，level-aware section boundary。影响全部49场会议。
- **vs v2:** BULLISH 248→229, BEARISH 214→254, NEUTRAL 78→104, UNKNOWN 208→179。
  分类更准确后组间差异扩大，信号更纯。

## 核心结果 (原始收益)

| 组别 | N | 7d均值 | 30d均值 | 30d中位 | 30d胜率 | 90d均值 | 180d均值 |
|------|---|--------|---------|---------|---------|---------|----------|
| 看多+已执行 | 96 | 0.8% | 2.7% | 2.7% | 62% | 7.0% | 12.2% |
| 看多+仅讨论 | 133 | 1.8% | 4.5% | 2.7% | 64% | 7.0% | 15.5% |
| 看空+已执行 | 67 | 0.2% | 2.9% | 1.4% | 61% | 4.3% | 8.8% |
| 看空+仅讨论 | 187 | 0.1% | 1.1% | 0.7% | 53% | 2.1% | 14.4% |
| 中性/未知 | 283 | 0.0% | 1.4% | 0.6% | 54% | 4.6% | 13.1% |

## SPY-Adjusted 超额收益

| 组别 | 7d超额 | 30d超额 | 90d超额 | 180d超额 |
|------|--------|---------|---------|----------|
| 看多+已执行 | -0.3% | +0.1% | -1.1% | -4.2% |
| 看多+仅讨论 | +1.6% | +3.7% | +2.6% | +3.2% |
| 看空+已执行 | -0.1% | +1.1% | -1.5% | -4.4% |
| 看空+仅讨论 | -0.2% | -0.6% | -3.1% | +1.9% |

## ★ 分时段对比 (旧42场 vs 新4场)

新期4场会议(01-16, 01-23, 01-31, 02-21)的74条picks。

| 组别 | 旧期N | 旧期30d | 新期N | 新期30d | 新期30d胜率 | 解读 |
|------|-------|---------|-------|---------|------------|------|
| 看多+已执行 | 90 | 3.1% | 6 | **-10.2%** | 33% | 新期踩雷 |
| 看多+仅讨论 | 127 | 4.4% | 6 | **+10.2%** | 100% | 没买的全涨 |
| 看空+已执行 | 57 | 3.5% | 10 | **-5.9%** | 0% | 看空持仓全跌 |
| 看空+仅讨论 | 174 | 1.6% | 13 | **-13.6%** | 0% | 空头判断极准 |

### 新期逐条重点

**看多+已执行 (踩雷):**
- SLM: -28.1%, SCHW: -8.9%, META: N/A (太新)
- TSM: +6.4% (唯一确认正收益)

**看多+仅讨论 (错过):**
- MU: +10.2%, CMCSA: +6.8%, AAPL: +1.8%

**看空+仅讨论 (精准空头):**
- COIN: -31.2%, MC.PA: -14.9%, ADBE: -12.0%, NFLX: -11.7%, GOOGL: -8.5%, INTC: -3.2%
- 空头判断准确率接近100%

### 新期核心发现
1. **空头判断能力极强:** 新期看空的13条discussed picks平均-13.6%，胜率100%
2. **多头执行选择有问题:** 看多的6条acted picks中多数亏损，而未买的全涨
3. **仓位惯性假说:** 持仓决策可能受已有仓位影响，而非跟随最新会议共识

## Alpha 衰减曲线 (超额收益 vs SPY)

| 持有期 | 看多+已执行 | 看多+仅讨论 | 看空+已执行 | 看空+仅讨论 |
|--------|------------|------------|------------|------------|
| 1天 | -0.0% | 0.1% | -0.1% | -0.2% |
| 7天 | -0.3% | 1.6% | -0.1% | -0.2% |
| 14天 | 0.2% | 1.9% | -0.4% | -0.2% |
| 30天 | 0.1% | 3.7% | 1.1% | -0.6% |
| 45天 | 1.4% | 3.0% | 1.1% | -1.5% |
| 90天 | -1.1% | 2.6% | -1.5% | -3.1% |
| 180天 | -4.2% | 3.2% | -4.4% | 1.9% |
| 270天 | -11.0% | 2.8% | -5.9% | 6.4% |
| 365天 | -9.4% | 1.3% | -10.9% | 1.9% |

## 入场点敏感性 (30天)

| 组别 | T+0 | T+1 | T+2 |
|------|-----|-----|-----|
| 看多+已执行 | 2.7% | 3.1% | 3.3% |
| 看多+仅讨论 | 4.5% | 3.9% | 4.1% |

看多+已执行组 T+2 > T+0，延迟入场更好。

## Regime 分析

| Regime | 多头30d超额 | 空头30d超额 |
|--------|------------|------------|
| SPY > 50D MA | 2.3% | -0.1% |
| SPY < 50D MA | 1.2% | -1.6% |
| VIX Low (<16.9) | 2.3% | -0.3% |
| VIX High (>16.9) | 1.5% | -0.2% |

## 统计检验

- **Placebo Test:** 30d超额在第65百分位，弱信号
- **OOS:** 训练期超额 0.8%，测试期 -0.3% → OOS仍为负但差距缩小
- **行业归因 (30d):**
  - 看多+已执行 vs SPY +0.1%, vs 行业ETF -0.3% → 个股选择为负
  - 看多+仅讨论 vs SPY +3.7%, vs 行业ETF +2.9% → 未执行组有明确alpha
- **信号一致性:**
  - 一致看多 (≥60%): 30d超额 1.8%
  - 一致看空: 30d超额 -0.8%
  - 多空反复: 0.4%
  - 仅提一次: -0.3%

## 止损止盈模拟

- **最优规则:** 持有45天，超额从0.1%→1.4%，胜率69%
- **止损有害:** 所有止损规则使超额恶化
- **止盈有害:** 所有止盈规则使超额恶化

## 行业拆解 (看多 30d vs SPY)

| 行业 | N | vs SPY | vs 行业ETF |
|------|---|--------|-----------|
| 半导体 | 28 | +7.1% | +2.5% |
| 金融 | 20 | +4.5% | +5.2% |
| 中概 | 30 | +2.3% | +1.0% |
| 科技 | 8 | +1.8% | +0.9% |
| 住房/建材 | 9 | +0.5% | +1.7% |
| 通信/媒体 | 25 | -0.1% | -0.7% |
| 可选消费 | 22 | +0.2% | +0.8% |
| 必选消费 | 12 | -0.3% | +2.5% |
| 奢侈品 | 4 | -1.8% | -5.5% |
| 工业 | 2 | -4.7% | -1.5% |

## v2→v3 关键变化

| 指标 | v2 (旧parser) | v3 (修复后) | 变化方向 |
|------|--------------|------------|---------|
| 看多+仅讨论 30d超额 | +2.6% | **+3.7%** | 信号更强 |
| 看空+仅讨论 30d超额 | -0.0% | **-0.6%** | 空头信号变有效 |
| NEUTRAL 分类数 | 78 | **104** | +33% |
| UNKNOWN 分类数 | 208 | **179** | -14% |
| Placebo百分位 | 38% | **65%** | 好转 |

分类精度提升后，看多+仅讨论组alpha从+2.6%升至+3.7%，是回测中最强信号。

## 背景信息

这是一个long-biased hedge fund的每周投资例会回测。一位PM每周讨论10-20只股票。
回测时间跨度约13个月(2025-01-25至2026-02-21)，49场会议，766条picks。
v3修复了情绪分类器：摘要表验证层修复了大量假阳性(如"利好已反映"被误判为看多，
"低端消费承压"被误判为看空)。修复后组间收益差异扩大，信号纯度提升。
核心结论：
1. **看多+仅讨论组是唯一有稳健alpha的组** (30d超额+3.7%, T+7至T+45均为正)
2. **执行层面摧毁价值** (看多+已执行 30d超额仅+0.1%)
3. **空头判断在新期极准** (13条discussed空头平均-13.6%)
4. 分类修复后Placebo从38%→65%，alpha边际好转但仍不显著
"""

PROMPT_TEMPLATE = """你是一位资深量化投资分析师。请对以下周会选股回测结果进行独立、严谨的评价。

{summary}

## 请回答以下问题（中文）

1. **Alpha 评估:** 基于所有统计证据，你认为这个PM的周会讨论是否有真正的选股alpha？概率估计？

2. **最令人震惊的发现:** 本次回测中最反直觉或最值得警惕的发现是什么？

3. **执行反转的诊断:** 上次"已执行"组优于"仅讨论"组，本次完全反转。你认为最可能的原因是什么？（提出2-3个假设）

4. **270d/365d 窗口新发现:** 新增的长窗口数据揭示了什么？"看空+仅讨论"组在270d/365d大幅跑赢是否说明空头判断在长期是对的？

5. **行业 vs 选股:** Alpha几乎全部来自行业配置而非个股选择。这对PM的投资流程意味着什么？

6. **可执行的改进建议:** 给出 3 条具体、可量化的行动建议（参数级别，如"持有期从30天改为X天"）。

7. **与上次回测的结论对比:** 上次CRO五条整改令（关停做空、T+2入场T+45退出、三次确认过滤、集中度限额、均线熔断）在新数据下是否仍然成立？哪些需要修改？

8. **元问题:** 这个回测框架本身是否有盲点或方法论缺陷？如何改进？

请尽量用数据支撑你的观点。每个问题回答 3-5 句话。
"""

def call_gpt(keys, prompt):
    from openai import OpenAI
    client = OpenAI(api_key=keys["openai"])
    print("  [GPT] Sending to gpt-5.2-chat-latest...")
    resp = client.chat.completions.create(
        model="gpt-5.2-chat-latest",
        messages=[
            {"role": "system", "content": "你是一位资深量化投资分析师和CRO（首席风控官），擅长回测诊断和alpha评估。请用中文回答，直言不讳，不需要客套。"},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=4000,
    )
    text = resp.choices[0].message.content
    print(f"  [GPT] Done ({len(text)} chars)")
    return text

def call_gemini(keys, prompt):
    from google import genai
    client = genai.Client(api_key=keys["gemini"])
    print("  [Gemini] Sending to gemini-3-pro-preview...")
    resp = client.models.generate_content(
        model="gemini-3-pro-preview",
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction="你是一位资深量化投资分析师和CRO（首席风控官），擅长回测诊断和alpha评估。请用中文回答，直言不讳，不需要客套。",
            temperature=0.7,
            max_output_tokens=4000,
        ),
    )
    text = resp.text
    print(f"  [Gemini] Done ({len(text)} chars)")
    return text

def main():
    print("=" * 60)
    print("  周会回测评审 (Multi-AI Review)")
    print("=" * 60)

    # Load API keys
    keys = load_keys()
    missing = []
    if not keys.get("openai"):
        missing.append("OpenAI")
    if not keys.get("gemini"):
        missing.append("Gemini")
    if missing:
        print(f"  WARNING: Missing API keys: {', '.join(missing)}")

    prompt = PROMPT_TEMPLATE.format(summary=BACKTEST_SUMMARY)

    # Run both in parallel
    results = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {}
        if keys.get("openai"):
            futures[executor.submit(call_gpt, keys, prompt)] = "GPT"
        if keys.get("gemini"):
            futures[executor.submit(call_gemini, keys, prompt)] = "Gemini"

        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                print(f"  [{name}] ERROR: {e}")
                results[name] = f"[Error: {e}]"

    # Write output report
    output_path = Path.home() / "Documents" / "Obsidian Vault" / "写作" / "投资回顾" / "2026-02-25_meeting_backtest_ai_review.md"

    lines = [
        "---",
        "date: 2026-02-25",
        "type: backtest-review",
        "tags: [backtest, meeting-picks, multi-ai, review]",
        "models: [gpt-5.2, gemini-3-pro]",
        f"related: \"[[2026-02-25_meeting_backtest]]\"",
        "---",
        "",
        "# 周会选股回测 — AI 交叉评审 (2026-02-25)",
        "",
        "> 将最新回测结果发送给 GPT-5.2 和 Gemini 3 Pro，各自独立评价。",
        "> 对比上次回测 (42场, 2026-02-08) vs 本次 (49场, 2026-02-25)。",
        "",
    ]

    for name in ["GPT", "Gemini"]:
        if name in results:
            lines.append(f"## {name} 评价")
            lines.append("")
            lines.append(results[name])
            lines.append("")

    # Cross-model synthesis
    if len(results) >= 2:
        lines.append("## 交叉对比")
        lines.append("")
        lines.append("> 以下由 Claude 基于两份独立评审进行综合。")
        lines.append("")
        lines.append("（待 Claude 补充综合分析）")
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n  Report saved to: {output_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
