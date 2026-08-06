"""文件类工具：read、glob（限制在仓库目录内）。"""

from __future__ import annotations

from pathlib import Path

from .base import ToolSpec, register

MAX_MATCHES = 500


def _safe_path(repo: Path, rel: str) -> Path:
    p = (repo / rel).resolve()
    if not p.is_relative_to(repo.resolve()):
        raise ValueError(f"路径越界，只允许访问仓库内文件: {rel}")
    return p


def _read(args: dict, repo: Path) -> str:
    path = str(args.get("path", "")).strip()
    if not path:
        return "[tool error] 缺少参数: path"
    target = _safe_path(repo, path)
    if not target.is_file():
        return f"[tool error] 文件不存在或不是文件: {path}"
    text = target.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    start = int(args.get("start_line", 1) or 1)
    end = int(args.get("end_line", 0) or 0) or len(lines)
    start = max(1, start)
    end = min(len(lines), max(start, end))
    numbered = [f"{i:>6}: {lines[i - 1]}" for i in range(start, end + 1)]
    head = f"# {path}  L{start}-L{end} / 共 {len(lines)} 行\n"
    return head + "\n".join(numbered)


def _glob(args: dict, repo: Path) -> str:
    pattern = str(args.get("pattern", "")).strip()
    base_rel = str(args.get("path", ".") or ".")
    if not pattern:
        return "[tool error] 缺少参数: pattern"
    base = _safe_path(repo, base_rel)
    if not base.is_dir():
        return f"[tool error] 目录不存在: {base_rel}"
    matches = []
    for p in base.glob(pattern):
        if ".git" in p.parts:
            continue
        if p.is_file():
            matches.append(str(p.relative_to(repo)).replace("\\", "/"))
    matches.sort()
    if len(matches) > MAX_MATCHES:
        return (
            f"匹配 {len(matches)} 个文件（过多，仅展示前 {MAX_MATCHES}）:\n"
            + "\n".join(matches[:MAX_MATCHES])
        )
    if not matches:
        return f"无匹配文件: {pattern}"
    return "\n".join(matches)


register(ToolSpec(
    name="read",
    description="读取文件内容，支持行范围分段（行号从 1 开始，含端点）",
    parameters={"type": "object", "properties": {
        "path": {"type": "string", "description": "仓库内相对路径，如 src/foo.py"},
        "start_line": {"type": "integer", "description": "起始行（可选，默认 1）"},
        "end_line": {"type": "integer", "description": "结束行（可选，默认到文件尾）"},
    }, "required": ["path"]},
    fn=_read,
    examples=['{"name": "read", "arguments": {"path": "src/foo.py", "start_line": 40, "end_line": 80}}'],
))

register(ToolSpec(
    name="glob",
    description="通配符匹配文件路径（相对仓库根，排除 .git）",
    parameters={"type": "object", "properties": {
        "pattern": {"type": "string", "description": "通配符模式，如 **/*.py"},
        "path": {"type": "string", "description": "搜索基准目录（可选，默认仓库根）"},
    }, "required": ["pattern"]},
    fn=_glob,
    examples=['{"name": "glob", "arguments": {"pattern": "**/*service*.py"}}'],
))
