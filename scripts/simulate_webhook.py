"""模拟 GitHub webhook 投递（本地测试用）：构造带签名 payload → POST 本地服务。"""
import hashlib
import hmac
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from rca import config
from dotenv import load_dotenv
load_dotenv()

SECRET = config.WEBHOOK_SECRET
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/webhook/github"

payload = {
    "action": "opened",
    "number": int(sys.argv[4]) if len(sys.argv) > 4 else 9999,
    "pull_request": {
        "title": sys.argv[5] if len(sys.argv) > 5 else "(simulated)",
        "body": sys.argv[6] if len(sys.argv) > 6 else "",
        "number": int(sys.argv[4]) if len(sys.argv) > 4 else 9999,
        "head": {"sha": sys.argv[3]},
        "base": {"sha": sys.argv[2]},
    },
    "repository": {
        "clone_url": "https://github.com/js110/rca-agent.git",
        "full_name": "js110/rca-agent",
    },
}

body = json.dumps(payload).encode()
sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
r = httpx.post(
    URL,
    content=body,
    headers={
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": sig,
        "Content-Type": "application/json",
    },
    timeout=30,
)
print(r.status_code, r.text)
