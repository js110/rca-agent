# rca-agent

MR 根因分析智能体：接收 GitHub PR webhook，克隆/增量更新仓库，按 diff 分类 PR 类型，加载对应分析框架，用工具循环（git 工具 + code-review-graph 代码图谱，测试注释）自动调查并输出根因分析报告，回写 PR 评论。

```
GitHub webhook ──> rca-agent
                     │ 1. clone / 增量 fetch，checkout head
                     ▼
                  ① 分类任务（pr-classification-template.md）→ TYPE: bugfix|feature|refactor|perf|config|other
                     ▼
                  ② 分派 → 加载分析框架（prompts/*-analysis-framework.md）
                     ▼
                  ③ 图谱 warm-start（code-review-graph）
                     ▼
                  ④ 工具循环：TOOL_CALL 文本协议 ↔ read/glob/git* /graph_*
                     ▼
                  ⑤ 报告（<!--RCA-REPORT-START--> 起始）→ 存 reports/ + 回写 PR 评论
```

## 安装

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
.venv\Scripts\pip install -r requirements.txt   # Linux/macOS: 用 .venv/bin/pip
```

配置 `.env`（参考 `.env.example`）：

```
RCA_OPENAI_API_KEY=你的key
RCA_OPENAI_BASE_URL=https://api.stepfun.com/step_plan/v1   # 任意 OpenAI 兼容端点
RCA_MODEL=step-3.7-flash
RCA_GITHUB_TOKEN=可选，回写 PR 评论用
RCA_WEBHOOK_SECRET=可选，校验 GitHub webhook 签名
```

## 用法

CLI 分析一个 MR（仓库 URL 或本地路径）：

```
.venv\Scripts\python -m rca.cli analyze --repo <url|path> --base <base_sha> --head <head_sha> [--title ...] [--desc ...] [--type bugfix]
```

只分类：`python -m rca.cli classify --repo ... --base ... --head ...`

启动 webhook 服务：

```
.venv\Scripts\python -m rca.cli serve --port 8000
# GitHub 仓库 → Settings → Webhooks → URL: https://<host>/webhook/github
# 事件选 Pull requests；配 Secret 后设 RCA_WEBHOOK_SECRET
```

## 工具

| 工具 | 说明 |
|---|---|
| read / glob | 文件读取（行范围）/ 通配符匹配 |
| gitLog / gitDiff / gitShow / gitShowStat | 提交历史 / 任意 ref 差异 / commit 快照·diff·文件 / 修改统计 |
| gitGrep / gitBlame / gitPickaxe | 正则搜索（排除锁文件/二进制）/ 按 commit 分组的行归属 / 按内容定位引入 commit |
| graph_query / graph_impact / graph_review | 代码图谱（code-review-graph）：调用链查询 / 爆炸半径 / 风险评分。图谱未构建时返回 unavailable，自动降级文本工具 |

## 提示词

`prompts/` 下：分类模板、分析系统提示词（类型软容错/证据规范/硬性禁令）、五种类型分析框架。管线流程见 `prompts/README.md`。

## 测试

```
.venv\Scripts\python scripts\make_test_repo.py <dir>   # 造三提交测试仓库（v1→v2 引入 bug→v3 修复）
.venv\Scripts\python scripts\test_tools.py <dir>       # 工具层
.venv\Scripts\python scripts\test_graph.py <dir> <base># CRG warm-start + 图谱工具
.venv\Scripts\python scripts\test_pipeline.py <dir> <base> <head>  # 管线（stub LLM，无需 key）
.venv\Scripts\python scripts\test_server.py            # webhook 服务
```

## 说明

- API key 只存于 `.env`（已 gitignore），不要把密钥提交到仓库。
- `code-review-graph` 需要 Python 3.10+，首次对某仓库分析会先建图（增量更新，通常数秒）。
