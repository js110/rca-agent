"""Webhook 服务：接收 GitHub PR 事件 → 后台跑管线 → 报告回写评论。"""

from __future__ import annotations

import hashlib
import hmac
import logging

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from . import config
from .pipeline import run_pipeline

log = logging.getLogger("rca.server")

PR_ACTIONS = {"opened", "synchronize", "reopened", "edited", "ready_for_review"}
MAX_COMMENT = 60000  # GitHub 评论上限 65536，留余量


def _verify_signature(payload: bytes, sig_header: str | None) -> bool:
    if not config.WEBHOOK_SECRET:
        return True
    if not sig_header or not sig_header.startswith("sha256="):
        return False
    expected = hmac.new(
        config.WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(sig_header[7:], expected)


def _post_comment(full_name: str, pr_number: int, body: str) -> None:
    if not config.GITHUB_TOKEN:
        log.info("未配置 RCA_GITHUB_TOKEN，跳过评论回写")
        return
    url = f"https://api.github.com/repos/{full_name}/issues/{pr_number}/comments"
    if len(body) > MAX_COMMENT:
        body = body[:MAX_COMMENT] + "\n...[报告过长已截断]"
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {config.GITHUB_TOKEN}"},
        json={"body": body},
        timeout=30,
    )
    if resp.status_code >= 400:
        log.error("评论回写失败 %s: %s", resp.status_code, resp.text[:500])


def _handle_pr(payload: dict) -> None:
    try:
        pr = payload["pull_request"]
        repo = payload["repository"]
        head_sha = pr["head"]["sha"]
        base_sha = pr["base"]["sha"]
        title = pr.get("title") or ""
        body = pr.get("body") or ""
        result = run_pipeline(
            repo_url=repo["clone_url"],
            base_ref=base_sha,
            head_ref=head_sha,
            title=title,
            description=body,
        )
        report = result["report"]
        log.info("分析完成 type=%s duration=%ss", result["type"], result["duration"])
        header = (
            f"### RCA Agent 分析报告（类型: {result['type']}）\n\n"
            f"---\n\n"
        )
        _post_comment(repo["full_name"], pr["number"], header + report)
    except Exception as exc:
        log.exception("PR 分析失败: %s", exc)


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
        if action not in PR_ACTIONS:
            return {"status": "ignored", "action": action}
        background.add_task(_handle_pr, data)
        return {"status": "accepted", "pr": data.get("number"),
                "action": action}

    return app
