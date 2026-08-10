"""CRG (code-review-graph) 图谱工具集成。

进程内直调 code_review_graph 的公开函数（与它的 MCP 工具同一实现），
条件：warm-start 成功 —— CRG 已安装、且该仓库的图谱已构建/构建成功。
图谱未就绪时工具返回 [unavailable] 状态信号，让模型转用 gitGrep/gitDiff 等文本工具
（unavailable 与 [tool error] 语义不同：前者是降级提示，不是错误）。
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import ToolError, ToolSpec, register

_CRG = None  # 延迟导入，未安装时优雅降级


def _load():
    global _CRG
    if _CRG is None:
        try:
            from code_review_graph.tools import build, query, review

            _CRG = {"build": build, "query": query, "review": review}
        except ImportError:
            _CRG = False
    return _CRG


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def crg_built(repo: Path) -> bool:
    """该仓库的图谱是否已构建（warm-start 检查）。"""
    mods = _load()
    if not mods:
        return False
    try:
        db = mods["query"].get_db_path(repo)
        return db.is_file() and db.stat().st_size > 0
    except Exception:
        return False


def crg_warm_start(repo: Path, base: str | None = None) -> bool:
    """增量更新/构建图谱（MR 场景每次 head 都可能是新的）。返回是否就绪。"""
    mods = _load()
    if not mods:
        return False
    try:
        mods["build"].build_or_update_graph(
            repo_root=str(repo), base=base or "HEAD~1", postprocess="minimal"
        )
    except Exception:
        try:
            mods["build"].build_or_update_graph(
                repo_root=str(repo), full_rebuild=True, postprocess="minimal"
            )
        except Exception:
            return False
    return crg_built(repo)


def _unavailable(reason: str) -> str:
    return (
        "[unavailable] 代码图谱不可用："
        + reason
        + "。请改用 gitGrep / gitDiff / read 等文本工具继续调查。"
    )


def _call(attr: str, repo: Path, **kwargs) -> str:
    """执行 CRG 函数:未安装/图谱未构建 → unavailable 降级信号,异常 → ToolError。

    attr 为 mods 字典内的点分路径,如 "query.query_graph" / "review.detect_changes_func"。
    """
    mods = _load()
    if not mods:
        return _unavailable("未安装 code-review-graph（pip install code-review-graph）")
    parts = attr.split(".")
    fn = mods[parts[0]]  # mods 是 dict;其值是模块,后续层用属性访问
    for part in parts[1:]:
        fn = getattr(fn, part)
    if not crg_built(repo):
        return _unavailable(
            "该仓库图谱未构建或 warm-start 失败（.code-review-graph/ 不存在）"
        )
    try:
        result = fn(repo_root=str(repo), **kwargs)
        return _dump(result)
    except Exception as exc:
        raise ToolError(f"{attr.rsplit('.', 1)[-1]} 失败: {exc}") from exc


def _changed_files(args: dict) -> list | None:
    """changed_files 参数清洗:CSV 字符串 → list(validate 只做 schema 校验)。"""
    files = args.get("changed_files")
    if isinstance(files, str):
        return [f.strip() for f in files.split(",") if f.strip()]
    return files


def _graph_query(args: dict, repo: Path) -> str:
    pattern = str(args.get("pattern", "") or "").strip()
    target = str(args.get("target", "") or "").strip()
    allowed = {
        "callers_of", "references_to", "callees_of", "imports_of",
        "importers_of", "children_of", "tests_for", "inheritors_of",
        "file_summary", "interfaces",
    }
    if pattern not in allowed:
        raise ToolError(f"pattern 必须是以下之一: {sorted(allowed)}")
    return _call(
        "query.query_graph",
        repo,
        pattern=pattern,
        target=target,
        max_results=args.get("max_results", 100),
    )


def _graph_impact(args: dict, repo: Path) -> str:
    return _call(
        "query.get_impact_radius",
        repo,
        changed_files=_changed_files(args),
        max_depth=args.get("max_depth", 2),
        base=str(args.get("base", "HEAD~1") or "HEAD~1"),
    )


def _graph_review(args: dict, repo: Path) -> str:
    return _call(
        "review.detect_changes_func",
        repo,
        base=str(args.get("base", "HEAD~1") or "HEAD~1"),
        changed_files=_changed_files(args),
        include_source=bool(args.get("include_source", False)),
        max_depth=args.get("max_depth", 2),
    )


register(ToolSpec(
    name="graph_query",
    description="代码图谱查询（CRG）：按符号名查调用关系，pattern 可选 callers_of/callees_of/importers_of/references_to/tests_for/inheritors_of/file_summary 等。用于追踪调用链（能跨文件/跨模块，比 grep 更完整）",
    parameters={"type": "object", "properties": {
        "pattern": {"type": "string", "description": "查询类型，如 callers_of、callees_of、importers_of、tests_for"},
        "target": {"type": "string", "description": "符号名/限定名/文件路径"},
        "max_results": {"type": "integer", "description": "默认 100"},
    }, "required": ["pattern", "target"]},
    fn=_graph_query,
    examples=['{"name": "graph_query", "arguments": {"pattern": "callers_of", "target": "normalizeModelRef"}}'],
))

register(ToolSpec(
    name="graph_impact",
    description="代码图谱爆炸半径：给定变更文件清单，返回可能受影响的调用方/依赖/测试（跨调用链传播，2 跳默认）",
    parameters={"type": "object", "properties": {
        "changed_files": {"type": "array", "items": {"type": "string"}, "description": "变更文件清单；省略则自动按 git 检测"},
        "max_depth": {"type": "integer", "description": "传播跳数，默认 2"},
        "base": {"type": "string", "description": "diff 基线 ref，默认 HEAD~1"},
    }},
    fn=_graph_impact,
    examples=['{"name": "graph_impact", "arguments": {"changed_files": ["src/a.py", "src/b.ts"]}}'],
))

register(ToolSpec(
    name="graph_review",
    description="代码图谱风险审查：把变更映射到受影响函数/执行流/测试缺口，输出风险评分与优先审查项",
    parameters={"type": "object", "properties": {
        "base": {"type": "string", "description": "diff 基线 ref，默认 HEAD~1"},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "include_source": {"type": "boolean", "description": "是否附带源码片段，默认 false"},
        "max_depth": {"type": "integer", "description": "默认 2"},
    }},
    fn=_graph_review,
    examples=['{"name": "graph_review", "arguments": {"base": "<base_sha>"}}'],
))
