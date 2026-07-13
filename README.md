# 多准则可持续披露报告 AI 能力包

这是一个面向可持续发展、ESG 和气候披露咨询团队的本地 AI 能力包。它用于复用客户证据、统一映射多套披露准则，并从同一份披露母版派生不同准则的报告粗稿。

> 当前状态：M2 证据库已经完成。项目可以解析本地 DOCX、文本型 PDF 和 XLSX，保留证据位置，并按文件哈希复用未变化资料；语义映射和报告生成将在 M3–M5 实现。

## 产品会帮助你完成什么

完整 MVP 计划支持以下流程：

1. 创建本地报告项目并确认数据处理边界；
2. 确认客户、报告期间、报告规格和适用准则版本；
3. 解析 Word、文本型 PDF 和 Excel 客户材料；
4. 建立可定位、可复用的客户证据库；
5. 将多套准则合并为统一披露要求；
6. 生成中文母版粗稿、回应矩阵、缺口清单和证据清单；
7. 从母版派生特定准则的适配粗稿；
8. 在导出干净版前拦截未确认的推断、建议文本和信息缺口。

本产品是咨询团队的内部专业辅助工具，不提供正式合规认证，也不替代顾问、法律、审计或鉴证判断。

## 当前可以做什么

当前 M2 Harness 可以：

- 创建符合 PRD 公共目录契约的本地项目；
- 校验 `project.yaml`、工作流和 `disclosure_ledger.jsonl`；
- 持久化和恢复流程状态及八个 Checkpoint；
- 阻止跳过前置确认节点；
- 在干净版导出前列出未确认内容和工作流阻塞项；
- 使用模拟规则和示例项目运行自动化验证。
- 解析本地 `.docx`、文本型 `.pdf` 和 `.xlsx` 客户或同行材料；
- 将 Word 段落/表格、PDF 页/文本块、Excel 工作表/单元格范围写入证据库；
- 记录 SHA-256、解析状态和证据 ID，第二次运行时复用未变化文件；
- 对扫描版 PDF 明确提示需要 OCR，并阻止错误推进。

产品和开发依据包括：

- [REQUIREMENTS.md](./REQUIREMENTS.md)：业务目标、范围和稳定验收基线；
- [PRD.md](./PRD.md)：功能规则、公共数据契约、状态机和验收用例；
- [HARNESS_ARCHITECTURE.md](./HARNESS_ARCHITECTURE.md)：Skill Harness 结构与质量协议；
- [PROJECT_PLAN.md](./PROJECT_PLAN.md)：当前状态、里程碑、依赖和交接说明；
- [AGENTS.md](./AGENTS.md)：开发约束和仓库规范。

## 使用方式

当前版本是一个可安装、可复制、可测试的本地 Agent Skill Harness。它已覆盖项目创建、流程状态、数据契约和证据资料解析，但不包含完整报告生成能力。

### 1. 安装 Harness

需要 Python 3.11+ 和 `uv`。在仓库根目录运行：

```text
make install
```

项目使用 `uv.lock` 安装固定版本依赖。统一开发命令为：

```text
make install     安装锁定的开发依赖
make test        运行完整自动化测试
make lint        运行静态检查但不改写文件
make format      应用格式化规则并刷新 Skill 校验值
make validate    校验 Skill、模式和示例项目
```

### 2. 在 Agent 中启用 Skill

M1 的核心包位于：

```text
skills/sustainability-report-harness/
```

该目录包含 `SKILL.md`、版本清单、分阶段参考协议、确定性脚本、项目模板和明确标记的模拟准则夹具。使用时可让 Agent 直接读取当前仓库中的 Skill，或将整个目录复制到受支持 Agent 的个人 Skill 目录。

在 Codex 中可直接提出类似请求：

```text
使用 $sustainability-report-harness 创建一个本地可持续披露报告项目。
```

### 3. 创建本地客户项目

通过 Agent 使用时，它应先询问下列信息。也可以直接运行脚手架命令：

```text
uv run python skills/sustainability-report-harness/scripts/scaffold_project.py \
  /absolute/path/to/client-project \
  --project-id example-project \
  --project-name "示例项目" \
  --client-name "示例客户" \
  --period-start 2025-01-01 \
  --period-end 2025-12-31
```

需要确认的信息包括：

- 客户和报告期间；
- 报告类型、篇幅和颗粒度；
- 数据是否允许发送到云端模型；
- 是否允许联网搜索；
- 是否需要脱敏；
- 中间文件的保留方式；
- 由顾问指定的适用准则及其版本。

确认后，Harness 将创建以下结构：

```text
client-project/
├── project.yaml
├── brief.md
├── sources/
│   ├── client/
│   ├── peer/
│   └── requirements/
├── state/
│   ├── workflow.json
│   ├── source_manifest.jsonl
│   ├── evidence.jsonl
│   ├── disclosure_ledger.jsonl
│   └── outline.md
├── drafts/
│   ├── master/
│   └── adaptations/
├── outputs/
│   ├── internal/
│   └── clean/
└── logs/
```

生成的客户项目应存放在源码目录之外。不要把真实客户材料提交到仓库。

### 4. 继续已有项目

项目状态保存在项目目录而不是 Agent 对话中。重新打开项目时，Agent 应读取 `project.yaml`、`state/workflow.json` 和相关账本，从最近完成的步骤继续，不重复处理未变化的文件，也不覆盖人工修改。

可以直接查看状态或验证项目：

```text
uv run python skills/sustainability-report-harness/scripts/workflow.py \
  /absolute/path/to/client-project status

uv run python skills/sustainability-report-harness/scripts/validate_project.py \
  /absolute/path/to/client-project
```

### 5. 构建证据库

完成数据授权、项目规格和准则版本确认后，将资料放入：

```text
sources/client/    客户事实材料
sources/peer/      同行参考材料
```

然后运行：

```text
uv run python skills/sustainability-report-harness/scripts/ingest_sources.py \
  /absolute/path/to/client-project
```

结果保存在 `state/source_manifest.jsonl` 和 `state/evidence.jsonl`。重复运行时，路径、哈希和解析器版本均未变化的文件不会重新解析。当前支持 `.docx`、文本型 `.pdf` 和 `.xlsx`；扫描版 PDF 会标记为需要 OCR，旧版 `.doc`、`.xls` 和加密 PDF 暂不支持。

### 6. 通过人工确认节点

工作流包含不可绕过的确认节点：

- 数据处理授权；
- 项目规格和准则版本；
- 证据缺口、映射及冲突；
- 正式目录；
- 代表性 Anchor 章节；
- 完整母版；
- 干净版导出前检查。

每个阶段遵循“生成 → 校验 → 修复 → 再校验 → 汇报”。前置确认未通过时，Harness 不得进入下一阶段。

## 数据安全与内容真实性

- 客户材料默认保存在本地；
- 未经项目级确认，不向外部服务发送客户内部材料；
- 联网搜索不得携带客户内部材料；
- 同行报告只能用于风格或质量参考，不能作为客户事实证据；
- 正式准则必须记录来源、版本、生效日期和审核状态；
- 模拟规则不得标记或展示为正式监管规则；
- 推断、建议文本和信息缺口必须明确标记；
- 人工编辑、已确认准则版本和数据授权不得被静默覆盖。

## M2 的交付边界

M2 已交付：

- 自包含的 `sustainability-report-harness` Skill 包；
- 标准客户项目脚手架；
- `project.yaml` 和 `disclosure_ledger.jsonl` 模式；
- 可恢复的工作流与 Checkpoint 状态；
- 项目、账本和导出前校验器；
- 模拟规则、示例项目、自动化测试和开发说明。
- DOCX、文本型 PDF 和 XLSX 本地解析；
- 文件哈希、增量复用、证据定位和显式年份/单位提取；
- 扫描版 PDF、空文件、空资料集和解析错误的阻塞状态。

M2 不会交付：

- 正式监管准则知识库；
- 扫描版 PDF OCR、旧版 `.doc`/`.xls` 和复杂嵌入对象解析；
- 完整母版、矩阵或适配稿生成；
- 正式 Word、Excel 业务成品导出；
- 第二个 Agent 适配层；
- Web 界面、数据库服务或 SaaS。

## 项目进度

M2 已通过自动化测试和 Skill 验证。当前里程碑及 M3–M5 的阻塞输入以 [PROJECT_PLAN.md](./PROJECT_PLAN.md) 为准。真实领域试用仍需要经过专业人员审核的准则拆解与映射、脱敏客户材料以及人工认可的期望输出；不得用模型猜测代替。
