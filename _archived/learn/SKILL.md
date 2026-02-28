---
name: learn
description: 80/20 技术概念学习助手 - 用类比和关键点快速理解技术概念，输出到 Obsidian。为投资背景的非技术用户设计。
---

# Learn - 80/20 技术概念学习

用 80/20 法则快速理解技术概念。类比优先，不超过 3 个关键点，5 分钟阅读时间。

## Instructions for Claude

**自动创建目录：** 如果 `~/Documents/Obsidian Vault/写作/技术概念/` 目录不存在，在保存第一个笔记前自动创建该目录。

**自动双链检测：** 在生成解释内容时，自动扫描 `写作/技术概念/` 目录下已存在的笔记。如果解释中提到的概念已有笔记文件，自动将其转换为 Obsidian 双链格式 `[[概念名]]`。例如：如果解释 Kubernetes 时提到 Docker，且 `Docker.md` 已存在，则自动写成 `[[Docker]]`。

**默认保存行为：** 默认保存到 Obsidian。如果用户使用 `--no-save` 参数，则只显示解释内容，不保存文件。

## When to Use This Skill

Trigger when user:
- 说"解释一下..."、"什么是..."、"帮我理解..."
- 提到技术术语并希望了解其含义
- 需要快速掌握某个技术概念的核心
- 使用 `/learn` 命令
- 在投资研究中遇到不熟悉的技术名词

**不适用于：**
- 需要深入技术细节的开发任务
- 已经熟悉的概念
- 非技术领域的概念

## Core Workflow

```
用户提问技术概念
    ↓
[0] 检查目录
    • 如果 写作/技术概念/ 目录不存在，自动创建
    • 扫描已存在的笔记文件，用于后续双链检测
    ↓
[1] 确定上下文
    • 用户已知的概念有哪些？
    • 为什么需要了解这个概念？(投资研究/日常使用/技术评估)
    ↓
[2] 类比优先
    • 用金融/商业类比（用户熟悉领域）
    • 用日常生活类比
    ↓
[3] 80/20 核心内容
    • 定义（1-2句话）
    • 核心作用（解决什么问题）
    • 3个关键特性（不超过3个！）
    ↓
[4] 实用判断
    • 何时用/何时不用
    • 常见误解
    ↓
[5] 自动双链
    • 检查解释中提到的概念是否已有笔记
    • 自动添加 [[概念名]] 双链
    ↓
[6] 输出到 Obsidian（默认）
    • ~/Documents/Obsidian Vault/写作/技术概念/{概念名}.md
    • 如果使用 --no-save，则只显示不保存
```

## Quick Start

### 基本用法

```
/learn Docker
/learn Kubernetes
/learn gRPC
/learn WebSocket vs REST
```

### 带上下文的用法

```
/learn Docker --context "在研究云计算公司"
/learn LLM fine-tuning --context "评估AI创业公司"
```

### 比较多个概念

```
/learn Docker vs Kubernetes vs Serverless
/learn REST vs GraphQL vs gRPC
/learn Docker vs Kubernetes --compare    # 明确使用对比模式
```

### 只查看不保存

```
/learn Docker --no-save                  # 只显示解释，不保存到 Obsidian
```

## 输出格式

每个概念解释遵循固定结构：

### 1. 一句话类比（必须）
用用户熟悉的领域来类比，第一句话就是类比。

**好的类比：**
- "Docker 就像集装箱——把应用和它需要的所有东西打包在一起，到哪都能用。"
- "API 就像餐厅的菜单——你不需要知道厨房怎么做菜，只需要看菜单点单。"
- "Git 就像投资的交易记录——每次改动都有快照，随时可以回到任何历史状态。"

**避免的类比：**
- 过于技术化的类比（用另一个技术概念解释）
- 过于抽象的类比

### 2. 核心定义（1-2句话）
精确但不过度技术化的定义。

### 3. 解决什么问题
这个技术为什么存在？它解决的痛点是什么？

### 4. 3个关键特性（严格不超过3个）
80/20 法则：掌握这 3 点 = 理解 80% 的核心价值

### 5. 何时用/何时不用
实用的判断指南，帮助用户在实际场景中做决策。

### 6. 常见误解（可选）
澄清常见的错误理解。

### 7. 延伸阅读（可选）
- 相关概念的链接（Obsidian 双链）
- 如果用户想深入，下一步看什么

## Commands Reference

```bash
# 基本学习
/learn {概念}                    # 解释单个概念，默认保存到 Obsidian
/learn {概念} --context "..."    # 带上下文解释
/learn {概念} --no-save          # 只显示解释，不保存

# 对比模式 (--compare)
/learn {A} vs {B}                # 比较两个概念
/learn {A} vs {B} vs {C}         # 比较多个概念（最多 5 个）
/learn {A} vs {B} --compare      # 明确使用对比模式

# 查看已学习的概念
/learn list                      # 列出所有已学习的概念（含日期和标签）
/learn show {概念}               # 显示已保存的笔记

# 管理
/learn refresh {概念}            # 更新已有笔记
/learn delete {概念}             # 删除笔记
```

## 对比模式详解 (--compare)

当使用 `vs` 关键字或 `--compare` 参数时，输出对比表格：

| 维度 | {概念A} | {概念B} | {概念C} |
|------|---------|---------|---------|
| **一句话** | 类比描述 | 类比描述 | 类比描述 |
| **用途** | 主要用途 | 主要用途 | 主要用途 |
| **优势** | 核心优点 | 核心优点 | 核心优点 |
| **劣势** | 主要缺点 | 主要缺点 | 主要缺点 |
| **何时选择** | 适用场景 | 适用场景 | 适用场景 |

对比笔记保存为：`写作/技术概念/{A} vs {B} vs {C}.md`

## /learn list 命令详解

列出 `写作/技术概念/` 目录下所有已学概念：

```
已学习的技术概念 (12 个)
========================

| 概念 | 学习日期 | 标签 |
|------|----------|------|
| Docker | 2026-02-01 | #容器化 #云计算 |
| Kubernetes | 2026-02-02 | #容器编排 #云计算 |
| REST vs GraphQL | 2026-02-03 | #API #网络 |
| ...

提示：使用 /learn show {概念} 查看详情
```

## Obsidian 集成

### 输出路径
```
~/Documents/Obsidian Vault/写作/技术概念/
├── Docker.md
├── Kubernetes.md
├── API.md
├── REST vs GraphQL.md
└── ...
```

### 笔记模板
见 `templates/learning_note.md`

### 双链支持（自动检测）

**行为：** 在生成解释内容时，自动扫描 `写作/技术概念/` 目录下已存在的 `.md` 文件。如果解释中提到的概念已有对应笔记，自动将其转换为双链格式。

**示例：**
- 目录中已有：`Docker.md`, `API.md`, `REST.md`
- 解释 Kubernetes 时提到 "Docker 容器"
- 自动转换为 "[[Docker]] 容器"

**不会双链的情况：**
- 概念尚未有笔记文件
- 概念名称只是部分匹配（如 "Dock" 不会链接到 "Docker"）

### Tags
自动添加的 tags：
- `#技术概念`
- `#学习笔记`
- 领域 tag（如 `#云计算`、`#AI`、`#网络`）

## 用户画像适配

### 已知领域（用于类比）
- 金融投资（portfolio, P&L, hedge, diversification）
- 商业运营（supply chain, inventory, margin）
- 日常生活

### 目标
- 快速掌握概念核心（80/20）
- 能在投资研究中判断技术可行性
- 能与技术人员基本沟通
- 不需要成为技术专家

### 避免
- 过度技术细节
- 代码示例（除非用户要求）
- 假设用户有编程背景

## 质量检查清单

生成每个解释时，检查：

- [ ] 第一句话是类比吗？
- [ ] 定义不超过 2 句话吗？
- [ ] 关键特性不超过 3 个吗？
- [ ] 5 分钟内能读完吗？
- [ ] 用户不需要技术背景也能理解吗？
- [ ] 有实用的"何时用/何时不用"判断吗？

## Example Output

```markdown
---
created: 2026-02-05
type: learning-note
tags: [技术概念, 学习笔记, 容器化]
related: [[Kubernetes]], [[虚拟机]]
---

# Docker

> 就像集装箱——把应用和它需要的所有东西打包在一起，到哪都能用。

## 定义
Docker 是一个容器化平台，让你把应用程序和它的依赖打包成一个"容器"，可以在任何支持 Docker 的环境中运行。

## 解决什么问题
"在我电脑上能跑"的问题。开发环境和生产环境不一致，导致部署时出错。

## 3 个关键特性

1. **打包一切** - 应用代码 + 依赖库 + 配置 = 一个容器
2. **到处能跑** - 本地、测试服务器、云端，只要有 Docker 就能运行
3. **轻量隔离** - 比虚拟机更轻，启动更快，资源占用更少

## 何时用 / 何时不用

**适合：**
- 部署微服务架构
- 需要环境一致性
- 快速扩缩容

**不适合：**
- 简单的单体应用
- 需要直接访问硬件
- Windows GUI 应用

## 常见误解

- Docker ≠ 虚拟机（容器共享操作系统内核，更轻量）
- Docker ≠ Kubernetes（K8s 是容器编排工具，管理多个容器）

## 延伸阅读

- [[Kubernetes]] - 当你有很多容器需要管理时
- [[虚拟机]] - 理解容器和虚拟机的区别
```

## Investment Context Linking

生成概念笔记后，自动检查是否与投资持仓相关：

1. **检查 entity_dictionary.yaml 的 `key_products` 字段**
   - 读取 `~/.claude/skills/shared/entity_dictionary.yaml`
   - 在所有公司的 `key_products` 中搜索概念名（模糊匹配）
   - 示例：学习 "CoWoS" → 匹配 TSM 的 key_products → 发现关联
   - 示例：学习 "ZYN" → 匹配 PM 的 key_products → 发现关联

2. **如果找到关联 ticker：**
   - 在 frontmatter 中添加 `related_tickers: [TSM, NVDA]`
   - 在笔记的"应用场景"或"延伸阅读"部分添加 wikilinks：[[TSM]], [[NVDA]]
   - 追加一个 section：
     ```
     ## 投资关联
     - 相关持仓：[[TSM]] — CoWoS 是其先进封装技术核心
     - 也关联：[[NVDA]] — CoWoS 是 H100/H200 的关键封装工艺
     ```

3. **检查是否有对应 thesis：**
   - 查看 `~/PORTFOLIO/portfolio_monitor/research/companies/{TICKER}/thesis.md` 是否存在
   - 如果存在，在终端输出提示：
     "This concept is related to your {TICKER} thesis. Consider adding [[{概念名}]] to the thesis."

## Integration with Other Skills

- **Thesis Manager**: 在投资研究中遇到技术概念时，可以快速学习；概念笔记自动链接到相关 thesis
- **NotebookLM**: 如果概念与已有文档相关，可以引用
- **Supply Chain**: 技术概念可能与供应链关系相关（如 CoWoS → TSM-NVDA 供应链）

## Best Practices

1. **先问上下文** - 了解用户为什么需要学这个概念
2. **类比用熟悉领域** - 优先用金融/商业类比
3. **严格 80/20** - 不要试图解释所有细节
4. **实用导向** - 帮助用户做判断，不是成为专家
5. **建立知识网络** - 通过双链连接相关概念
