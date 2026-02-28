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

## References

Detailed reference material — read as needed:
- Depth levels (Shallow/Standard/Deep detailed content): `references/depth-levels.md`
- Focus options (6 types with analysis details): `references/focus-options.md`
- Output templates and report structure: `references/output-templates.md`
