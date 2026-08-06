# prompts/ — RCA Agent 提示词管线

## 流水线：先分类，后分析

```
webhook 收到 MR
   │  1. 拉取/增量更新仓库，收集 MR 信息（title / description / diff / git log）
   ▼
① 分类任务（pr-classification-template.md）
   │  输入：MR 信息 → 输出：一行 TYPE: <bugfix|feature|refactor|perf|config|other>
   ▼
② 分派：按 TYPE 加载对应分析框架
   ▼
③ 分析任务（analysis-system-prompt.md + 对应框架模板）
   │  输入：系统提示词 + 框架模板 + MR 上下文
   │  输出：以 <!--RCA-REPORT-START--> 起始的正式报告
   ▼
报告回写 MR
```

## 分派表

| TYPE | 加载框架 |
|---|---|
| bugfix | bugfix-analysis-framework.md |
| feature | feature-analysis-framework.md |
| perf | perf-analysis-framework.md |
| refactor | refactor-analysis-framework.md |
| config | chore-analysis-framework.md（依赖/构建/CI 影响） |
| other | 无框架，按 analysis 系统提示词硬性禁令 #2：trivial 直接「无风险」；有实质行为变化则就近选框架 |

## 分析任务输入组装

- System：analysis-system-prompt.md
- User message：
  1. 对应类型的框架模板全文（决定报告章节结构，每步对应一个 `##` 二级标题）
  2. MR 上下文：title / description / git diff / 变更文件列表 / git log
  3. 「节省上下文」section（可选）：变更行的 blame 溯源、变更文件历史——**一旦附带，分析端不得再用 gitPickaxe / gitBlame 重复拉同一信息**

## 约定

- 分类输出必须被严格解析（一行 `TYPE: x`），解析失败则回退默认框架 bugfix 并标记 low confidence
- 分析报告只输出 `<!--RCA-REPORT-START-->` 之后的内容，之前的内容（工具调用、思考）被丢弃
- 类型软容错：分析端发现实际变更性质与 TYPE 不符时，在报告第一段声明差异，仍按原框架章节结构执行（见 analysis-system-prompt.md）
