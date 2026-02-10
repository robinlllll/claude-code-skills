---
name: plan
description: 为复杂功能生成结构化 markdown 计划文件。包含 TLDR、关键决策、任务拆解、状态跟踪。输出到 Obsidian，可被不同模型（Claude、Gemini、GPT）执行。
---

# Plan - 结构化计划生成器

为复杂功能或项目生成结构化的 markdown 计划文件。设计用于多模型执行场景，确保任何 AI 都能接手执行。

## When to Use This Skill

Trigger when user:
- 说"帮我规划"、"做个计划"、"拆解任务"
- 开始一个复杂功能开发，需要先规划
- 需要跟踪多个任务的进度
- 说"这个功能怎么实现"（暗示需要规划）
- 使用 `/plan` 命令

**不适用于：**
- 简单的单步任务
- 已有明确实现路径的小改动
- 纯粹的 bug 修复

## Core Workflow

```
用户描述需求
    |
[1] 澄清需求（必要时）
    • 范围边界
    • 成功标准
    • 约束条件
    |
[2] 生成计划
    • TLDR（3句话概括）
    • 成功标准（可验证）
    • 关键决策点
    • 任务拆解（分层）
    |
[3] 保存到 Obsidian
    • ~/Documents/Obsidian Vault/Projects/{PLAN_NAME}/
    |
[4] 执行时更新状态
    • pending -> in-progress -> done
```

## Quick Start

### 1. 创建新计划

```
/plan "为 portfolio monitor 添加自动止损功能"
```

Claude 会：
1. 理解需求，必要时澄清
2. 生成结构化计划
3. 保存到 Obsidian

### 2. 查看现有计划

```
/plan list                     # 列出所有计划
/plan show "计划名称"           # 显示计划详情
```

### 3. 更新计划状态

```
/plan update "计划名称" --task "任务ID" --status done
/plan update "计划名称" --task "1.2" --status in-progress
```

### 4. 继续执行计划

在后续对话中，告诉 Claude（或其他模型）：

```
继续执行计划：~/Documents/Obsidian Vault/Projects/auto-stop-loss/PLAN.md
```

任何模型都能读取计划并按步骤执行。

## Plan Template Structure

计划文件包含以下部分：

### 1. YAML Frontmatter

```yaml
---
created: 2026-02-05
type: feature-plan
status: in-progress
scope: medium          # small | medium | large
owner: Robin
tags: [portfolio, automation]
---
```

### 2. TLDR（必须）

**3 句话概括整个计划：**
1. 做什么（What）
2. 为什么（Why）
3. 怎么做（How - 高层策略）

**好的 TLDR 示例：**
> 为 portfolio monitor 添加自动止损功能，当持仓亏损超过阈值时自动触发警报。
> 这能帮助控制下行风险，避免因疏忽导致的超额亏损。
> 通过监控实时价格、对比成本价、达到阈值时发送 Telegram 通知来实现。

### 3. Success Criteria（成功标准）

可验证的完成条件：

```markdown
## Success Criteria

- [ ] 能设置每个持仓的止损百分比
- [ ] 触发止损时收到 Telegram 通知
- [ ] 有历史触发记录可查
- [ ] 支持暂停/恢复止损监控
```

### 4. Key Decisions（关键决策表）

| Decision | Options | Choice | Rationale |
|----------|---------|--------|-----------|
| 止损触发方式 | 市价单/限价单/仅通知 | 仅通知 | 自动下单风险高，先从通知开始 |
| 价格数据源 | Yahoo/IBKR API | Yahoo | 已有集成，免费 |

### 5. Task Breakdown（任务拆解）

```markdown
## Task Breakdown

### Phase 1: Foundation
- [ ] **1.1** 设计止损配置数据结构
  - Subtasks:
    - [ ] 1.1.1 定义 StopLoss schema
    - [ ] 1.1.2 添加到数据库
  - Dependencies: none
  - Estimate: 1h

- [ ] **1.2** 创建止损配置 API
  - Dependencies: 1.1
  - Estimate: 2h

### Phase 2: Core Logic
- [ ] **2.1** 实现价格监控循环
  - Dependencies: 1.1
  - Estimate: 2h

- [ ] **2.2** 实现止损触发逻辑
  - Dependencies: 2.1
  - Estimate: 1h
```

### 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| 价格 API 延迟 | 止损不及时 | 设置合理的检查频率 |
| 误触发 | 不必要的警报 | 添加确认机制 |

### 7. Progress Tracking

```markdown
## Progress

| Phase | Status | Completed |
|-------|--------|-----------|
| Phase 1 | done | 2026-02-05 |
| Phase 2 | in-progress | - |
| Phase 3 | pending | - |

### Recent Updates
- 2026-02-05: 完成 1.1, 1.2
- 2026-02-05: 开始 2.1
```

## Commands Reference

```bash
# 创建计划
/plan "计划描述"                           # 创建新计划（使用 basic 模板）
/plan "计划描述" --template feature        # 使用 feature 模板（更详细）
/plan "计划描述" --scope large             # 指定范围

# 查看计划
/plan list                                 # 列出所有计划
/plan list --status in-progress            # 按状态筛选
/plan show "计划名称"                       # 显示计划详情
/plan show "计划名称" --tasks              # 只显示任务列表

# 更新计划
/plan update "计划名称" --task "1.2" --status done
/plan update "计划名称" --task "1.2" --status in-progress
/plan update "计划名称" --task "1.2" --status blocked --reason "等待 API 文档"

# 添加内容
/plan add-task "计划名称" --phase 2 --task "新任务描述"
/plan add-decision "计划名称" --decision "..." --choice "..." --rationale "..."
/plan add-note "计划名称" --note "补充说明"
```

## Obsidian Integration

### Output Path

```
~/Documents/Obsidian Vault/Projects/
├── auto-stop-loss/
│   ├── PLAN.md              # 主计划文件
│   ├── decisions/           # 详细决策记录（可选）
│   └── notes/               # 相关笔记（可选）
├── 13f-api-redesign/
│   └── PLAN.md
└── ...
```

### Linking

计划文件支持 Obsidian 双链：

```markdown
- 相关 thesis: [[BABA]]
- 相关代码: [[portfolio_monitor]]
- 前置计划: [[database-migration]]
```

### Tags

自动添加的 tags：
- `#plan`
- `#status/{pending|in-progress|done}`
- 用户指定的其他 tags

## Multi-Model Execution

计划设计为可被任何模型执行：

### 为什么需要这个

- Claude 可能在会话中途断开
- 用户可能想用不同模型执行部分任务
- 计划需要跨多个会话执行

### 如何确保可执行性

1. **任务自包含** - 每个任务描述包含足够上下文
2. **依赖明确** - 使用 blockedBy 明确前置任务
3. **成功标准清晰** - 每个任务有明确的完成条件
4. **无假设** - 不假设模型知道之前的对话

### 执行指令示例

给其他模型的指令：

```
请读取并执行这个计划：
~/Documents/Obsidian Vault/Projects/auto-stop-loss/PLAN.md

从 Phase 2 的第一个 pending 任务开始。
完成后更新任务状态为 done。
```

## Best Practices

### TLDR 写作指南

- 第一句：做什么（功能描述）
- 第二句：为什么（业务价值）
- 第三句：怎么做（高层方案）
- 不超过 100 字
- 避免技术细节

### 任务分层建议

| 项目规模 | Phase 数量 | 每 Phase 任务数 |
|----------|------------|-----------------|
| Small | 1-2 | 3-5 |
| Medium | 2-4 | 5-10 |
| Large | 4-6 | 10-20 |

### 估时建议

- 乐观估计 x 1.5 = 实际估时
- 不确定的任务标记 `?`
- 大任务（>4h）应拆分

### 依赖管理

```markdown
# 好的依赖声明
- Dependencies: 1.1, 1.2

# 带条件的依赖
- Dependencies: 1.1 (schema), 2.1 (API ready)

# 外部依赖
- Dependencies: [external] IBKR API 文档
```

### 状态更新频率

- 开始任务时：pending -> in-progress
- 完成任务时：in-progress -> done
- 遇到阻塞时：添加 blocked 原因
- 每个会话结束时：更新 Progress 部分

## Integration with Other Skills

- **Thesis Manager**: 计划可链接到相关投资 thesis
- **Portfolio Monitor**: 功能计划可引用现有代码结构
- **Explore**: 复杂项目先用 /explore 了解再做计划

## Troubleshooting

| 问题 | 解决方案 |
|------|----------|
| 计划太大无法一次完成 | 拆分为多个小计划 |
| 任务依赖不清晰 | 添加 blockedBy 字段 |
| 多人协作冲突 | 每人负责不同 Phase |
| 计划过时 | 定期 review，标记 deprecated 任务 |
