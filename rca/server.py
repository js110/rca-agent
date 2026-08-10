"""Webhook 服务：接收 GitHub PR 事件 → 后台跑管线 → 报告回写评论。"""

from __future__ import annotations

import hashlib
import hmac
import logging
import threading

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from . import config, safety, state
from .checkout import cleanup as cleanup_worktree
from .pipeline import run_pipeline

log = logging.getLogger("rca.server")

PR_ACTIONS = {"opened", "synchronize", "reopened", "edited", "ready_for_review"}
CLOSE_ACTIONS = {"closed"}
MAX_COMMENT = 60000  # GitHub 评论上限 65536，留余量

# 按 (repo, branch) 串行化分析：同一分支并发 checkout 竞争由 worktree 文件锁兜底；
# 不同分支走不同 worktree，天然并行。
_branch_locks_guard = threading.Lock()
_branch_locks: dict[tuple[str, str], threading.Lock] = {}


def _branch_lock(full_name: str, branch: str) -> threading.Lock:
    with _branch_locks_guard:
        return _branch_locks.setdefault((full_name, branch), threading.Lock())


def _verify_signature(payload: bytes, sig_header: str | None) -> bool:
    if not config.WEBHOOK_SECRET:
        return True
    if not sig_header or not sig_header.startswith("sha256="):
        return False
    expected = hmac.new(
        config.WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(sig_header[7:], expected)


def _post_comment(
    full_name: str, pr_number: int, body: str, comment_id: int | None = None
) -> int | None:
    """发布/更新评论（sticky）。返回评论 id；失败返回 None。"""
    if not config.GITHUB_TOKEN:
        log.info("未配置 RCA_GITHUB_TOKEN，跳过评论回写")
        return None
    body = safety.redact_secrets(body)
    if len(body) > MAX_COMMENT:
        body = body[:MAX_COMMENT] + "\n...[报告过长已截断]"
    headers = {"Authorization": f"Bearer {config.GITHUB_TOKEN}"}
    create_url = (
        f"https://api.github.com/repos/{full_name}/issues/{pr_number}/comments"
    )
    if comment_id is not None:
        url = f"https://api.github.com/repos/{full_name}/issues/comments/{comment_id}"
        resp = httpx.patch(url, headers=headers, json={"body": body}, timeout=30)
        if resp.status_code == 404:
            resp = httpx.post(create_url, headers=headers,
                              json={"body": body}, timeout=30)
    else:
        resp = httpx.post(create_url, headers=headers, json={"body": body},
                          timeout=30)
    if resp.status_code >= 400:
        log.error("评论回写失败 %s: %s", resp.status_code, resp.text[:500])
        return None
    data = resp.json()
    return data.get("id")


def _cleanup_pr(payload: dict) -> None:
    """PR 关闭/合并：清理该分支的 codegraph worktree + 索引（best-effort）。

    布局是 checkout 模块的私有知识：这里只传 repo_url + branch，
    不会触发任何 git 操作（不 fetch）。
    """
    try:
        pr = payload["pull_request"]
        branch = pr["head"]["ref"]
        repo_url = payload["repository"]["clone_url"]
    except Exception as exc:
        log.warning("清理 worktree 失败（payload 不完整）: %s", exc)
        return
    cleanup_worktree(repo_url, branch)


def _handle_pr(payload: dict) -> None:
    pr = payload["pull_request"]
    repo = payload["repository"]
    full_name = repo["full_name"]
    pr_number = pr["number"]
    head_sha = pr["head"]["sha"]
    base_sha = pr["base"]["sha"]
    branch = pr["head"]["ref"]
    title = pr.get("title") or ""
    body = pr.get("body") or ""
    action = payload.get("action", "")

    if action in CLOSE_ACTIONS:
        _cleanup_pr(payload)
        return

    with _branch_lock(full_name, branch):
        st = state.get(full_name, pr_number)
        if st and st["head_sha"] == head_sha:
            log.info("跳过 %s #%d：head_sha %s 已分析过",
                     full_name, pr_number, head_sha[:10])
            return
        try:
            result = run_pipeline(
                repo_url=repo["clone_url"],
                base_ref=base_sha,
                head_ref=head_sha,
                title=title,
                description=body,
                branch=branch,
            )
        except Exception as exc:
            log.exception("PR 分析失败: %s", exc)
            return
        report = result["report"]
        log.info("分析完成 type=%s duration=%ss",
                 result["type"], result["duration"])
        header = (
            f"### RCA Agent 分析报告（类型: {result['type']}）\n\n"
            f"---\n\n"
        )
        comment_id = _post_comment(
            full_name, pr_number, header + report,
            comment_id=st["comment_id"] if st else None,
        )
        if comment_id is not None:
            state.put(full_name, pr_number, head_sha, comment_id)


def create_app() -> FastAPI:
    app = FastAPI(title="rca-agent", version="0.1.0")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/webhook/github")
    async def github_webhook(
        request: Request,
        background: BackgroundTasks,
        x_github_event: str | None = Header(default=None),
        x_hub_signature_256: str | None = Header(default=None),
    ):
        payload = await request.body()
        if not _verify_signature(payload, x_hub_signature_256):
            raise HTTPException(status_code=400, detail="signature 校验失败")
        if x_github_event != "pull_request":
            return {"status": "ignored", "event": x_github_event}
        data = await request.json()
        action = data.get("action", "")
        if action not in PR_ACTIONS and action not in CLOSE_ACTIONS:
            return {"status": "ignored", "action": action}
        background.add_task(_handle_pr, data)
        return {"status": "accepted", "pr": data.get("number"),
                "action": action}

    return app
