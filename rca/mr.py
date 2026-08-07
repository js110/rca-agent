"""MR 上下文收集：标题/描述/变更文件统计/提交日志/diff，组装「节省上下文」section。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .safety import UNTRUSTED_DECLARATION


def _git(repo: Path, *args: str, timeout: int = 120) -> str:
    proc = subprocess.run(
        [config.GIT_BINARY, "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        return f"[git error] {proc.stderr.strip()[:1000]}"
    return proc.stdout


@dataclass
class MRContext:
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

    def text(self) -> str:
        self.collect()
        return UNTRUSTED_DECLARATION + f"""## MR 信息

- 标题: {self.title or '(无)'}
- 描述: {self.description or '(无)'}
- 基线(base): {self.base_ref}
- 变更(head): {self.head_ref}

## 节省上下文（已收集，无需用 gitPickaxe / gitBlame 重复拉取）

### 变更文件（git diff --stat {self.base_ref}..{self.head_ref}）
{self.file_stats or '(空)'}

### 变更文件清单
{self.changed_files or '(空)'}

### 提交日志（base..head）
{self.commit_log or '(空)'}

### 完整 diff（截断上限 {config.MAX_DIFF_CHARS} 字符）
{self.diff or '(空)'}
"""
