"""仓库管理：克隆 / 增量更新 / checkout 到指定 ref。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import config


def _git(repo: Path, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        [config.GIT_BINARY, "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )


def is_url(s: str) -> bool:
    return "://" in s or s.startswith("git@") or s.startswith("ssh://")


def repo_name(repo_url: str) -> str:
    name = repo_url.rstrip("/").split("/")[-1]
    return name[:-4] if name.endswith(".git") else name


def ensure_repo(repo_url: str, workspace: Path | None = None) -> Path:
    """URL → clone/增量 fetch；本地路径 → 原样返回。"""
    workspace = workspace or config.WORKSPACE
    if not is_url(repo_url):
        p = Path(repo_url).expanduser().resolve()
        if not (p / ".git").exists():
            raise FileNotFoundError(f"不是 git 仓库: {p}")
        return p
    workspace.mkdir(parents=True, exist_ok=True)
    dest = workspace / repo_name(repo_url)
    if not (dest / ".git").exists():
        proc = subprocess.run(
            [config.GIT_BINARY, "clone", "--quiet", repo_url, str(dest)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=1800,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"clone 失败: {proc.stderr.strip()[:2000]}")
    else:
        _git(dest, "fetch", "origin", "--prune", "--tags")
    return dest


def ensure_ref(repo: Path, ref: str) -> bool:
    """确保 ref（常为 sha）本地可用；远程仓库尝试 fetch 单 sha。"""
    if _git(repo, "cat-file", "-e", f"{ref}^{{commit}}").returncode == 0:
        return True
    if _git(repo, "remote").stdout.strip():
        proc = _git(repo, "fetch", "origin", ref)
        if proc.returncode == 0:
            return True
    return False


def merge_base(repo: Path, a: str, b: str) -> str | None:
    """a、b 的共同祖先 sha；无法计算时返回 None。"""
    proc = _git(repo, "merge-base", a, b)
    if proc.returncode != 0:
        return None
    lines = proc.stdout.strip().splitlines()
    return lines[0] if lines else None


def checkout(repo: Path, ref: str) -> None:
    proc = _git(repo, "checkout", "-f", "--detach", ref)
    if proc.returncode != 0:
        raise RuntimeError(f"checkout {ref} 失败: {proc.stderr.strip()[:2000]}")
