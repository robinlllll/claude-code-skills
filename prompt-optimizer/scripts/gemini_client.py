#!/usr/bin/env python3
"""
Gemini API Client for Prompt Optimizer
Uses the official google-genai SDK (not the deprecated google-generativeai)

Role: Spec Compliance Auditor
- Primary focus: Does the prompt satisfy EVERY requirement in spec.md?
- Checks for: missing constraints, ambiguous instructions, underspecified output format
- Output: checklist of spec requirements with PASS/FAIL for each
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types as genai_types


@dataclass
class GeminiReviewResult:
    text: str
    model: str


class GeminiClient:
    """Client for Gemini API using official google-genai SDK

    Role: Spec Compliance Auditor - systematically checks every spec requirement.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        timeout: Optional[int] = None,
    ):
        # Official SDK reads from GEMINI_API_KEY env var by default
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        client_kwargs = {}
        if self.api_key:
            client_kwargs["api_key"] = self.api_key
        if timeout:
            client_kwargs["http_options"] = genai_types.HttpOptions(timeout=timeout)
        self.client = genai.Client(**client_kwargs)
        self.model = model

    def health_check(self) -> bool:
        """Test API connectivity"""
        try:
            r = self.client.models.generate_content(
                model=self.model,
                contents="ping",
            )
            _ = getattr(r, "text", None)
            return True
        except Exception:
            return False

    def review_prompt(
        self,
        spec_md: str,
        prompt_text: str,
        test_report: str = "",
        history_excerpt: str = "",
    ) -> GeminiReviewResult:
        """
        Send prompt to Gemini for spec compliance review.

        Role: Spec Compliance Auditor
        - Checks every requirement in spec.md against the prompt
        - Returns checklist with PASS/FAIL per requirement
        - Plus verdict, issues, minimal patch, and regression risks
        """
        contents = f"""
你是 **Spec Compliance Auditor**（规格合规审计员）。你的核心任务是逐条检查 Prompt 是否满足 PromptSpec 中的每一项要求。

## 你的审查重点
- 逐条对照 PromptSpec，检查 Prompt 是否覆盖了每一项约束和要求
- 找出遗漏的约束、模糊的指令、未明确定义的输出格式
- 关注 PromptSpec 中的硬性约束（hard constraints）是否被严格满足

## 输出格式必须严格为：

### 1) Spec Compliance Checklist
逐条列出 PromptSpec 中的关键要求，并标注 PASS / FAIL：
- [PASS/FAIL] 要求描述 → 在 Prompt 中的对应位置或缺失说明

### 2) Verdict: PASS / FAIL
基于 Checklist 结果给出总体判定。任何硬性约束 FAIL 则总体 FAIL。

### 3) Top 5 Issues（按严重性排序）
每条包括：问题 → 为什么严重 → 触发场景 → 如何验证
重点关注：
- 缺失的约束（spec 有要求但 prompt 没提到）
- 模糊的指令（spec 明确但 prompt 表述含糊）
- 输出格式不完整（spec 定义了格式但 prompt 未完全说明）

### 4) Minimal Patch
只给必要修改：用"替换/新增/删除"的差分指令，不要重写全文

### 5) Regression Risks
这次修改可能引入的新问题

## 约束
- 不要提出"重新定义任务/扩大范围"的建议
- 不要给泛泛之谈；每条问题必须能用测试用例复现或验证
- 你只负责 spec 合规性，不负责边缘情况测试（那是另一个审阅者的工作）

[PromptSpec]
{spec_md}

[Prompt]
{prompt_text}

[TestReport（如果有）]
{test_report if test_report else "暂无"}

[History Excerpt（可选）]
{history_excerpt if history_excerpt else "首次审阅"}
""".strip()

        resp = self.client.models.generate_content(
            model=self.model,
            contents=contents,
        )
        return GeminiReviewResult(
            text=resp.text if hasattr(resp, "text") else str(resp),
            model=self.model
        )


def main():
    """Test Gemini client"""
    import argparse

    parser = argparse.ArgumentParser(description='Test Gemini API')
    parser.add_argument('--health', action='store_true', help='Health check')
    parser.add_argument('--test', help='Test with simple prompt')

    args = parser.parse_args()

    client = GeminiClient()

    if args.health:
        ok = client.health_check()
        print(f"Health check: {'OK' if ok else 'FAILED'}")
        return 0 if ok else 1

    if args.test:
        result = client.review_prompt(
            spec_md="测试用 spec",
            prompt_text=args.test
        )
        print(result.text)
        return 0

    # Default: health check
    ok = client.health_check()
    print(f"Gemini client ready: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main() or 0)
