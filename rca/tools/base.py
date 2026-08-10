"""工具规范定义：TOOL_CALL 文本协议 + 工具注册表。

错误契约集中于此:工具函数只负责「参数进、内容出」或抛 ToolError,
统一的错误前缀、参数校验(schema 生成)与输出截断都在 execute_tool 出口完成。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import config
from ..report import REPORT_START

ToolFn = Callable[[dict, Path], str]


class ToolError(Exception):
    """工具调用失败(参数错误/业务错误/底层命令失败)。

    只带消息,不带工具名;execute_tool 出口统一渲染成
    「[tool error] {工具名}: {消息}」。
    """


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


def validate(spec: ToolSpec, args: dict) -> dict:
    """按 parameters schema 校验/清洗参数,返回清洗后的 dict。

    - required 缺失(None / 空字符串)全部列出
    - integer 字段转换(失败报类型错误)
    - enum 字段越界报错
    - 未知参数与空串非必填字段忽略(宽容),条件必填由工具内部处理
    """
    props = spec.parameters.get("properties", {})

    def _missing(name: str) -> bool:
        val = args.get(name)
        return val is None or (isinstance(val, str) and not val.strip())

    missing = [
        name for name in spec.parameters.get("required", []) if _missing(name)
    ]
    if missing:
        raise ToolError("缺少参数: " + ", ".join(missing))

    out: dict = {}
    for name, val in args.items():
        prop = props.get(name)
        if prop is None:
            continue  # 未知参数:忽略,不传给工具函数
        if val is None:
            continue  # 显式 None 视同缺失
        if isinstance(val, str) and not val.strip():
            continue  # 空串:必填已在上方报错,非必填忽略
        if "enum" in prop and val not in prop["enum"]:
            raise ToolError(
                f"参数 {name} 必须是以下之一: {', '.join(prop['enum'])}"
            )
        if prop.get("type") == "integer" and not isinstance(val, bool):
            try:
                out[name] = int(val)
            except (TypeError, ValueError):
                raise ToolError(
                    f"参数 {name} 类型错误，期望 integer，实际: {val!r}"
                )
        else:
            out[name] = val
    return out


def _cap(text: str) -> str:
    if len(text) > config.MAX_TOOL_OUTPUT:
        return text[: config.MAX_TOOL_OUTPUT] + (
            f"\n...[输出过长，已截断，共 {len(text)} 字符]"
        )
    return text


def execute_tool(name: str, args: dict, repo: Path) -> str:
    spec = REGISTRY.get(name)
    if spec is None:
        return f"[tool error] 未知工具: {name}，可用: {', '.join(REGISTRY)}"
    try:
        cleaned = validate(spec, args)
        return _cap(spec.fn(cleaned, repo))
    except ToolError as exc:
        return f"[tool error] {name}: {exc}"
    except Exception as exc:  # 工具内部意外错误反馈给模型，让它换参数/换方向
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
        "调查完成后，最终报告必须以单独一行 " + REPORT_START + " 开头",
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
