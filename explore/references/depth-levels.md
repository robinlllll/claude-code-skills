# Depth Levels

| Level | Time | Scope | Use Case |
|-------|------|-------|----------|
| **shallow** | ~5 min | 入口文件、README、配置文件 | 快速了解项目是什么 |
| **standard** | ~15 min | + 核心模块、主要流程 | 准备开发前的标准探索 |
| **deep** | ~30 min | + 所有模块、测试、文档 | 深入理解、重构准备 |

## Shallow (5 min)
- README / documentation
- Entry points (main.py, index.js, etc.)
- Configuration files (package.json, pyproject.toml, etc.)
- High-level directory structure
- Quick tech stack identification

## Standard (15 min) - Default
- Everything in Shallow, plus:
- Core module analysis
- Main data flows
- Key abstractions / interfaces
- Database schema (if applicable)
- API endpoints overview
- Primary design patterns

## Deep (30 min)
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
