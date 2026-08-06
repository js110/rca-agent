"""分派：TYPE → 分析框架模板。"""

from __future__ import annotations

from .. import config

FRAMEWORKS = {
    "bugfix": "bugfix-analysis-framework.md",
    "feature": "feature-analysis-framework.md",
    "perf": "perf-analysis-framework.md",
    "refactor": "refactor-analysis-framework.md",
    "config": "chore-analysis-framework.md",
}


def framework_text(ptype: str) -> str | None:
    fname = FRAMEWORKS.get(ptype)
    if fname is None:
        return None
    return (config.PROMPTS_DIR / fname).read_text(encoding="utf-8")
