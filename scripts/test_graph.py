"""CRG warm-start + 图谱工具测试。"""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from rca.tools import execute_tool
from rca.tools import graph_tool

REPO = Path(sys.argv[1]).resolve()
BASE = sys.argv[2]

print("crg built before:", graph_tool.crg_built(REPO))
print("warm-start:", graph_tool.crg_warm_start(REPO, BASE))
print("crg built after:", graph_tool.crg_built(REPO))

for name, args in [
    ("graph_query", {"pattern": "callers_of", "target": "add"}),
    ("graph_impact", {"changed_files": ["calculator.py"], "base": BASE}),
    ("graph_review", {"base": BASE}),
]:
    out = execute_tool(name, args, REPO)
    print(f"=== {name} ({len(out)} chars) ===")
    print(out[:1500])
    print()
