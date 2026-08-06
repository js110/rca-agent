import sys, json
sys.path.insert(0, ".")
from rca.tools.base import REGISTRY
from rca.pipeline.analyze import build_system_prompt, parse_tool_call

print("tools:", sorted(REGISTRY))
proto = build_system_prompt()
print("protocol ok:", "graph_query" in proto and "TOOL_CALL" in proto)

raw = 'TOOL_CALL\n{"name": "gitDiff", "arguments": {"base_ref": "a", "head_ref": "b"}}'
c = parse_tool_call(raw)
print("parse ok:", c.name, c.args)

import rca.cli, rca.server
print("cli/server import ok")
