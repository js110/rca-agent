"""仓库管理：克隆 / 增量更新 / checkout 到指定 ref。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import config


def run_git(repo: Path, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        [config.GIT_BINARY, "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )


def is_url(s: str) -> bool:
    return "://" in s or s.startswith("git@") or s.startswith("ssh://")


def repo_name(repo_url: str) -> str:
    name = repo_url.rstrip("/\\").split("/")[-1].split("\\")[-1]
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
        run_git(dest, "fetch", "origin", "--prune", "--tags")
    return dest


def ensure_ref(repo: Path, ref: str) -> bool:
    """确保 ref（常为 sha）本地可用；远程仓库尝试 fetch 单 sha。"""
    if run_git(repo, "cat-file", "-e", f"{ref}^{{commit}}").returncode == 0:
        return True
    if run_git(repo, "remote").stdout.strip():
        proc = run_git(repo, "fetch", "origin", ref)
        if proc.returncode == 0:
            return True
    return False


def remote_web_url(repo: Path) -> str | None:
    """origin 远程地址 → https 网页根 URL（如 https://github.com/js110/rca-agent）；
    无法解析（本地仓库/无远程）返回 None。"""
    proc = run_git(repo, "remote", "get-url", "origin")
    if proc.returncode != 0:
        return None
    url = proc.stdout.strip()
    if not url:
        return None
    if url.startswith("git@"):
        url = "https://" + url[4:].replace(":", "/", 1)
    elif url.startswith("ssh://"):
        url = "https://" + url[len("ssh://"):]
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    if not url.startswith(("https://", "http://")):
        return None
    return url


def merge_base(repo: Path, a: str, b: str) -> str | None:
    """a、b 的共同祖先 sha；无法计算时返回 None。"""
    proc = run_git(repo, "merge-base", a, b)
    if proc.returncode != 0:
        return None
    lines = proc.stdout.strip().splitlines()
    return lines[0] if lines else None


def checkout(repo: Path, ref: str) -> None:
    proc = run_git(repo, "checkout", "-f", "--detach", ref)
    if proc.returncode != 0:
        raise RuntimeError(f"checkout {ref} 失败: {proc.stderr.strip()[:2000]}")
