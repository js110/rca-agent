"""Checkout 准备模块测试：单 clone / 注入失败回退 / ref 不可用抛错 / cleanup。

用法: python scripts\test_checkout.py <repo> <head_sha>
worktree 成功路径仅当本机 codegraph 可用时执行(与 test_graph 同条件)。
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")

from rca import config
from rca.checkout import CheckoutError, cleanup, prepare
from rca.codegraph import codegraph_available


def fake_failing_provider(base, branch, head_sha):
    raise RuntimeError("fake 索引提供者故障")


def head_of(repo: Path) -> str:
    return subprocess.run(
        [config.GIT_BINARY, "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout.strip()


def main():
    repo_url = sys.argv[1]
    head = sys.argv[2]

    # 1) 单 clone 无索引
    pc = prepare(repo_url, head, index=False)
    assert pc.path.is_dir(), "单 clone 应返回仓库路径"
    assert not pc.used_worktree, "index=False 不应走 worktree"
    assert head_of(pc.path) == head, "检出 HEAD 应等于 head_sha"
    print("OK  单 clone 检出 + HEAD 校验")

    # 2) 注入 fake 索引提供者失败 → 自动回退单 clone
    pc = prepare(repo_url, head, branch="test-branch", index=True,
                 provider=fake_failing_provider)
    assert not pc.used_worktree, "worktree 失败应回退单 clone"
    assert head_of(pc.path) == head, "回退后 HEAD 仍应等于 head_sha"
    print("OK  注入失败 → 回退单 clone（回退后仍校验）")

    # 3) ref 不可用 → CheckoutError
    try:
        prepare(repo_url, "0" * 40, index=False)
        raise SystemExit("FAIL: 非法 ref 应抛 CheckoutError")
    except CheckoutError as exc:
        print(f"OK  CheckoutError: {str(exc)[:60]}…")

    # 4) cleanup no-op（从未建过 worktree 的分支）
    cleanup(repo_url, "never-created-branch")
    print("OK  cleanup no-op（无 worktree 不报错）")

    # 5) worktree 成功 + cleanup（仅当 codegraph 可用）
    if codegraph_available():
        pc = prepare(repo_url, head, branch="test-branch", index=True)
        assert pc.used_worktree, "codegraph 可用时应走 worktree"
        assert head_of(pc.path) == head, "worktree HEAD 应等于 head_sha"
        wt = pc.path
        cleanup(repo_url, "test-branch")
        assert not wt.exists(), "cleanup 应移除 worktree 目录"
        print("OK  worktree 成功 + cleanup 移除")
    else:
        print("SKIP worktree 成功（本机 codegraph 不可用）")

    print("PASS  checkout e2e")


if __name__ == "__main__":
    main()
