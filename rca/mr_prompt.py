"""MR 提示词渲染：把 MR 证据组装成给 LLM 的「MR 上下文」文本。

与 mr 模块（证据收集）分层：渲染格式/声明措辞改动只动这里，不碰 git 收集；
渲染输入是 MRContext 的结构化字段，输出是单一文本。
"""

from __future__ import annotations

from . import config
from .mr import MRContext
from .safety import UNTRUSTED_DECLARATION


def render_mr_text(mr: MRContext) -> str:
    """渲染完整 MR 上下文（不可信数据声明 + MR 信息 + 已收集的证据）。"""
    mr.collect()
    return UNTRUSTED_DECLARATION + f"""## MR 信息

- 标题: {mr.title or '(无)'}
- 描述: {mr.description or '(无)'}
- 基线(base): {mr.base_ref}
- 变更(head): {mr.head_ref}

## 节省上下文（已收集，无需用 gitPickaxe / gitBlame 重复拉取）

### 变更文件（git diff --stat {mr.base_ref}..{mr.head_ref}）
{mr.file_stats or '(空)'}

### 变更文件清单
{mr.changed_files or '(空)'}

### 提交日志（base..head）
{mr.commit_log or '(空)'}

### 完整 diff（截断上限 {config.MAX_DIFF_CHARS} 字符）
{mr.diff or '(空)'}
"""
