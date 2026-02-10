# PromptSpec

## Goal
Conference transcript analysis prompt — extract incremental updates vs last earnings call, strategic signals, investment-relevant info under CFA 9-section framework

## 任务一句话
分析投资者会议 transcript（UBS、Goldman、Barclays 等），提取相对最近一季财报电话会的增量信息、战略信号和投资决策相关要点。

## 输入
- 输入格式：1份会议 transcript PDF + 公司/ticker/会议名/日期/最近财报季度 + [可选] 公司特定注意事项 + [可选] earnings call 原文（用于精确增量对比）
- 输入示例：KKR UBS Financial Services Conference 2026-02-09 transcript PDF，参考季度 Q4 2025 earnings call

## 输出
- 输出格式：结构化 markdown briefing（中文），800-1500字，含页码引用
- 输出示例：增量数据表 + 战略信号 + 框架映射 + Q&A亮点 + 行动建议

## 硬约束（必须满足）
- H1: 增量优先 — 只提取相对最近 earnings call 的新信息/不同信息，不复述已知内容
- H2: 来源引用 — 每个事实性陈述必须标注来源位置：有页码时用 `(p.X)`，无页码时统一用位置描述。全文必须使用同一种引用方式
- H3: 框架映射 — 每个 insight 映射到 9-section 分析框架 (S1-S9)
- H4: 数据精确 — 禁止使用约数（"~"、"大约"），使用 transcript 原始数字
- H5: 中文输出 — 分析内容用中文，技术术语可保留英文
- H6: 会议情境 — 注明受众(sell-side/buy-side/industry)、主持人，分析如何影响管理层表述
- H7: 信号检测 — 明确识别管理层语气/重点相对 earnings call 的变化
- H8: 决策导向 — 必须以"对投资论文的影响"和"需要跟踪的变量"结尾

## 软约束（尽量满足）
- S1: 识别"脱稿时刻" — 管理层超出准备发言的即兴回答
- S2: 标注听众反应（如有）
- S3: 标记首次披露的数据点（earnings call 未出现过的）
- S4: 对比管理层回答的定量vs定性程度
- S5: 识别主持人问了但 earnings call 分析师没问的问题
- S6: 注意是否派出不同高管出席（战略优先级信号）
- S7: 跟踪竞争对手提及（公司名、产品、技术）

## 必须避免
- A1: 不要复制 earnings analysis 的完整结构（详细Q&A逐条表、完整财务模型更新等）— 这是轻量级增量 briefing，section 数量和名称应与 earnings analysis 明显不同
- A2: 不要编造数据或用假设填充空白
- A3: 不要使用泛泛语言（"管理层很积极"）— 必须量化或引用原文
- A4: 不要忽略会议情境（房间里的人决定了说什么）
- A5: 不要把会议等同于财报 — 这是补充情报
- A6: 不要使用 emoji

## 评估标准
- E1 (30%): 增量价值 — 分析是否提供了仅读 earnings call 会遗漏的信息？
- E2 (20%): 精确性 — 所有数据点是否精确且有页码引用？
- E3 (15%): 框架覆盖 — insights 是否映射到 9-section 框架？
- E4 (15%): 简洁性 — 是否比 earnings analysis 适当精简？
- E5 (20%): 决策效用 — PM 读完能否立刻知道什么变了？

## 测试用例
见 tests/ 目录
