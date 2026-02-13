#!/usr/bin/env python3
"""
OpenAI API Client for Prompt Optimizer

Role: Edge Case Hunter
- Primary focus: What inputs would break this prompt? What ambiguities cause inconsistent outputs?
- Checks for: adversarial inputs, boundary conditions, cultural/language edge cases, model confusion risks
- Output: list of problematic test cases with expected vs likely actual behavior
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

sys.stdout.reconfigure(encoding='utf-8', errors='replace')


@dataclass
class GPTReviewResult:
    text: str
    model: str


class GPTClient:
    """Client for OpenAI API

    Role: Edge Case Hunter - finds inputs that break the prompt.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-5.2-chat-latest",
        base_url: Optional[str] = None,
    ):
        from openai import OpenAI

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        kwargs = {"api_key": self.api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def health_check(self) -> bool:
        """Test API connectivity"""
        try:
            r = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_completion_tokens=5,
            )
            return bool(r.choices[0].message.content)
        except Exception:
            return False

    def review_prompt(
        self,
        spec_md: str,
        prompt_text: str,
        test_report: str = "",
        history_excerpt: str = "",
    ) -> GPTReviewResult:
        """
        Send prompt to GPT for edge case review.

        Role: Edge Case Hunter
        - Finds inputs that would break the prompt
        - Identifies ambiguities that cause inconsistent outputs
        - Tests boundary conditions and adversarial scenarios
        """
        contents = f"""
你是 **Edge Case Hunter**（边缘情况猎手）。你的核心任务是找出哪些输入会让这个 Prompt 产生错误、不一致或意外的输出。

## 你的审查重点
- 什么样的输入会让 Prompt 崩溃或产生垃圾输出？
- 哪些模糊表述会导致不同运行之间输出不一致？
- 有哪些边界条件（极短/极长输入、特殊字符、多语言混合）没有处理？
- 用户可能如何误用这个 Prompt？模型可能如何误解指令？

## 输出格式必须严格为：

### 1) Edge Case Test Cases
列出 5-8 个具体的问题测试用例，每个包括：
- **输入**: 具体的测试输入描述
- **预期行为**: 根据 spec 应该怎么处理
- **可能实际行为**: 当前 prompt 大概率会怎么处理
- **风险等级**: HIGH / MEDIUM / LOW

### 2) Verdict: PASS / FAIL
如果存在 HIGH 风险的边缘情况则 FAIL

### 3) Top 5 Issues（按严重性排序）
每条包括：问题 → 为什么严重 → 触发场景 → 如何验证
重点关注：
- 对抗性输入（用户故意或无意提供异常数据）
- 边界条件（空输入、超长输入、特殊格式）
- 文化/语言边缘情况（中英文混合、专有名词、编码问题）
- 模型困惑风险（指令歧义导致模型行为不确定）

### 4) Minimal Patch
只给必要修改：用"替换/新增/删除"的差分指令，不要重写全文

### 5) Regression Risks
这次修改可能引入的新问题

## 约束
- 不要提出"重新定义任务/扩大范围"的建议
- 不要给泛泛之谈；每条问题必须能用测试用例复现或验证
- 你只负责边缘情况和鲁棒性，不负责 spec 合规性检查（那是另一个审阅者的工作）

[PromptSpec]
{spec_md}

[Prompt]
{prompt_text}

[TestReport（如果有）]
{test_report if test_report else "暂无"}

[History Excerpt（可选）]
{history_excerpt if history_excerpt else "首次审阅"}
""".strip()

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": contents}],
        )
        return GPTReviewResult(
            text=resp.choices[0].message.content,
            model=self.model,
        )


def main():
    """Test GPT client"""
    import argparse

    parser = argparse.ArgumentParser(description='Test OpenAI API')
    parser.add_argument('--health', action='store_true', help='Health check')
    parser.add_argument('--test', help='Test with simple prompt')

    args = parser.parse_args()

    client = GPTClient()

    if args.health:
        ok = client.health_check()
        print(f"Health check: {'OK' if ok else 'FAILED'}")
        return 0 if ok else 1

    if args.test:
        result = client.review_prompt(
            spec_md="测试用 spec",
            prompt_text=args.test,
        )
        print(result.text)
        return 0

    ok = client.health_check()
    print(f"GPT client ready: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main() or 0)
