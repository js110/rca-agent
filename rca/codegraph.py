"""CodeGraph 索引原语:CLI 封装 + base 索引的 init / 播种 / 同步。

只管「索引怎么建、怎么拷、怎么对账」;worktree 的生命周期决策、回退与清理
见 checkout 模块(Checkout 准备模块)。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import config

log = logging.getLogger("rca.codegraph")

_inproc_locks: dict[str, threading.Lock] = {}
_inproc_locks_guard = threading.Lock()


def _lock(fh) -> None:
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)


def _unlock(fh) -> None:
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


class FileLock:
    """跨进程文件锁(Windows msvcrt / POSIX fcntl),同进程内用 threading.Lock 兜底。"""

    def __init__(self, path: Path):
        self.path = path
        key = str(path)
        with _inproc_locks_guard:
            self._tl = _inproc_locks.setdefault(key, threading.Lock())

    def __enter__(self) -> "FileLock":
        self._tl.acquire()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+")
        self._fh.seek(0)
        try:
            _lock(self._fh)
        except Exception:
            self._fh.close()
            self._tl.release()
            raise
        return self

    def __exit__(self, *exc) -> None:
        try:
            self._fh.seek(0)
            _unlock(self._fh)
        finally:
            self._fh.close()
            self._tl.release()


def _codegraph_bin() -> str | None:
    """解析 codegraph 可执行文件绝对路径(Windows 下优先 .cmd/.exe,避免 .ps1 shim)。"""
    for name in (config.CODEGRAPH_BINARY,):
        p = shutil.which(name)
        if not p:
            continue
        if os.name == "nt" and p.lower().endswith(".ps1"):
            for alt in (p[:-4] + ".cmd", p[:-4] + ".exe", p[:-4] + ".bat"):
                if os.path.exists(alt):
                    return alt
            return None  # 只有 .ps1:CreateProcess 无法直接执行
        return p
    return None


def _codegraph(*args: str, cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    """codegraph CLI,非交互(stdin 关闭 + --quiet)。"""
    env = dict(os.environ)
    env.setdefault("CI", "1")
    bin_path = _codegraph_bin()
    if not bin_path:
        raise RuntimeError(f"codegraph 二进制不可用: {config.CODEGRAPH_BINARY}")
    return subprocess.run(
        [bin_path, *args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, stdin=subprocess.DEVNULL, env=env,
    )


def codegraph_available() -> bool:
    if not config.CODEGRAPH_ENABLED:
        return False
    return _codegraph_bin() is not None


# ---------------------------------------------------------------------------
# 索引:init / 播种 / 同步
# ---------------------------------------------------------------------------

def ensure_base_index(base: Path) -> None:
    """base 仓库首次 codegraph init(只做一次;锁保护防并发 init)。"""
    db = base / ".codegraph" / "codegraph.db"
    if db.is_file():
        return
    with FileLock(base.parent / f".{base.name}.init.lock"):
        if db.is_file():
            return
        t0 = time.time()
        proc = _codegraph("init", ".", cwd=base,
                          timeout=config.CODEGRAPH_INIT_TIMEOUT)
        if proc.returncode != 0:
            raise RuntimeError(
                f"codegraph init 失败 ({proc.returncode}): "
                f"{proc.stderr.strip()[:2000] or proc.stdout.strip()[:2000]}"
            )
        log.info("codegraph init 完成（%.1fs）", time.time() - t0)


def _copy_index_dir(base: Path, wt: Path, dirname: str) -> None:
    """把 base 的图谱目录播种到 worktree(连 -wal/-shm 一起拷,删 lock 文件)。"""
    src = base / dirname
    dst = wt / dirname
    if not src.is_dir() or dst.is_dir():
        return
    shutil.copytree(src, dst)
    for name in list(dst.iterdir()):
        if name.name.endswith(".lock") and name.is_file():
            name.unlink()
    if dirname == ".codegraph" and not (dst / "codegraph.db").is_file():
        log.warning("%s 播种后缺少 codegraph.db，sync 将重建", dst)


def seed_index(base: Path, wt: Path) -> None:
    """把 base 的图谱目录播种到 worktree(.codegraph + .code-review-graph)。"""
    _copy_index_dir(base, wt, ".codegraph")
    _copy_index_dir(base, wt, ".code-review-graph")


def sync_index(wt: Path) -> None:
    proc = _codegraph("sync", "--quiet", ".", cwd=wt,
                      timeout=config.CODEGRAPH_SYNC_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(
            f"codegraph sync 失败 ({proc.returncode}): "
            f"{proc.stderr.strip()[:2000] or proc.stdout.strip()[:2000]}"
        )
