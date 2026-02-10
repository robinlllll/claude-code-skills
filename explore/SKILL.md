---
name: explore
description: Codebase exploration tool - understand project structure before development. 3 depth levels (Shallow/Standard/Deep), 6 focus options, outputs structured reports to Obsidian.
---

# Explore - Codebase Exploration Tool

Systematically explore and understand codebases before development. Generates structured reports with architecture insights, data flows, and clarification questions.

**Important:** If the output directory `~/Documents/Obsidian Vault/归档/Code Exploration/` does not exist, create it automatically before writing reports. Never ask the user to create directories manually.

## When to Use This Skill

Trigger when user:
- Says "explore", "understand codebase", "analyze project"
- Wants to understand a new codebase before making changes
- Needs a project overview or architecture documentation
- Uses `/explore` command
- Asks "how does this project work?"
- Uses `/explore list` to view previously explored projects

## Core Workflow

**Progress Display:** Show progress at each stage to keep the user informed.

```
用户指定目录 + 深度 + 聚焦
    |
[1/6] 扫描目录结构...
    | 快速扫描 - 项目类型识别
    | README, package.json, requirements.txt, etc.
    |
[2/6] 读取项目文档...
    | 结构分析 - 目录树 + 文件统计
    | 按深度级别决定扫描范围
    |
[3/6] 分析核心组件...
    | 聚焦分析 - 根据 focus 选项深入
    | architecture / data / api / workflow / dependencies / newbie
    |
[4/6] 识别设计模式...
    | 模式识别 - 设计模式、约定
    | 命名规范、目录组织、配置方式
    |
[5/6] 生成澄清问题...
    | 问题生成 - 澄清问题
    | 识别文档缺失、隐式假设
    |
[6/6] 写入探索报告...
    | 报告输出 - 写入 Obsidian (自动创建目录)
    | ~/Documents/Obsidian Vault/归档/Code Exploration/{PROJECT}/
```

**Note:** If `归档/Code Exploration/` directory does not exist, create it automatically at step 6.

## Quick Start

### Basic Usage
```bash
# 标准探索 (15分钟)
/explore /path/to/project

# 带任务描述
/explore /path/to/project "implement user authentication"

# 指定深度
/explore /path/to/project --depth shallow
/explore /path/to/project --depth deep

# 指定聚焦
/explore /path/to/project --focus architecture
/explore /path/to/project --focus api

# 自定义输出路径
/explore /path/to/project --output ~/Desktop/report.md

# 多文件输出
/explore /path/to/project --split

# 列出已探索的项目
/explore list
```

### Full Command Format
```
/explore PATH [TASK_DESCRIPTION] [OPTIONS]
/explore list
```

## Depth Levels

| Level | Time | Scope | Use Case |
|-------|------|-------|----------|
| **shallow** | ~5 min | 入口文件、README、配置文件 | 快速了解项目是什么 |
| **standard** | ~15 min | + 核心模块、主要流程 | 准备开发前的标准探索 |
| **deep** | ~30 min | + 所有模块、测试、文档 | 深入理解、重构准备 |

### Shallow (5 min)
- README / documentation
- Entry points (main.py, index.js, etc.)
- Configuration files (package.json, pyproject.toml, etc.)
- High-level directory structure
- Quick tech stack identification

### Standard (15 min) - Default
- Everything in Shallow, plus:
- Core module analysis
- Main data flows
- Key abstractions / interfaces
- Database schema (if applicable)
- API endpoints overview
- Primary design patterns

### Deep (30 min)
- Everything in Standard, plus:
- All module interactions
- Test coverage analysis
- Build / deployment configuration
- Performance considerations
- Security patterns
- Dependency deep dive
- **Git History Analysis** (if git repo):
  - Recent commits (last 20 commits with messages)
  - Active contributors (top committers)
  - Code change hotspots (most frequently modified files)
  - Branch structure overview

## Focus Options

| Focus | Description | Key Questions |
|-------|-------------|---------------|
| **architecture** | 系统架构、模块划分 | 如何组织？核心抽象是什么？ |
| **data** | 数据模型、存储、流转 | 数据如何持久化？Schema 是什么？ |
| **api** | 接口定义、端点、协议 | 有哪些 API？如何认证？ |
| **workflow** | 业务流程、状态机 | 主要用户流程是什么？ |
| **dependencies** | 依赖关系、版本、风险 | 关键依赖是什么？有无安全风险？ |
| **newbie** | 新手入门视角 | 如何运行？如何开发？常见坑？ |

### Architecture Focus
```
分析内容:
- 目录结构设计原则
- 核心模块及其职责
- 模块间依赖关系图
- 设计模式使用情况
- 扩展点和插件机制
```

### Data Focus
```
分析内容:
- 数据库类型和 schema
- ORM / 数据访问层
- 数据流向图
- 缓存策略
- 数据验证规则
```

### API Focus
```
分析内容:
- API 路由定义
- 请求/响应格式
- 认证/授权机制
- 错误处理约定
- API 文档位置
```

### Workflow Focus
```
分析内容:
- 主要用户流程
- 状态转换逻辑
- 异步任务处理
- 事件/消息流
- 错误恢复流程
```

### Dependencies Focus
```
分析内容:
- 直接依赖列表
- 依赖版本锁定情况
- 安全漏洞扫描
- 未使用依赖
- 依赖升级建议
```

### Newbie Focus
```
分析内容:
- 开发环境搭建步骤
- 运行和调试方法
- 代码规范和约定
- 常见问题和解决方案
- 推荐的学习路径
```

## Commands Reference

### Primary Command
```bash
/explore PATH [TASK] [OPTIONS]

# Examples
/explore ~/PORTFOLIO
/explore ~/13F-CLAUDE "add new data source"
/explore . --depth deep --focus architecture
/explore ~/xueqiu --output ~/Desktop/xueqiu-report.md
/explore ~/PORTFOLIO --split
```

### List Command
```bash
/explore list

# Output example:
# 归档/Code Exploration/ 目录下已探索的项目:
#
# | Project | Explored Date | Depth | Files |
# |---------|---------------|-------|-------|
# | PORTFOLIO | 2026-01-15 | deep | 7 |
# | 13F-CLAUDE | 2026-01-10 | standard | 5 |
# | xueqiu | 2025-12-20 | shallow | 3 |
```

### Options

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--depth` | shallow, standard, deep | standard | 探索深度 |
| `--focus` | architecture, data, api, workflow, dependencies, newbie | (all) | 聚焦领域 |
| `--output` | PATH | `归档/Code Exploration/{PROJECT}/README.md` | 自定义输出路径 (单文件) |
| `--split` | - | false | 多文件输出模式 |
| `--no-obsidian` | - | false | 不输出到 Obsidian |

### Output Modes

**Default (Single File):**
```bash
/explore ~/PORTFOLIO
# Output: ~/Documents/Obsidian Vault/归档/Code Exploration/PORTFOLIO/README.md
```

**Custom Output Path:**
```bash
/explore ~/PORTFOLIO --output ~/Desktop/portfolio-report.md
# Output: ~/Desktop/portfolio-report.md (single file with all sections)
```

**Split Mode (Multiple Files):**
```bash
/explore ~/PORTFOLIO --split
# Output: ~/Documents/Obsidian Vault/归档/Code Exploration/PORTFOLIO/
#   ├── README.md           # 主报告 (索引)
#   ├── architecture.md     # 架构分析
#   ├── data-model.md       # 数据模型
#   ├── api-reference.md    # API 参考
#   ├── dependencies.md     # 依赖分析
#   └── questions.md        # 澄清问题
```

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

### Main Report Structure
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

## Integration with Robin's Projects

此 skill 已针对用户现有项目优化:

| Project | 推荐 Focus | 关键探索点 |
|---------|------------|-----------|
| PORTFOLIO | data, api | SQLite schema, FastAPI routes, P&L calculation |
| 13F-CLAUDE | data, workflow | SEC EDGAR parsing, filing schedule, data pipeline |
| CALENDAR-CONVERTER | workflow | Event parsing, .ics generation |
| xueqiu | data, workflow | Scraping logic, rate limiting |
| wechat-exporter | workflow, api | WeChat API, Notion integration |

## Task-Driven Exploration

当用户提供任务描述时，探索会更有针对性:

```bash
/explore ~/PORTFOLIO "add support for options trading"
```

此时报告会特别关注:
- 当前交易类型如何定义
- 数据模型是否支持期权属性
- P&L 计算是否可扩展
- UI 需要哪些改动

## Best Practices

1. **先 shallow 后 deep** - 不确定时从 shallow 开始
2. **带任务描述** - 有具体任务时效果更好
3. **保存报告** - 报告是宝贵的项目文档
4. **回答澄清问题** - 这是深化理解的最佳方式
5. **多 focus 组合** - 复杂项目可以多次探索不同 focus

## Limitations

- 不执行代码，仅静态分析
- 依赖良好的命名和结构推断意图
- 复杂业务逻辑可能需要人工补充
- Git 历史分析需要 git 仓库
