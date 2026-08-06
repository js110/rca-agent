"""工具层端到端测试：对测试仓库逐个调用工具。"""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from rca.tools import execute_tool

REPO = Path(sys.argv[1]).resolve()

cases = [
    ("read", {"path": "calculator.py"}),
    ("glob", {"pattern": "**/*.py"}),
    ("gitLog", {"max_count": 10}),
    ("gitDiff", {"base_ref": "HEAD~1", "head_ref": "HEAD"}),
    ("gitShow", {"ref": "HEAD~2", "mode": "snapshot", "path": "calculator.py"}),
    ("gitShowStat", {"ref": "HEAD"}),
    ("gitGrep", {"pattern": "float"}),
    ("gitBlame", {"path": "calculator.py"}),
    ("gitPickaxe", {"pattern": "float"}),
]
for name, args in cases:
    out = execute_tool(name, args, REPO)
    head = "\n".join(out.splitlines()[:8])
    print(f"=== {name} ({len(out)} chars) ===")
    print(head)
    print()
