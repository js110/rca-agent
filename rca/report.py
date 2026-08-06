"""报告提取：只保留 <!--RCA-REPORT-START--> 之后的内容。"""

from __future__ import annotations

REPORT_START = "<!--RCA-REPORT-START-->"


def extract(text: str) -> str:
    idx = text.find(REPORT_START)
    if idx == -1:
        return text.strip()
    report = text[idx + len(REPORT_START):].strip()
    if report.endswith(REPORT_START):
        report = report[: -len(REPORT_START)].rstrip()
    return report
