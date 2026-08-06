"""CLI：analyze / classify / serve 三个子命令。"""

from __future__ import annotations

import argparse
import json
import sys

from . import config
from .llm import LLMClient
from .mr import MRContext
from .pipeline import run_pipeline
from .pipeline.classify import classify
from .repo import checkout, ensure_ref, ensure_repo


def _cmd_analyze(args: argparse.Namespace) -> int:
    result = run_pipeline(
        repo_url=args.repo,
        base_ref=args.base,
        head_ref=args.head,
        title=args.title or "",
        description=args.desc or "",
        ptype=args.type,
    )
    print(result["report"])
    print(f"\n[report] 已保存: {result['report_file']}")
    print(f"[done] type={result['type']} duration={result['duration']}s")
    return 0


def _cmd_classify(args: argparse.Namespace) -> int:
    llm = LLMClient()
    repo = ensure_repo(args.repo)
    for ref in (args.base, args.head):
        if not ensure_ref(repo, ref):
            print(f"[error] 无法获取 ref: {ref}", file=sys.stderr)
            return 1
    checkout(repo, args.head)
    mr = MRContext(repo_path=repo, base_ref=args.base, head_ref=args.head,
                   title=args.title or "", description=args.desc or "")
    print(classify(llm, mr))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app

    uvicorn.run(
        create_app(),
        host=args.host or config.SERVER_HOST,
        port=args.port or config.SERVER_PORT,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rca", description="RCA Agent：MR 根因分析智能体"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="完整分析：分类 → 分派 → 工具循环 → 报告")
    p_analyze.add_argument("--repo", required=True, help="仓库 URL 或本地路径")
    p_analyze.add_argument("--base", required=True, help="基线 ref（如 main 或 base_sha）")
    p_analyze.add_argument("--head", required=True, help="变更 ref（如 PR 分支/head_sha）")
    p_analyze.add_argument("--title", default="")
    p_analyze.add_argument("--desc", default="")
    p_analyze.add_argument("--type", default=None,
                           help="跳过分类，强制指定类型")
    p_analyze.set_defaults(func=_cmd_analyze)

    p_classify = sub.add_parser("classify", help="只做分类")
    p_classify.add_argument("--repo", required=True)
    p_classify.add_argument("--base", required=True)
    p_classify.add_argument("--head", required=True)
    p_classify.add_argument("--title", default="")
    p_classify.add_argument("--desc", default="")
    p_classify.set_defaults(func=_cmd_classify)

    p_serve = sub.add_parser("serve", help="启动 webhook 服务")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
