# rca-agent 领域术语

## 核心概念

- **MR(Merge Request)/ PR** — 待分析的代码变更,由 GitHub webhook 事件提供,含 `base_ref`、`head_ref`、标题、描述。
- **分析工作区(PreparedCheckout)** — 已检出 `head_sha`、且可选带索引的仓库目录;是分析执行时的唯一工作目录。
- **Checkout 准备模块** — 把「仓库 URL + head_sha」变成分析工作区的模块(`rca/checkout.py`):内部决策走 worktree 方案(每分支独立 worktree + codegraph 索引,索引严格等于 head_sha)还是单 clone,任何一步失败自动回退单 clone,并负责 PR 关闭时的清理。外部只有 `prepare` / `cleanup` 两个入口,worktree 布局是其私有知识。
- **索引提供者(IndexProvider)** — Checkout 准备模块的注入点:`(base, branch, head_sha) → worktree 路径`,失败抛异常。测试注入永远失败的 fake 即可覆盖回退路径。
- **索引原语(codegraph 模块)** — 只管「索引怎么建、怎么拷、怎么对账」:codegraph CLI 封装、base 首次 init、向 worktree 播种 `.codegraph` 与 `.code-review-graph`、增量 sync。不含生命周期决策。
- **图谱 warm-start(CRG)** — 分析前对**分析工作区**增量构建/更新 code-review-graph,保证图谱 == head 的代码;成功后图谱工具才可用,否则返回 unavailable 让模型转文本工具。

## 管线环节

- **分类任务** — 判定 MR 类型:bugfix / feature / refactor / perf / config / other。
- **分派** — 类型 → 加载对应分析框架提示词(`prompts/*-analysis-framework.md`)。
- **MR 提示词渲染(mr_prompt 模块)** — 把 MRContext 的结构化证据与不可信数据声明组装成给 LLM 的「MR 上下文」文本;与证据收集(`rca/mr.py`)分层,渲染格式改动不碰 git 收集。
- **工具循环** — LLM 通过 TOOL_CALL 文本协议反复调用工具(gitLog / gitDiff / gitShow / gitGrep / gitBlame / gitPickaxe / read / glob / graph_query / graph_impact / graph_review)收集证据,直到输出以 `<!--RCA-REPORT-START-->` 开头的报告。
- **工具调用结果契约** — 工具错误一律由 `execute_tool` 出口渲染成 `[tool error] {工具名}: {消息}`(参数校验由 ToolSpec 的 JSON schema 生成);`[unavailable]` 是独立的降级信号(图谱未就绪,提示模型换文本工具),不是错误。
- **报告输出模块(report 模块)** — 报告域的全部知识:`<!--RCA-REPORT-START-->` 协议标记(全项目唯一出处,协议文本/提取都引用它)、从模型输出提取报告正文、落盘(文件名 `{仓库名}-{head_sha[:10]}.md` + 头模板)。
- **合并基线(merge-base)** — diff 口径:优先用 base 与 head 的共同祖先,而非 base 分支最新 tip(避免混入 PR 创建后的无关提交)。

## 安全与幂等

- **不可信数据声明** — PR 标题/描述/diff 全部视为数据而非指令(提示词注入防护);对外的评论再经凭据脱敏。
- **head_sha 去重** — 同一 PR 相同 head_sha 不重复分析。
- **sticky 评论** — 同一 PR 的后续分析以更新方式回写评论(先查上次的 comment_id)。
