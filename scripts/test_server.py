"""Webhook 服务测试：签名校验、事件路由、健康检查。"""
import hashlib
import hmac
import sys

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from rca import config
from rca.server import create_app

SECRET = "test-secret"
config.WEBHOOK_SECRET = SECRET

app = create_app()
client = TestClient(app)


def sig(payload: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()


def pr_payload() -> dict:
    return {
        "action": "opened",
        "number": 7,
        "pull_request": {
            "title": "fix precision",
            "body": "修复 float 精度",
            "number": 7,
            "head": {"sha": "9e895710bab318f493b4a54aeb97ee209c1eb7c7",
                     "ref": "bugfix/precision"},
            "base": {"sha": "6ad7e2e27c32189b14483a970d8e78944704689b",
                     "ref": "main"},
        },
        "repository": {"clone_url": "https://github.com/js110/demo.git",
                       "full_name": "js110/demo"},
    }


import json

body = json.dumps(pr_payload()).encode()

r = client.get("/health")
assert r.status_code == 200 and r.json()["status"] == "ok", r.text

# 签名错误 → 400
r = client.post("/webhook/github", content=body,
                headers={"X-GitHub-Event": "pull_request",
                         "X-Hub-Signature-256": "sha256=bad"})
assert r.status_code == 400, r.text

# 无 secret 配置时放行 + 正确签名
r = client.post("/webhook/github", content=body,
                headers={"X-GitHub-Event": "pull_request",
                         "X-Hub-Signature-256": sig(body)})
assert r.status_code == 200, r.text
assert r.json()["status"] == "accepted", r.text

# 非 PR 事件 → ignored
r = client.post("/webhook/github", content=json.dumps({"action": "pushed"}).encode(),
                headers={"X-GitHub-Event": "push",
                         "X-Hub-Signature-256": sig(json.dumps({"action": "pushed"}).encode())})
assert r.json()["status"] == "ignored", r.text

# closed 在 CLOSE_ACTIONS 中：被接受（触发后台 worktree 清理）
p = pr_payload()
p["action"] = "closed"
r = client.post("/webhook/github", content=json.dumps(p).encode(),
                headers={"X-GitHub-Event": "pull_request",
                         "X-Hub-Signature-256": sig(json.dumps(p).encode())})
assert r.json()["status"] == "accepted", r.text

print("PASS  server e2e")
