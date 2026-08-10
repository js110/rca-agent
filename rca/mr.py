"""MR 证据收集：变更文件 / 提交日志 / diff / 统计等仓库事实。

只负责从 git 收集结构化证据，不含任何提示词/渲染逻辑；
把证据组装成给 LLM 的 MR 上下文文本见 mr_prompt 模块（提示词渲染）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .repo import run_git


def _git(repo: Path, *args: str, timeout: int = 120) -> str:
    """跑 git 并返回 stdout;失败返回错误串(不抛,让证据字段保留可读内容)。"""
    proc = run_git(repo, *args, timeout=timeout)
    if proc.returncode != 0:
        return f"[git error] {proc.stderr.strip()[:1000]}"
    return proc.stdout


@dataclass
class MRContext:
    """MR 的事实集合：仓库定位 + 输入信息（标题/描述）+ 收集到的证据。"""

    repo_path: Path
    base_ref: str
    head_ref: str
    title: str = ""
    description: str = ""
    changed_files: str = ""
    commit_log: str = ""
    diff: str = ""
    file_stats: str = ""
    _collected: bool = field(default=False, init=False)

    def collect(self) -> "MRContext":
        if self._collected:
            return self
        repo, base, head = self.repo_path, self.base_ref, self.head_ref
        self.commit_log = _git(repo, "log", "--date=short",
                               "--pretty=format:%h %ad %an %s", f"{base}..{head}")
        self.file_stats = _git(repo, "diff", "--stat", base, head)
        self.changed_files = _git(repo, "diff", "--name-only", base, head)
        diff = _git(repo, "diff", base, head)
        if len(diff) > config.MAX_DIFF_CHARS:
            diff = (
                diff[: config.MAX_DIFF_CHARS]
                + f"\n...[diff 过长，已截断，共 {len(diff)} 字符，可用 gitDiff 工具按文件查看]"
            )
        self.diff = diff
        self._collected = True
        return self
