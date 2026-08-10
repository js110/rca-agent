"""管线编排：分类 → 分派 → 图谱（worktree 索引）→ 分析 → 报告。"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .. import config
from ..checkout import prepare
from ..llm import LLMClient
from ..mr import MRContext
from ..mr_prompt import render_mr_text
from ..report import extract_and_save
from ..repo import ensure_ref, merge_base, remote_web_url
from ..tools import graph_tool
from .analyze import run_analysis
from .classify import classify
from .dispatch import framework_text

log = logging.getLogger("rca.pipeline")


def run_pipeline(
    repo_url: str,
    base_ref: str,
    head_ref: str,
    title: str = "",
    description: str = "",
    ptype: str | None = None,
    workspace: Path | None = None,
    branch: str | None = None,
) -> dict:
    """执行完整管线，返回 {type, report, repo_path, duration}。

    branch 提供时（webhook 场景）走「每分支 worktree + 独立 codegraph 索引」方案，
    索引严格等于 head_ref 指向的 commit；失败由 checkout 模块自动回退单 clone。
    """
    t0 = time.time()
    llm = LLMClient()

    # A1: 准备可分析工作区（检出 head_ref；worktree 失败自动回退单 clone）
    pc = prepare(repo_url, head_ref, branch=branch, index=True, workspace=workspace)
    repo = pc.path
    log.info("checkout 就绪: %s (used_worktree=%s)", repo, pc.used_worktree)

    # A2: diff 口径用 merge-base，而非 base 分支最新 tip
    # （base 分支在本 PR 创建后可能有新提交，base.sha..head 会混入无关变更）
    if not ensure_ref(repo, base_ref):
        raise RuntimeError(f"无法获取 ref: {base_ref}")
    diff_base = base_ref
    mb = merge_base(repo, base_ref, head_ref)
    if mb and mb != base_ref:
        diff_base = mb
        log.info("base=%s 非 merge-base，改用 %s", base_ref[:10], mb[:10])

    mr = MRContext(
        repo_path=repo, base_ref=diff_base, head_ref=head_ref,
        title=title, description=description,
    )
    mr.collect()

    if ptype is None:
        ptype = classify(llm, mr)
    print(f"[classify] {ptype}")

    # A3: 图谱 warm-start 作用在分析工作区上（worktree 时即该分支的独立索引，
    # 保证图谱 == head_ref 的代码；单 clone 场景等价于原 base 行为）
    if config.CRG_AUTOBUILD:
        try:
            if graph_tool.crg_warm_start(repo, base_ref):
                log.info("warm-start 成功（图谱已就绪）")
            else:
                log.info("warm-start 失败，图谱工具将返回 unavailable")
        except Exception as exc:
            log.info("warm-start 异常: %s", exc)

    framework = framework_text(ptype)
    raw = run_analysis(llm, repo, render_mr_text(mr), framework, remote_web_url(repo))
    report, out = extract_and_save(raw, repo.name, base_ref, head_ref, ptype, repo_url)
    return {
        "type": ptype,
        "report": report,
        "report_file": str(out),
        "repo_path": str(repo),
        "duration": round(time.time() - t0, 1),
    }
