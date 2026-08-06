"""管线编排：分类 → 分派 → 图谱 warm-start → 分析 → 报告。"""

from __future__ import annotations

import time
from pathlib import Path

from .. import config
from ..llm import LLMClient
from ..mr import MRContext
from ..report import extract
from ..repo import checkout, ensure_ref, ensure_repo
from ..tools import graph_tool
from .analyze import run_analysis
from .classify import classify
from .dispatch import framework_text


def run_pipeline(
    repo_url: str,
    base_ref: str,
    head_ref: str,
    title: str = "",
    description: str = "",
    ptype: str | None = None,
    workspace: Path | None = None,
) -> dict:
    """执行完整管线，返回 {type, report, repo_path, duration}。"""
    t0 = time.time()
    llm = LLMClient()
    repo = ensure_repo(repo_url, workspace)

    for ref in (base_ref, head_ref):
        if not ensure_ref(repo, ref):
            raise RuntimeError(f"无法获取 ref: {ref}")
    checkout(repo, head_ref)

    mr = MRContext(
        repo_path=repo, base_ref=base_ref, head_ref=head_ref,
        title=title, description=description,
    )
    mr.collect()

    if ptype is None:
        ptype = classify(llm, mr)
    print(f"[classify] {ptype}")

    if config.CRG_AUTOBUILD:
        try:
            if graph_tool.crg_warm_start(repo, base_ref):
                print("[graph] warm-start 成功（图谱已就绪）")
            else:
                print("[graph] warm-start 失败，图谱工具将返回 unavailable")
        except Exception as exc:
            print(f"[graph] warm-start 异常: {exc}")

    framework = framework_text(ptype)
    raw = run_analysis(llm, repo, mr.text(), framework)
    report = extract(raw)

    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = config.REPORT_DIR / f"{repo.name}-{head_ref[:10]}.md"
    out.write_text(
        f"# RCA Report\n\n- repo: {repo_url}\n- type: {ptype}\n"
        f"- base: {base_ref}\n- head: {head_ref}\n\n---\n\n{report}",
        encoding="utf-8",
    )
    return {
        "type": ptype,
        "report": report,
        "report_file": str(out),
        "repo_path": str(repo),
        "duration": round(time.time() - t0, 1),
    }
