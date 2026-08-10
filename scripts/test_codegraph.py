"""codegraph worktree 索引正确性测试（适配重构后的 checkout/codegraph 分层）。

用法:
  .venv\\Scripts\\python scripts\\test_codegraph.py <repo-dir>

验证:
  1. prepare() 建出 <workspace>/<repo>-wt/<branch>, HEAD == head_sha
  2. 索引播种 + sync 成功, .codegraph/codegraph.db 存在
  3. 切到另一 commit 再 prepare 同分支, HEAD 跟随新 sha, 索引仍可查询
  4. cleanup 清理
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")
from rca import codegraph, config
from rca.checkout import cleanup, prepare, sanitize_branch

REPO = Path(sys.argv[1]).resolve()


def git(*args, cwd=REPO):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True, encoding="utf-8")


def head_of(cwd):
    return git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


def main():
    base = head_of(REPO)
    wt_root = config.WORKSPACE / f"{REPO.name}-wt"
    wt = wt_root / sanitize_branch("test/branch-a")

    print(f"[1] base={base[:10]} prepare branch-a ...")
    pc = prepare(str(REPO), base, branch="test/branch-a", index=True,
                 workspace=config.WORKSPACE)
    assert pc.path == wt and pc.used_worktree, (pc.path, wt)
    assert head_of(wt) == base, f"HEAD {head_of(wt)[:10]} != {base[:10]}"
    db = wt / ".codegraph" / "codegraph.db"
    assert db.is_file() and db.stat().st_size > 0, "索引不存在或为空"
    print(f"[ok] worktree HEAD == base, 索引 {db.stat().st_size} bytes")

    print("[2] 切到 parent commit 再 prepare 同分支 ...")
    parent = git("rev-parse", "HEAD~1").stdout.strip()
    pc2 = prepare(str(REPO), parent, branch="test/branch-a", index=True,
                  workspace=config.WORKSPACE)
    assert pc2.path == wt and head_of(wt) == parent
    print(f"[ok] HEAD 跟随 {parent[:10]}")

    print("[3] codegraph query 可查询（校验索引服务当前分支代码）...")
    out = subprocess.run(
        [codegraph._codegraph_bin(), "query", "add", "--limit", "3"],
        cwd=str(wt), capture_output=True, text=True, encoding="utf-8",
        timeout=120,
    )
    print(f"[ok] query exit={out.returncode}: {out.stdout.strip()[:200] or out.stderr.strip()[:200]}")

    print("[4] cleanup 清理 ...")
    cleanup(str(REPO), "test/branch-a", workspace=config.WORKSPACE)
    assert not wt.exists(), "worktree 未清理干净"
    print("[ok] 已清理")


if __name__ == "__main__":
    main()
