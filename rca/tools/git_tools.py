"""Git 类工具：gitLog / gitDiff / gitShow / gitGrep / gitBlame / gitPickaxe / gitShowStat。"""

from __future__ import annotations

import re
from pathlib import Path

from .. import config
from ..repo import run_git
from .base import ToolError, ToolSpec, register

LOCK_SUFFIXES = (
    ".lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "Cargo.lock", "composer.lock", "Gemfile.lock", "poetry.lock",
    "go.sum", "*.lock",
)


def _git(repo: Path, *args: str, timeout: int = 120) -> str:
    """跑 git 并返回 stdout;失败抛 ToolError(由 execute_tool 出口统一渲染)。"""
    proc = run_git(repo, *args, timeout=timeout)
    if proc.returncode != 0:
        raise ToolError(
            f"git {' '.join(args[:2])}... 失败: {proc.stderr.strip()[:2000]}"
        )
    return proc.stdout


def _is_lock_file(rel: str) -> bool:
    low = rel.lower()
    return (
        low.endswith((".lock", ".min.js", ".min.css"))
        or "lock" in low.split("/")[-1]
    )


# ---------- gitLog ----------

def _git_log(args: dict, repo: Path) -> str:
    cmd = ["log", "--date=short", "--pretty=format:%h %ad %an %s"]
    ref_range = str(args.get("ref_range", "") or "").strip()
    if ref_range:
        cmd.append(ref_range)
    if args.get("author"):
        cmd.append(f"--author={args['author']}")
    if args.get("since"):
        cmd.append(f"--since={args['since']}")
    if args.get("until"):
        cmd.append(f"--until={args['until']}")
    n = args.get("max_count", 30) or 30
    cmd += ["-n", str(min(max(n, 1), config.MAX_LOG_ENTRIES))]
    path = str(args.get("path", "") or "").strip()
    if path:
        cmd += ["--", path]
    return _git(repo, *cmd)


# ---------- gitDiff ----------

def _git_diff(args: dict, repo: Path) -> str:
    base = str(args.get("base_ref", "") or "").strip()
    head = str(args.get("head_ref", "") or "").strip()
    cmd = ["diff", base, head]
    path = str(args.get("path", "") or "").strip()
    if path:
        cmd += ["--", path]
    out = _git(repo, *cmd)
    if args.get("stat"):
        out = _git(repo, "diff", "--stat", base, head, *(["--", path] if path else [])) + "\n\n" + out
    return out


# ---------- gitShow ----------

def _git_show(args: dict, repo: Path) -> str:
    ref = str(args.get("ref", "") or "").strip()
    mode = str(args.get("mode", "diff") or "diff")
    if mode == "snapshot":
        path = str(args.get("path", "") or "").strip()
        if not path:
            raise ToolError("snapshot 模式需要 path 参数")
        return _git(repo, "show", f"{ref}:{path}")
    if mode == "files":
        return _git(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", ref)
    return _git(repo, "show", "--stat", "--date=short", ref)


# ---------- gitGrep ----------

def _git_grep(args: dict, repo: Path) -> str:
    pattern = str(args.get("pattern", "") or "").strip()
    cmd = ["grep", "-n", "-I", "-e", pattern]
    path = str(args.get("path", "") or "").strip()
    if path:
        cmd.append("--")
        cmd.append(path)
    out = _git(repo, *cmd)
    lines = []
    for line in out.splitlines():
        try:
            rel = line.split(":", 1)[0]
        except Exception:
            rel = ""
        if _is_lock_file(rel):
            continue
        lines.append(line)
    if len(lines) > config.MAX_GREP_MATCHES:
        return (
            f"命中 {len(lines)} 处（过多，仅展示前 {config.MAX_GREP_MATCHES}）:\n"
            + "\n".join(lines[: config.MAX_GREP_MATCHES])
        )
    if not lines:
        return f"无匹配: {pattern}"
    return "\n".join(lines)


# ---------- gitBlame ----------

_BLAME_RE = re.compile(r"^([0-9a-f^]+)\s+\((.*?)\)\s*(.*)$", re.S)


def _git_blame(args: dict, repo: Path) -> str:
    path = str(args.get("path", "") or "").strip()
    cmd = ["blame", "--date=short", "-w", "--"]
    start = args.get("start_line", 0) or 0
    end = args.get("end_line", 0) or 0
    if start:
        cmd += ["-L", f"{start},{end if end >= start else start}"]
    cmd.append(path)
    out = _git(repo, *cmd)
    groups: list[tuple[str, list[tuple[int, str]]]] = []
    cur_sha = None
    cur_lines: list[tuple[int, str]] = []
    meta: dict[str, tuple[str, str]] = {}

    for raw in out.splitlines():
        m = _BLAME_RE.match(raw)
        if not m:
            continue
        sha, inside, code = m.group(1), m.group(2), m.group(3)
        tokens = inside.split()
        if len(tokens) < 3:
            continue
        lineno, date = int(tokens[-1]), tokens[-2]
        author = " ".join(tokens[:-2])
        meta.setdefault(sha, (author, date))
        if sha != cur_sha:
            if cur_sha is not None:
                groups.append((cur_sha, cur_lines))
            cur_sha, cur_lines = sha, []
        cur_lines.append((lineno, code))
    if cur_sha is not None:
        groups.append((cur_sha, cur_lines))

    parts = [f"# git blame {path}（按 commit 分组）\n"]
    for sha, lines in groups:
        author, date = meta[sha]
        parts.append(f"commit {sha}  {author}  {date}")
        for lineno, code in lines:
            parts.append(f"  L{lineno}: {code}")
    return "\n".join(parts)


# ---------- gitPickaxe ----------

def _git_pickaxe(args: dict, repo: Path) -> str:
    pattern = str(args.get("pattern", "") or "").strip()
    cmd = [
        "log", "--oneline", "--date=short",
        "--pretty=format:%h %ad %an %s",
    ]
    ref_range = str(args.get("ref_range", "") or "").strip()
    if ref_range:
        cmd.append(ref_range)
    if args.get("string_mode"):
        cmd += ["-S", pattern]
    else:
        cmd += ["-G", pattern]
    path = str(args.get("path", "") or "").strip()
    if path:
        cmd += ["--", path]
    return _git(repo, *cmd)


# ---------- gitShowStat ----------

def _git_show_stat(args: dict, repo: Path) -> str:
    ref = str(args.get("ref", "") or "").strip()
    return _git(repo, "show", "--stat", "--date=short", "--format=%h %ad %an %s", ref)


register(ToolSpec(
    name="gitLog",
    description="提交历史，支持按文件/作者过滤（--pretty=短哈希 日期 作者 主题）",
    parameters={"type": "object", "properties": {
        "ref_range": {"type": "string", "description": "提交区间，如 base..head 或 <sha>"},
        "path": {"type": "string", "description": "只查该路径的历史"},
        "author": {"type": "string"},
        "since": {"type": "string", "description": "起始日期，如 2026-01-01"},
        "until": {"type": "string"},
        "max_count": {"type": "integer", "description": "最多条数，默认 30"},
    }},
    fn=_git_log,
    examples=['{"name": "gitLog", "arguments": {"ref_range": "base..head", "max_count": 50}}'],
))

register(ToolSpec(
    name="gitDiff",
    description="任意两个 ref 的代码差异（unified diff；可用 path 缩小到单文件）",
    parameters={"type": "object", "properties": {
        "base_ref": {"type": "string"},
        "head_ref": {"type": "string"},
        "path": {"type": "string", "description": "限定单文件"},
        "stat": {"type": "boolean", "description": "是否同时输出 --stat 统计"},
    }, "required": ["base_ref", "head_ref"]},
    fn=_git_diff,
    examples=['{"name": "gitDiff", "arguments": {"base_ref": "main", "head_ref": "feature/xxx"}}'],
))

register(ToolSpec(
    name="gitShow",
    description="查看 commit：mode=snapshot 看某 ref 下指定文件的快照内容；mode=diff 看该 commit 的完整改动；mode=files 只看改动的文件列表",
    parameters={"type": "object", "properties": {
        "ref": {"type": "string"},
        "mode": {"type": "string", "enum": ["snapshot", "diff", "files"], "description": "默认 diff"},
        "path": {"type": "string", "description": "snapshot 模式必填"},
    }, "required": ["ref"]},
    fn=_git_show,
    examples=['{"name": "gitShow", "arguments": {"ref": "<sha>", "mode": "snapshot", "path": "src/foo.py"}}'],
))

register(ToolSpec(
    name="gitGrep",
    description="文本/正则搜索（排除锁文件、压缩产物、二进制）",
    parameters={"type": "object", "properties": {
        "pattern": {"type": "string", "description": "正则表达式"},
        "path": {"type": "string", "description": "限定搜索目录/文件"},
    }, "required": ["pattern"]},
    fn=_git_grep,
    examples=['{"name": "gitGrep", "arguments": {"pattern": "normalizeModelRef", "path": "src"}}'],
))

register(ToolSpec(
    name="gitBlame",
    description="代码演进历史：指定文件行范围的归属（按 commit 分组输出：commit + 作者 + 日期 + 行号）",
    parameters={"type": "object", "properties": {
        "path": {"type": "string"},
        "start_line": {"type": "integer"},
        "end_line": {"type": "integer"},
    }, "required": ["path"]},
    fn=_git_blame,
    examples=['{"name": "gitBlame", "arguments": {"path": "src/foo.py", "start_line": 40, "end_line": 60}}'],
))

register(ToolSpec(
    name="gitPickaxe",
    description="按代码内容定位引入/删除该内容的 commit（默认正则 -G；string_mode=true 时精确字符串 -S）",
    parameters={"type": "object", "properties": {
        "pattern": {"type": "string"},
        "ref_range": {"type": "string", "description": "限定历史区间，如 base..head"},
        "path": {"type": "string"},
        "string_mode": {"type": "boolean"},
    }, "required": ["pattern"]},
    fn=_git_pickaxe,
    examples=['{"name": "gitPickaxe", "arguments": {"pattern": "d3modelItemId"}}'],
))

register(ToolSpec(
    name="gitShowStat",
    description="commit 修改文件统计（文件 + 增删行数）",
    parameters={"type": "object", "properties": {
        "ref": {"type": "string"},
    }, "required": ["ref"]},
    fn=_git_show_stat,
    examples=['{"name": "gitShowStat", "arguments": {"ref": "<sha>"}}'],
))
