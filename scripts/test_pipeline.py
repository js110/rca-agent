"""管线端到端测试：stub LLM 模拟模型，验证 分类→分派→工具循环→报告提取 全链路。"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from rca import config
from rca.checkout import prepare
from rca.mr import MRContext
from rca.mr_prompt import render_mr_text
from rca.pipeline.analyze import parse_tool_call
from rca.pipeline.classify import classify
from rca.pipeline.dispatch import framework_text
from rca.report import REPORT_START, extract, extract_and_save


class StubLLM:
    """预编程回复：分类 → bugfix；分析 → 先 gitDiff 一次，再输出报告。"""

    def __init__(self):
        self.turns = 0

    def chat(self, messages, max_tokens=None):
        self.turns += 1
        if "判断其类型" in messages[-1]["content"]:
            return "TYPE: bugfix"
        if self.turns == 2:
            return (
                'TOOL_CALL\n{"name": "gitDiff", "arguments": '
                '{"base_ref": "HEAD~1", "head_ref": "HEAD", "path": "calculator.py"}}'
            )
        return (
            REPORT_START
            + "\n## 1. 表象+影响\n浮点精度丢失。\n"
            + "## 2. 根因\nint() 强转截断（calculator.py:2）。\n"
            + "## 3. 最早起源 commit\n引入于 add 的 int 归一化提交。\n"
        )


def main():
    head = sys.argv[3]
    pc = prepare(sys.argv[1], head, index=False)
    repo = pc.path
    base = sys.argv[2]

    mr = MRContext(repo_path=repo, base_ref=base, head_ref="HEAD",
                   title="fix precision", description="")
    mr.collect()
    assert "calculator.py" in mr.changed_files, "changed_files 应包含 calculator.py"
    assert "diff --git" in mr.diff, "diff 应包含 unified diff"
    assert "preserve float precision" in mr.commit_log, "commit_log 应有记录"

    llm = StubLLM()
    ptype = classify(llm, mr)
    assert ptype == "bugfix", f"分类应为 bugfix，实际 {ptype}"

    fw = framework_text(ptype)
    assert "五问法" in fw, "bugfix 框架应加载"

    from rca.pipeline.analyze import run_analysis
    raw = run_analysis(llm, repo, render_mr_text(mr), fw)
    assert REPORT_START in raw, "分析输出应包含报告起始标记"
    assert "最早起源 commit" in raw, "报告应包含起源 commit 章节"

    report = extract(raw)
    assert "浮点精度丢失" in report
    assert "TOOL_CALL" not in report, "报告不应包含协议调用细节"
    assert "gitDiff" not in report, "报告不应包含工具名"

    assert llm.turns >= 3, f"应至少 3 轮（分类+2 次分析），实际 {llm.turns}"

    # extract_and_save: 提取一致 + 落盘（临时报告目录）
    old_dir = config.REPORT_DIR
    with tempfile.TemporaryDirectory() as td:
        config.REPORT_DIR = Path(td)
        try:
            saved, out_path = extract_and_save(raw, "testrepo", base, head, ptype,
                                               "https://example.com/r.git")
            assert saved == report, "extract_and_save 提取应与 extract 一致"
            assert out_path.name == f"testrepo-{head[:10]}.md", out_path.name
            content = out_path.read_text(encoding="utf-8")
            assert "- repo: https://example.com/r.git" in content
            assert "- type: bugfix" in content
            assert REPORT_START not in saved
        finally:
            config.REPORT_DIR = old_dir
    print(f"OK  报告落盘（extract_and_save 提取一致 + 头模板）")

    print(f"PASS  pipeline e2e, turns={llm.turns}")
    print("--- 报告预览 ---")
    print(report[:300])


if __name__ == "__main__":
    main()
