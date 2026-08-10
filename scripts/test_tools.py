"""工具层端到端测试：错误契约断言 + 对测试仓库逐个调用工具。

用法: python scripts\test_tools.py <repo>
"""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from rca import config
from rca.tools import REGISTRY, execute_tool
from rca.tools.base import ToolSpec, register

REPO = Path(sys.argv[1]).resolve()

# ---------- 错误契约(不需要仓库) ----------

# 1) 未知工具
out = execute_tool("noSuchTool", {}, REPO)
assert out.startswith("[tool error] 未知工具: noSuchTool"), out

# 2) 缺参(required 全部列出)
out = execute_tool("gitDiff", {}, REPO)
assert out == "[tool error] gitDiff: 缺少参数: base_ref, head_ref", out

# 3) 类型错(integer 字段传字符串数字可转换;传非数字报错)
out = execute_tool("gitLog", {"max_count": "abc"}, REPO)
assert out.startswith("[tool error] gitLog: 参数 max_count 类型错误"), out

# 4) enum 越界
out = execute_tool("gitShow", {"ref": "HEAD", "mode": "bogus"}, REPO)
assert out.startswith("[tool error] gitShow: 参数 mode 必须是以下之一"), out

# 5) 业务错误统一前缀(read 不存在的文件)
out = execute_tool("read", {"path": "no-such-file.py"}, REPO)
assert out == "[tool error] read: 文件不存在或不是文件: no-such-file.py", out

# 6) 条件必填留在工具内(snapshot 模式缺 path)
out = execute_tool("gitShow", {"ref": "HEAD", "mode": "snapshot"}, REPO)
assert out == "[tool error] gitShow: snapshot 模式需要 path 参数", out

# 7) 内部意外异常兜底
def _boom(args, repo):
    raise RuntimeError("boom")


register(ToolSpec(name="test_boom", description="", parameters={}, fn=_boom))
out = execute_tool("test_boom", {}, REPO)
assert out == "[tool error] test_boom 执行失败: boom", out
del REGISTRY["test_boom"]

# 8) 输出截断统一在出口
old_max = config.MAX_TOOL_OUTPUT
config.MAX_TOOL_OUTPUT = 100
register(ToolSpec(name="test_long", description="", parameters={},
                  fn=lambda a, r: "x" * 500))
out = execute_tool("test_long", {}, REPO)
assert "输出过长" in out and len(out) < 500, out
del REGISTRY["test_long"]
config.MAX_TOOL_OUTPUT = old_max

# 9) integer 自动转换 + 宽容(未知参数从返回值剔除,不传给工具函数)
def _probe(args, repo):
    assert "bogus_key" not in args, f"未知参数应被剔除: {args}"
    assert "max_count" in args and args["max_count"] == 3, f"integer 应转换: {args}"
    return "probe-ok"


register(ToolSpec(name="test_probe", description="", parameters={
    "type": "object",
    "properties": {"max_count": {"type": "integer"}},
}, fn=_probe))
out = execute_tool("test_probe", {"max_count": "3", "bogus_key": 1}, REPO)
assert out == "probe-ok", out
del REGISTRY["test_probe"]

out = execute_tool("gitLog", {"max_count": "3", "bogus_key": 1}, REPO)
assert not out.startswith("[tool error]"), out

print("OK  错误契约 9 项")

# ---------- 正常路径(真实仓库) ----------

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
