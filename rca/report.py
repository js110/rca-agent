"""报告输出模块：协议标记、提取与落盘。

工具循环以 <!--RCA-REPORT-START--> 起始输出报告，本模块负责报告域的全部知识：
- 协议标记（全项目唯一出处：analyze 检测、NUDGE、协议文本、提取都引用它）
- 从模型原始输出提取报告正文
- 保存为报告文件（文件名规则 + 头模板）
"""

from __future__ import annotations

from pathlib import Path

from . import config

REPORT_START = "<!--RCA-REPORT-START-->"


def extract(text: str) -> str:
    """从模型输出中提取 REPORT_START 之后的报告正文。"""
    idx = text.find(REPORT_START)
    if idx == -1:
        return text.strip()
    report = text[idx + len(REPORT_START):].strip()
    if report.endswith(REPORT_START):
        report = report[:-len(REPORT_START)].rstrip()
    return report


def extract_and_save(
    raw: str,
    repo_name: str,
    base_ref: str,
    head_ref: str,
    ptype: str,
    repo_url: str,
) -> tuple[str, Path]:
    """提取报告正文并落盘，返回 (报告正文, 文件路径)。

    文件名规则: {仓库名}-{head_sha[:10]}.md；头模板记录 repo/type/base/head 元数据。
    """
    report = extract(raw)
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = config.REPORT_DIR / f"{repo_name}-{head_ref[:10]}.md"
    out.write_text(
        f"# RCA Report\n\n- repo: {repo_url}\n- type: {ptype}\n"
        f"- base: {base_ref}\n- head: {head_ref}\n\n---\n\n{report}",
        encoding="utf-8",
    )
    return report, out
