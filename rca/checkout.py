"""Checkout 准备模块:把仓库准备成「可分析工作区」(检出 head_sha,可选带索引)。

决策与生命周期集中于此:
- worktree 方案(每分支独立 worktree + codegraph 索引,索引严格等于 head_sha)
- 单 clone 方案(无索引 / 未给分支 / worktree 失败自动回退)
- 清理(PR 关闭时移除该分支的 worktree + 索引)

正确性链条:事件里钉死 head_sha → 检出 → rev-parse HEAD == head_sha → 索引同步;
worktree 失败回退单 clone 后同样校验,失败才抛 CheckoutError。

外部只看到 prepare / cleanup 两个入口;worktree 布局是模块私有知识。
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import config
from .codegraph import (
    FileLock,
    codegraph_available,
    ensure_base_index,
    seed_index,
    sync_index,
)
from .repo import checkout, ensure_ref, ensure_repo, repo_name, run_git

log = logging.getLogger("rca.checkout")

WT_SUFFIX = "-wt"
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")


class CheckoutError(RuntimeError):
    """仓库无法准备成可分析状态(ref 不可用 / 检出失败 / HEAD 校验失败)。"""


@dataclass
class PreparedCheckout:
    path: Path
    used_worktree: bool


# 索引提供者:给定 (base, branch, head_sha) 返回就绪的 worktree 路径;失败抛异常。
# 这是测试注入点——传一个永远失败的 fake 即可覆盖回退路径。
IndexProvider = Callable[[Path, str, str], Path]


# ---------------------------------------------------------------------------
# 布局(模块私有知识,调用方不需要知道)
# ---------------------------------------------------------------------------

def sanitize_branch(branch: str) -> str:
    safe = _SANITIZE_RE.sub("_", branch).strip("._")
    return safe[:120] or "branch"


def worktrees_root(base: Path) -> Path:
    return base.parent / f"{base.name}{WT_SUFFIX}"


def branch_wt_dir(base: Path, branch: str) -> Path:
    return worktrees_root(base) / sanitize_branch(branch)


def _wt_lock_path(wt_root: Path, branch: str) -> Path:
    """该分支的跨进程锁文件——prepare 与 cleanup 必须用同一路径。"""
    return wt_root / f".{sanitize_branch(branch)}.lock"


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def prepare(
    repo_url: str,
    head_sha: str,
    branch: str | None = None,
    index: bool = False,
    workspace: Path | None = None,
    provider: IndexProvider | None = None,
) -> PreparedCheckout:
    """把仓库准备成可分析状态,返回 PreparedCheckout(path, used_worktree)。

    - branch + index:尝试 worktree 方案,任何一步失败自动回退单 clone
    - 其余(无索引场景,如 classify):单 clone 检出
    - 两种方案检出后都校验 HEAD == head_sha,仍失败抛 CheckoutError
    """
    base = ensure_repo(repo_url, workspace)
    if not ensure_ref(base, head_sha):
        raise CheckoutError(f"无法获取 ref: {head_sha}")

    prov = provider or _prepare_worktree
    if index and branch:
        try:
            wt = prov(base, branch, head_sha)
            log.info("worktree 就绪: %s @ %s", wt, head_sha[:10])
            return PreparedCheckout(path=wt, used_worktree=True)
        except Exception as exc:
            log.warning("worktree 准备失败，回退单 clone 检出: %s", exc)

    _single_checkout(base, head_sha)
    return PreparedCheckout(path=base, used_worktree=False)


def _remove_wt(base: Path, wt: Path) -> None:
    """移除单个 worktree:git worktree remove --force + 目录兜底清理。"""
    if (wt / ".git").exists():
        run_git(base, "worktree", "remove", "--force", str(wt), timeout=300)
    shutil.rmtree(wt, ignore_errors=True)


def cleanup(repo_url: str, branch: str, workspace: Path | None = None) -> None:
    """PR 关闭/合并后清理该分支的 worktree + 索引(best-effort)。

    用纯字符串解析仓库名定位 base(不触发 git/fetch),仓库从未克隆过则 no-op。
    """
    try:
        base = (workspace or config.WORKSPACE) / repo_name(repo_url)
        if not (base / ".git").exists():
            return
        wt_root = worktrees_root(base)
        wt = branch_wt_dir(base, branch)
        with FileLock(_wt_lock_path(wt_root, branch)):
            _remove_wt(base, wt)
            run_git(base, "worktree", "prune")
        log.info("已清理分支 %s 的 worktree + 索引", branch)
    except Exception as exc:
        log.warning("清理 worktree 失败: %s", exc)


# ---------------------------------------------------------------------------
# 内部:单 clone 检出
# ---------------------------------------------------------------------------

def _single_checkout(base: Path, head_sha: str) -> None:
    try:
        checkout(base, head_sha)
    except RuntimeError as exc:
        raise CheckoutError(str(exc)) from exc
    _verify_head(base, head_sha)


def _verify_head(repo: Path, head_sha: str) -> None:
    head = run_git(repo, "rev-parse", "HEAD", timeout=60).stdout.strip()
    if head != head_sha:
        raise CheckoutError(
            f"检出后 HEAD={head[:12]} != 期望 {head_sha[:12]}，拒绝分析"
        )


# ---------------------------------------------------------------------------
# 内部:worktree 方案(默认索引提供者)
# ---------------------------------------------------------------------------

def _prepare_worktree(base: Path, branch: str, head_sha: str) -> Path:
    if not codegraph_available():
        raise CheckoutError("codegraph 未启用或二进制不可用")
    wt_root = worktrees_root(base)
    wt = branch_wt_dir(base, branch)
    wt_root.mkdir(parents=True, exist_ok=True)

    with FileLock(_wt_lock_path(wt_root, branch)):
        # 1) 检出目标 SHA(首建 worktree,此后同分支只增量切换)
        if not (wt / ".git").exists():
            proc = run_git(base, "worktree", "add", "--detach", str(wt), head_sha)
            if proc.returncode != 0:
                raise CheckoutError(
                    f"worktree add {branch}@{head_sha[:10]} 失败: "
                    f"{proc.stderr.strip()[:2000]}"
                )
        else:
            proc = run_git(wt, "checkout", "-f", "--detach", head_sha)
            if proc.returncode != 0:
                raise CheckoutError(
                    f"worktree checkout {head_sha[:10]} 失败: "
                    f"{proc.stderr.strip()[:2000]}"
                )

        # 2) 校验:HEAD 必须 == head_sha
        _verify_head(wt, head_sha)

        # 3) 播种 + 同步索引(播种一次,此后 sync 增量)
        ensure_base_index(base)
        seed_index(base, wt)
        sync_index(wt)

        _prune_old(wt_root, base)
    return wt


def _prune_old(wt_root: Path, base: Path) -> None:
    """保留最近 N 个 worktree,其余清理(防止长期积累占磁盘)。"""
    dirs = [d for d in wt_root.iterdir() if d.is_dir()]
    dirs = sorted(dirs, key=lambda d: d.stat().st_mtime, reverse=True)
    for d in dirs[config.CODEGRAPH_WT_MAX_COUNT:]:
        log.info("清理过期 worktree: %s", d.name)
        _remove_wt(base, d)
    run_git(base, "worktree", "prune")
