"""构造测试仓库：v1 功能 → v2 引入 bug → v3 bugfix（MR = base..head）。"""
import subprocess
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("testrepo")
REPO = REPO.resolve()


def git(*args, cwd=REPO):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True, encoding="utf-8")


REPO.mkdir(parents=True, exist_ok=True)

v1_main = """import calculator

def format_total(a, b):
    return f"total={calculator.add(a, b)}"

def safe_div(a, b):
    return calculator.div(a, b)
"""

v1_calc = """def add(a, b):
    return a + b

def div(a, b):
    return a / b
"""

# v2: 引入 bug —— div 的除数从分母改为硬编码 0 兜底，导致除零；add 增加了精度处理但丢失 float
v2_calc = """def add(a, b):
    return int(a) + int(b)

def div(a, b):
    if b == 0:
        return 0
    return a / b
"""

# v3: bugfix —— 修复 add 丢失 float 精度的问题（div 的兜底行为被保留，属于另一个隐患）
v3_calc = """def add(a, b):
    return float(a) + float(b)

def div(a, b):
    if b == 0:
        return 0
    return a / b
"""

v3_main = """import calculator

def format_total(a, b):
    return f"total={calculator.add(a, b)}"

def safe_div(a, b):
    return calculator.div(a, b)

def main():
    print(format_total(1.5, 2.5))
"""


def commit(msg: str):
    git("add", "-A")
    git("commit", "--quiet", "-m", msg)


git("init", "-q", "-b", "main")
git("config", "user.name", "tester")
git("config", "user.email", "tester@test.local")

(REPO / "calculator.py").write_text(v1_calc, encoding="utf-8")
(REPO / "main.py").write_text(v1_main, encoding="utf-8")
commit("feat: add calculator")

(REPO / "calculator.py").write_text(v2_calc, encoding="utf-8")
commit("fix: handle divide by zero, normalize add to int")

# MR 分支：base = 上面这个 commit，head = bugfix 分支
git("checkout", "-q", "-b", "bugfix/precision")
(REPO / "calculator.py").write_text(v3_calc, encoding="utf-8")
(REPO / "main.py").write_text(v3_main, encoding="utf-8")
commit("fix: preserve float precision in add")

base = git("rev-parse", "HEAD~1").stdout.strip()
head = git("rev-parse", "HEAD").stdout.strip()
print(f"repo={REPO}")
print(f"base={base}")
print(f"head={head}")
