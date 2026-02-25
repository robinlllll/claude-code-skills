# /moc Output Templates & Examples

## Full MOC File Example (NVDA)

````markdown
---
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: moc
ticker: NVDA
aliases: [NVIDIA, 英伟达]
total_notes: 15
tags: [moc, NVDA]
---

# NVDA - Map of Content

> 跨 Vault 知识地图，自动生成于 YYYY-MM-DD，共找到 15 条相关笔记。

## 📊 投资论点 (Thesis)
- [[thesis]] - 核心投资逻辑 (PORTFOLIO) | 更新于 YYYY-MM-DD [Thesis]

## 📝 研究笔记 (研究/研究笔记)
- [[NVDA_2026-02-05]] - 深度研究，覆盖估值/竞争/风险 | 2026-02-05 [Vault]

## 📈 财报分析 (研究/财报分析)
- （无相关记录）

## 🎙️ 播客提及 (信息源/播客)
- [[The Hidden Economics Powering AI]] - a16z Show, AI基础设施经济学 | 2026-01-26 [Podcast]
- [[#407.拆解华为算力真相与中芯困局]] - 芯片出口管制复盘 | 2026-01-xx [Podcast]

## 📬 收件箱
- [[2026-01-25 - NVDA earnings preview]] - 财报前瞻 | 2026-01-25 [Vault]

## 🗓️ 周会讨论
- [[会议实录 2026-01-03]] - AI硬件/半导体偏多，存储股两周涨40% | 2026-01-03 [Meeting]

## 🏦 机构持仓 (13F)
- （无相关记录）

## 🇨🇳 雪球讨论 (信息源/雪球)
- （无相关记录）

## 📎 其他 (剪藏 / 思考 / 技术概念)
- （无相关记录）

## 📚 NotebookLM Q&A
- [[导航/NotebookLM/Oracle Cloud Unit Economics]] - Q: "What drives OCI margins?" | 2026-01-25 [NLM]
- （无相关记录）

## 🔗 Supply Chain Mentions
- TSM Q4 2025 财报提到 NVDA CoWoS 扩产 | 2025-12-15 [SC]
- AVGO Q3 2025 提到 NVDA networking 需求 | 2025-09-20 [SC]
- （无相关记录）

## 💬 ChatGPT Analysis History
- [[ChatGPT/Investment Research/2026-01-20 - NVDA估值讨论]] | 2026-01-20 [ChatGPT]
- （无相关记录）

## 📐 Framework Coverage View

| # | Section | Sources | Level |
|---|---------|---------|-------|
| S1 | 📈 Market & Growth | 4 (2p+2s) | ✅ |
| S2 | 🏟️ Competitive Landscape | 3 (2p+1s) | ✅ |
| S3 | 🏰 Barriers & Moat | 2 (1p+1s) | ⚠️ |
| S4 | 📊 Company & Financials | 5 (3p+2s) | ✅ |
| S5 | 👔 Management | 0 | ❌ |
| S6 | 💰 Valuation | 1 (0p+1s) | ⚠️ |
| S7 | ⚠️ Risks | 2 (1p+1s) | ⚠️ |
| S8 | 🎯 Investment Conclusion | 1 (1p+0s) | ⚠️ |
| S9 | 🔍 Research Gaps | 0 | ❌ |

Score: 56% | Gaps: S5 管理层, S9 研究盲区
→ Run `/research TICKER --deep` to fill gaps

---
<!-- USER NOTES -->
（用户手动添加的笔记保留在此处）
````

## Source Tag Placement Example

```markdown
### 研究笔记
- [[2025-01-15 - PM earnings Q4 analysis]] - 财报深度拆解 | 2025-01-15 [Transcript]
- [[2025-02-01 - PM ZYN growth thesis]] - ZYN 增长逻辑 | 2025-02-01 [Thesis]

### 机构持仓
- 19 institutional holders in Q4 2025 [13F]

### 供应链信号
- IQOS manufacturing expansion in Italy mentioned by STMicroelectronics [SC]

### 播客提及
- [[The Hidden Economics Powering AI]] - a16z Show | 2026-01-26 [Podcast]

### ChatGPT Analysis
- [[2026-01-20 - NVDA估值讨论]] - 估值模型对比 | 2026-01-20 [ChatGPT]

### 投资回顾
- 2025-Q4 review 中提到 PM 减仓决策 [Review]
```

## /moc list Output Example

```
已生成的 Map of Content (3 个)
============================

| Ticker/主题 | 相关笔记数 | 最后更新 |
|-------------|-----------|----------|
| NVDA | 15 | 2026-02-05 |
| UBER | 8 | 2026-02-04 |
| AI Infrastructure | 22 | 2026-02-03 |
```
