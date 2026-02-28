# Output Templates and Report Structure

## Output Structure

**Default location:** `~/Documents/Obsidian Vault/归档/Code Exploration/{PROJECT}/`

**Note:** Directory is created automatically if it does not exist.

### Default Mode (Single README.md)
```
~/Documents/Obsidian Vault/归档/Code Exploration/{PROJECT}/
└── README.md                # 完整报告 (所有内容在一个文件)
```

### Split Mode (--split)
```
~/Documents/Obsidian Vault/归档/Code Exploration/{PROJECT}/
├── README.md                # 主报告 (链接到其他文件)
├── architecture.md          # 架构分析
├── data-model.md            # 数据模型
├── api-reference.md         # API 参考
├── directory-structure.md   # 目录结构
├── dependencies.md          # 依赖分析
├── getting-started.md       # 入门指南
└── questions.md             # 澄清问题
```

## Main Report Structure
```markdown
---
created: YYYY-MM-DD
project: PROJECT_NAME
depth: standard
focus: [architecture, data]
path: /absolute/path/to/project
---

# {PROJECT} - Exploration Report

## Executive Summary
[1-2 段落概述项目用途、技术栈、架构风格]

## Quick Facts
| Attribute | Value |
|-----------|-------|
| Language | Python 3.x |
| Framework | FastAPI |
| Database | SQLite |
| Lines of Code | ~5,000 |
| Last Updated | 2026-01-15 |

## Directory Structure
[核心目录树，带注释]

## Core Components
[主要模块及其职责]

## Data Flow
[数据如何流转，可用 Mermaid 图]

## Key Design Patterns
[使用的设计模式、约定]

## Critical Files
[必须了解的关键文件列表]

## Clarification Questions
[需要进一步了解的问题]

## Next Steps
[建议的探索方向或开发起点]
```

## Clarification Questions

每份报告必须包含 "Clarification Questions" 部分。这些问题帮助识别:

1. **文档缺失** - 代码有但文档没说明的部分
2. **隐式假设** - 代码中隐含的业务逻辑假设
3. **设计意图** - 为什么这样设计（不是怎么实现的）
4. **边界条件** - 错误处理、极端情况
5. **部署要求** - 环境变量、外部依赖

**示例问题格式:**
```markdown
## Clarification Questions

### Architecture
- [ ] `services/` 和 `handlers/` 的职责划分标准是什么？
- [ ] 为什么选择 SQLite 而非 PostgreSQL？有扩展考虑吗？

### Data
- [ ] `users.status` 字段有哪些有效值？状态转换规则是什么？
- [ ] 价格数据的更新频率是多少？缓存策略如何？

### Operations
- [ ] 生产环境需要哪些环境变量？
- [ ] 有备份和恢复流程吗？
```
