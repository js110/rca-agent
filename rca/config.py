"""集中配置：全部从环境变量读取，支持 .env 文件。"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"


def _get(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


# LLM
OPENAI_API_KEY = _get("RCA_OPENAI_API_KEY") or _get("OPENAI_API_KEY")
OPENAI_BASE_URL = (
    _get("RCA_OPENAI_BASE_URL") or _get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
)
MODEL = _get("RCA_MODEL", "o3-mini")
MAX_TOKENS = _get("RCA_MAX_TOKENS")
REASONING_EFFORT = _get("RCA_REASONING_EFFORT")

# 运行参数
MAX_ITERATIONS = int(_get("RCA_MAX_ITERATIONS", "30"))
MAX_TOOL_OUTPUT = int(_get("RCA_MAX_TOOL_OUTPUT", "40000"))
MAX_DIFF_CHARS = int(_get("RCA_MAX_DIFF_CHARS", "30000"))
WORKSPACE = Path(_get("RCA_WORKSPACE", str(BASE_DIR / "workspace")))
REPORT_DIR = Path(_get("RCA_REPORT_DIR", str(BASE_DIR / "reports")))
STATE_DB = Path(_get("RCA_STATE_DB", str(BASE_DIR / "state.db")))
GIT_BINARY = _get("RCA_GIT_BINARY", "git")
MAX_GREP_MATCHES = int(_get("RCA_MAX_GREP_MATCHES", "500"))
MAX_LOG_ENTRIES = int(_get("RCA_MAX_LOG_ENTRIES", "100"))
CRG_AUTOBUILD = _get("RCA_CRG_AUTOBUILD", "1") in ("1", "true", "yes", "on")

# Webhook / GitHub
WEBHOOK_SECRET = _get("RCA_WEBHOOK_SECRET")
GITHUB_TOKEN = _get("RCA_GITHUB_TOKEN")
SERVER_HOST = _get("RCA_SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(_get("RCA_SERVER_PORT", "8000"))
