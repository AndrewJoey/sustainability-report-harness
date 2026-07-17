# Sustainability Report Harness

一个给可持续发展、ESG 和气候披露顾问使用的本地 AI Skill。它读取客户资料和已审核的准则包，先形成覆盖所选准则并集的报告母版，再为每套准则生成独立 Markdown 初版。

> 当前是内部试用版。它帮助顾问整理证据和起草报告，不提供合规认证，也不能替代顾问、法律、审计或鉴证判断。

## 你会得到什么

一次完整运行默认生成：

```text
outputs/markdown/
├── master_report.md                 # 所选准则要求并集的母版
├── adapted_<standard-id>.md         # 每个已确认准则各一份
└── report_manifest.json             # 输入和输出哈希，用于发现过期结果
```

对应的完整相对路径是 `outputs/markdown/master_report.md`、
`outputs/markdown/adapted_<standard-id>.md` 和
`outputs/markdown/report_manifest.json`。

Markdown 会保留：

- `[待确认-推断]`：根据现有资料推断，尚未确认；
- `[建议文本]`：建议写法，不是客户事实；
- `[信息缺口]`：当前资料不足；
- HTML 注释中的内容 ID 和证据 ID，方便内部追溯。

现有 DOCX/XLSX 内部审阅功能仍然保留，但不是当前 MVP 的主交付。Word 模板化输出属于后续增强。

## 最简单的使用方式

把本仓库交给能够读取 Skill 并执行本地脚本的 AI Agent，然后直接说：

```text
请使用 sustainability-report-harness 创建一个报告项目。
先向我确认所需资料和报告要求，不要直接开始生成。
```

Agent 应先询问：

1. 客户材料有哪些；
2. 是否有既有报告或客户模板；
3. 需要使用哪些交易所规则或报告框架；
4. 是否有优秀报告案例，以及它们用于风格参考、质量标杆还是两者；
5. 报告用途、目标读者、文风和必须覆盖的议题。

优秀案例不是必填项，但必须由用户明确回答“提供”或“不提供”。客户材料和至少一套目标准则是生成报告的必要输入。

## 安装

需要 Python 3.11+ 和 `uv`。在仓库根目录运行：

```text
make install
```

常用开发检查：

```text
make test       # 自动化测试
make lint       # 静态检查
make format     # 格式化并刷新 Skill 哈希
make validate   # 校验 Skill、Schema 和示例项目
```

Skill 包位于 `skills/sustainability-report-harness/`。复制时必须保留整个目录，不能只复制 `SKILL.md`，因为脚本、模板、Schema 和参考协议都使用相对路径。

### Codex

可以直接在本仓库使用 Skill，或把整个 Skill 目录复制到个人 Skills 目录。然后在对话中明确要求使用 `sustainability-report-harness`。

### Claude Code

把整个 Skill 目录复制或链接为：

```text
.claude/skills/sustainability-report-harness/
```

在 Claude Code 中要求它先读取该 Skill，再读取客户项目中的 `project.yaml`、`state/workflow.json` 和 `state/handoff.json`。

### WorkBuddy 和 Trae

当前采用通用接入方式：让 Agent 的项目指令读取完整 `SKILL.md`，并允许它执行同目录下的 Python 脚本。若产品支持项目级 Skills 目录，可将完整 Skill 包放入该目录；目录名称不同，应以对应产品的当前说明为准。

MVP 只验证通用 Skill、项目状态、确定性命令和独立进程接续，不要求在 Claude Code、WorkBuddy 或 Trae 上做真实外部调用，也不宣称这些产品已经实测。

## 手动创建一个项目

大多数用户不需要手动运行命令；下面的方式适合排查问题或开发验证。

### 1. 创建项目目录

```text
uv run python skills/sustainability-report-harness/scripts/scaffold_project.py \
  /absolute/path/to/client-project \
  --project-id example-project \
  --project-name "示例项目" \
  --client-name "示例客户" \
  --period-start 2025-01-01 \
  --period-end 2025-12-31
```

真实客户项目应放在本仓库之外，且不得提交到 GitHub。

### 2. 放入材料

```text
client-project/sources/client/        客户事实材料、既有报告
client-project/sources/requirements/  客户任务书或模板
client-project/sources/peer/          可选优秀案例
```

当前支持 `.docx`、文本型 `.pdf` 和 `.xlsx`。扫描 PDF 会暂停并让用户选择本地 OCR、经授权的其他方式、补充可搜索文件或人工录入；Harness 不会静默上传资料或假装解析成功。

### 3. 确认问询结果

先记录本项目的数据处理授权并进入规格确认阶段：

```text
uv run python skills/sustainability-report-harness/scripts/workflow.py \
  /absolute/path/to/client-project transition awaiting_data_consent

uv run python skills/sustainability-report-harness/scripts/workflow.py \
  /absolute/path/to/client-project checkpoint data_consent approved \
  --approved-by "顾问姓名"

uv run python skills/sustainability-report-harness/scripts/workflow.py \
  /absolute/path/to/client-project transition awaiting_spec_confirmation
```

然后从 `skills/sustainability-report-harness/templates/intake.json.template` 复制一份回答文件，填写项目内的相对路径，并由用户确认：

```text
uv run python skills/sustainability-report-harness/scripts/confirm_intake.py confirm \
  /absolute/path/to/client-project \
  /absolute/path/to/intake.json \
  --confirmed-by "顾问姓名"
```

结果保存到 `state/intake.json`。目标准则、参考案例选择和报告偏好不会只留在聊天记录中。

### 4. 导入并锁定准则

准则内容必须来自顾问导入且已经审核的结构化准则包。Agent 可以推荐报告期适用版本，但不能自行决定企业适用哪套准则，也不能静默升级版本。

```text
uv run python skills/sustainability-report-harness/scripts/standards.py lock \
  /absolute/path/to/client-project \
  --package /absolute/path/to/reviewed-standard.json \
  --confirmed-by "顾问姓名"
```

仓库中的 `simulated-standard-a.json` 和 `simulated-standard-b.json` 只用于自动化测试，不是正式准则。

### 5. 继续证据、映射和起草流程

Agent 会按以下顺序推进，并在关键节点等待顾问确认：

```text
资料解析 → 准则要求并集 → Evidence 确认 → 正式目录 → Anchor 章节
→ 完整母版 → 逐准则适配 → Markdown 交付
```

项目状态保存在本地文件，不依赖某一次聊天。换一个 Agent 或重新打开项目时，应从现有状态继续，不重复解析没有变化的文件，不覆盖人工修改。

### 6. 生成 Markdown

完成母版确认并建立全部准则适配方案后运行：

```text
uv run python skills/sustainability-report-harness/scripts/export_markdown.py generate \
  /absolute/path/to/client-project
```

检查结果是否仍然有效：

```text
uv run python skills/sustainability-report-harness/scripts/export_markdown.py validate \
  /absolute/path/to/client-project
```

如果客户材料、优秀案例、模板、账本、目录、准则锁、intake 或输出文件发生变化，哈希校验会提示重新生成。

## 数据与安全边界

- 默认本地处理，云端模型、联网、脱敏和文件保留方式按项目确认；
- 客户事实必须引用客户证据；优秀案例只能用于结构、表达或质量对标；
- OCR 无可用工具时必须让用户选择，不自动调用云服务；
- 正式准则必须由专业人员审核后导入；
- `state/disclosure_ledger.jsonl` 是业务判断的唯一真相源，Markdown、Word 和 Excel 都只能从它派生。

## 当前尚未完成

- 正式交易所准则内容不会随仓库分发；
- 仍需要正式准则、脱敏客户材料和顾问期望稿完成专业试用；
- 英文版、复杂篇幅控制、基础数据一致性和客户 Word 模板属于后续增强；
- Claude Code、WorkBuddy 和 Trae 提供通用接入说明，但不属于本 MVP 的真实环境验收范围。

开发状态和验收边界见 [PROJECT_PLAN.md](./PROJECT_PLAN.md)，产品契约见 [PRD.md](./PRD.md) 和 [REQUIREMENTS.md](./REQUIREMENTS.md)。
