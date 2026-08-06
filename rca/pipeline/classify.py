"""分类任务：根据 MR 信息输出一行 TYPE。"""

from __future__ import annotations

import re

from .. import config
from ..llm import LLMClient
from ..mr import MRContext

VALID_TYPES = {"bugfix", "feature", "refactor", "perf", "config", "other"}


def _template_parts() -> tuple[str, str]:
    """按「## User Message」切分：前为 system，后为 user 模板。"""
    text = (config.PROMPTS_DIR / "pr-classification-template.md").read_text(
        encoding="utf-8"
    )
    marker = "## User Message"
    if marker in text:
        system, user = text.split(marker, 1)
        return system.strip(), user.strip()
    return text.strip(), ""


def classify(llm: LLMClient, mr: MRContext) -> str:
    system, user_template = _template_parts()
    user = user_template + "\n\n" + mr.text()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    for attempt in range(2):
        out = llm.chat(messages, max_tokens=512)
        m = re.search(r"TYPE\s*[:：]\s*([A-Za-z_]+)", out or "")
        if m and m.group(1).lower() in VALID_TYPES:
            return m.group(1).lower()
        print(f"[warn] 分类输出无法解析: {out!r}，重试…")
        messages.append({"role": "assistant", "content": out or "(empty)"})
        messages.append(
            {"role": "user", "content": "输出不符合格式。只输出一行，形如：TYPE: bugfix"}
        )
    print("[warn] 分类两次均失败，回退为 bugfix")
    return "bugfix"
