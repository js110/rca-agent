"""分析任务：工具循环。TOOL_CALL 文本协议 → 执行 → 反馈结果，直到输出报告。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .. import config
from ..llm import LLMClient
from ..report import REPORT_START
from ..tools import execute_tool, protocol_text

_CALL_RE = re.compile(
    r"TOOL_CALL\s*(\{[^{}]*?(?:\{[^{}]*\}[^{}]*?)*\})", re.DOTALL
)
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

NUDGE = (
    "你上一轮的输出既不是 TOOL_CALL 也不是以 "
    + REPORT_START
    + " 开头的最终报告。"
    "请重新输出：要么输出 TOOL_CALL + JSON，要么直接输出最终报告。"
)


@dataclass
class ToolCall:
    name: str
    args: dict


def parse_tool_call(text: str) -> ToolCall | None:
    m = _CALL_RE.search(text) or _FENCE_RE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    name = data.get("name")
    args = data.get("arguments") or {}
    if not isinstance(name, str) or not isinstance(args, dict):
        return None
    return ToolCall(name=name, args=args)


def build_system_prompt() -> str:
    base = (config.PROMPTS_DIR / "analysis-system-prompt.md").read_text(encoding="utf-8")
    return base + "\n\n" + protocol_text()


def run_analysis(llm: LLMClient, repo: Path, mr_text: str,
                 framework: str | None, commit_url: str | None = None) -> str:
    system = build_system_prompt()
    user = f"## 分析框架\n\n{framework or '(无匹配框架：按系统提示词规则处理)'}\n\n{mr_text}"
    if commit_url:
        user += (
            "\n\n### 提交链接\n\n"
            f"本仓库 commit 链接前缀: {commit_url}/commit/\n"
            "报告引用 commit 时用 markdown 链接：[短 hash](前缀 + 完整 hash)"
        )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    last_text = ""
    call_counts: dict[tuple[str, str], int] = {}

    for step in range(1, config.MAX_ITERATIONS + 1):
        last_text = llm.chat(messages)
        if REPORT_START in last_text:
            return last_text
        call = parse_tool_call(last_text)
        if call is None:
            messages.append({"role": "assistant", "content": last_text})
            messages.append({"role": "user", "content": NUDGE})
            continue
        sig = (call.name, json.dumps(call.args, sort_keys=True, ensure_ascii=False))
        call_counts[sig] = call_counts.get(sig, 0) + 1
        result = execute_tool(call.name, call.args, repo)
        if call_counts[sig] > 1:
            result += (
                "\n[note] 该调用（相同参数）已执行过，结果不会变化，请换方向或换参数。"
            )
        messages.append({"role": "assistant", "content": last_text})
        messages.append(
            {"role": "user", "content": f"## TOOL RESULT（第 {step} 轮）\n{result}"}
        )
        print(f"[step {step}] {call.name} {json.dumps(call.args, ensure_ascii=False)[:120]}")

    print(f"[warn] 达到最大迭代 {config.MAX_ITERATIONS}，输出最后一次回复")
    return last_text
