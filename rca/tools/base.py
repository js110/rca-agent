"""工具规范定义：TOOL_CALL 文本协议 + 工具注册表。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ToolFn = Callable[[dict, Path], str]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    fn: ToolFn
    examples: list[str] = field(default_factory=list)


REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    REGISTRY[spec.name] = spec
    return spec


def execute_tool(name: str, args: dict, repo: Path) -> str:
    spec = REGISTRY.get(name)
    if spec is None:
        return f"[tool error] 未知工具: {name}，可用: {', '.join(REGISTRY)}"
    try:
        return spec.fn(args, repo)
    except Exception as exc:  # 工具内部错误反馈给模型，让它换参数/换方向
        return f"[tool error] {name} 执行失败: {exc}"


def protocol_text() -> str:
    """生成给 LLM 看的工具协议（含每个工具的 JSON schema 摘要）。"""
    lines = [
        "## 工具协议",
        "",
        "你的调查必须通过调用工具完成。需要调用工具时，输出且只输出以下格式：",
        "",
        "```",
        "TOOL_CALL",
        '{"name": "<工具名>", "arguments": {...}}',
        "```",
        "",
        "TOOL_CALL 之后会被执行，执行结果以「TOOL RESULT」的形式追加到对话中。",
        "可以连续多轮调用工具，直到证据充分。",
        "工具调用之外不要输出多余内容；不要解释、不要预告、不要使用其他格式。",
        "",
        "调查完成后，最终报告必须以单独一行 <!--RCA-REPORT-START--> 开头",
        "（报告是最终输出，之后不再调用任何工具）。",
        "",
        "### 可用工具",
        "",
    ]
    for spec in REGISTRY.values():
        lines.append(f"- **{spec.name}**：{spec.description}")
        lines.append(f"  参数: {json.dumps(spec.parameters, ensure_ascii=False)}")
        if spec.examples:
            lines.append(f"  示例: {spec.examples[0]}")
        lines.append("")
    return "\n".join(lines)
