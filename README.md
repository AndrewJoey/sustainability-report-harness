# 多准则可持续披露报告 AI 能力包

这是一个面向可持续发展、ESG 和气候披露咨询团队的本地 AI 能力包。它用于复用客户证据、统一映射多套披露准则，并从同一份披露母版派生不同准则的报告粗稿。

> 当前状态：M4 工程实现已完成。项目可以生成并审核正式目录、Anchor 和完整母版，导出内部 Word/Excel 审阅包，并在未确认内容存在时阻止干净版；真实专业验收仍待正式准则和脱敏样例。

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

当前 M4 Harness 可以：

- 创建符合 PRD 公共目录契约的本地项目；
- 校验 `project.yaml`、工作流和 `disclosure_ledger.jsonl`；
- 持久化和恢复流程状态及八个 Checkpoint；
- 阻止跳过前置确认节点；
- 在干净版导出前列出未确认内容和工作流阻塞项；
- 使用模拟规则和示例项目运行自动化验证；
- 解析本地 `.docx`、文本型 `.pdf` 和 `.xlsx` 客户或同行材料；
- 将 Word 段落/表格、PDF 页/文本块、Excel 工作表/单元格范围写入证据库；
- 记录 SHA-256、解析状态和证据 ID，第二次运行时复用未变化文件；
- 对扫描版 PDF 明确提示需要 OCR，并阻止错误推进。
- 按报告期间推荐准则版本，并由用户确认后锁定；
- 校验准则包的原始条款、拆解要求、审核信息和内容哈希；
- 将相同、相近和特有要求组成完整并集，阻止任何原始要求静默丢失；
- 记录 `direct`、`supporting`、`contradicting` 三类证据关系和明确缺口；
- 在映射、冲突证据和缺口未经用户确认时阻止进入报告目录阶段。
- 为扫描版 PDF 持久化用户选择的 OCR、补件或人工录入方案，不静默调用外部服务；
- 生成覆盖全部统一披露要求的正式目录，并明确选定 Anchor；
- 先生成和审核 Anchor，再生成完整母版，保留人工编辑；
- 分开记录准则回应评价和同行/最佳实践评价；
- 导出内部审阅 DOCX、回应矩阵、缺口清单、证据清单和独立同行评价表；
- 通过账本哈希、文件哈希、Checkpoint 和内容状态阻止过期或不安全的干净版导出。

产品和开发依据包括：

- [REQUIREMENTS.md](./REQUIREMENTS.md)：业务目标、范围和稳定验收基线；
- [PRD.md](./PRD.md)：功能规则、公共数据契约、状态机和验收用例；
- [HARNESS_ARCHITECTURE.md](./HARNESS_ARCHITECTURE.md)：Skill Harness 结构与质量协议；
- [PROJECT_PLAN.md](./PROJECT_PLAN.md)：当前状态、里程碑、依赖和交接说明；
- [AGENTS.md](./AGENTS.md)：开发约束和仓库规范。

## 使用方式

当前版本是一个可安装、可复制、可测试的本地 Agent Skill Harness。它已覆盖从项目创建到可审阅母版和内部业务文件导出的 M1–M4 工程链路。

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

Skill 的核心包位于：

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
│   ├── standards.lock.json       # 锁定准则后生成
│   ├── source_manifest.jsonl
│   ├── ocr_decisions.jsonl
│   ├── evidence.jsonl
│   ├── requirement_union.json    # 构建并集后生成
│   ├── disclosure_ledger.jsonl
│   ├── outline.json
│   └── outline.md
├── drafts/
│   ├── master/                   # Anchor 和完整母版的 JSON/Markdown 快照
│   └── adaptations/
├── outputs/
│   ├── internal/                 # DOCX、XLSX 与 export_manifest.json
│   └── clean/                    # 仅通过门禁后生成
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

### 5. 锁定准则版本

Agent 先基于报告期推荐版本，展示来源、生效日期、审核状态和内容哈希。顾问确认后再锁定：

```text
uv run python skills/sustainability-report-harness/scripts/standards.py lock \
  /absolute/path/to/client-project \
  --package /absolute/path/to/reviewed-standard.json \
  --confirmed-by "顾问姓名"
```

仓库中的 `simulated-standard-a.json` 和 `simulated-standard-b.json` 仅用于结构测试。只有开发测试时才能显式使用 `--allow-simulated`，不得把它们当成正式准则。

### 6. 构建证据库

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

结果保存在 `state/source_manifest.jsonl` 和 `state/evidence.jsonl`。重复运行时，路径、哈希和解析器版本均未变化的文件不会重新解析。当前支持 `.docx`、文本型 `.pdf` 和 `.xlsx`；Excel 公式会保留但不会假装重新计算。扫描版 PDF 会标记为需要 OCR，旧版 `.doc`、`.xls` 和加密 PDF 暂不支持。

扫描版 PDF 由用户选择本地 OCR、Agent 视觉、经授权的云 OCR、提供可搜索版本、人工录入、暂停，或在明确非关键时作为缺口跳过：

```text
uv run python skills/sustainability-report-harness/scripts/review_ocr.py decide \
  /absolute/path/to/client-project sources/client/scanned.pdf run_local_ocr \
  --criticality critical --decided-by "顾问姓名"
```

### 7. 构建多准则要求并集

Agent 根据已锁定规则和证据生成待审阅 mapping plan。所有 Agent 新映射必须为 `unreviewed`，然后运行：

```text
uv run python skills/sustainability-report-harness/scripts/build_requirement_union.py \
  /absolute/path/to/client-project \
  /absolute/path/to/mapping-plan.json
```

系统会写入 `state/disclosure_ledger.jsonl` 和 `state/requirement_union.json`，并停在 Evidence Checkpoint。

### 8. 记录人工审核并确认 Evidence Checkpoint

通过 `review_requirement_union.py` 分别记录映射、证据关系和缺口决定。所有事项完成后，由顾问明确执行：

```text
uv run python skills/sustainability-report-harness/scripts/review_requirement_union.py \
  /absolute/path/to/client-project finalize \
  --reviewed-by "顾问姓名"
```

存在未审核或被拒绝的映射、证据关系、冲突证据或缺口时，系统拒绝进入正式目录生成。
如果顾问要求重新分组或重做映射，可修正 mapping plan 后使用 `--replace`；未变化的人工决定会保留，变化项重新进入待审核状态。

### 9. 生成目录、Anchor 和母版

Agent 先按照 `templates/outline-plan.json.template` 生成 proposal，再运行：

```text
uv run python skills/sustainability-report-harness/scripts/build_outline.py \
  /absolute/path/to/client-project /absolute/path/to/outline-plan.json

uv run python skills/sustainability-report-harness/scripts/review_outline.py \
  /absolute/path/to/client-project approved --reviewed-by "顾问姓名"
```

正文 proposal 使用 `templates/draft-proposal.json.template`。`anchor` 只能覆盖已选 Anchor，获批后 `master` 才能覆盖其余章节：

```text
uv run python skills/sustainability-report-harness/scripts/build_draft.py \
  /absolute/path/to/client-project /absolute/path/to/anchor-proposal.json anchor

uv run python skills/sustainability-report-harness/scripts/review_draft.py finalize \
  /absolute/path/to/client-project anchor --reviewed-by "顾问姓名"
```

每个内容块、准则评价和同行评价都要先通过 `review_draft.py item` 接受、拒绝或编辑，才能 finalize。

### 10. 导出内部审阅包

```text
uv run python skills/sustainability-report-harness/scripts/export_project.py \
  /absolute/path/to/client-project internal
```

内部输出包括 `master_report_internal.docx`、`response_matrix.xlsx`、`gap_list.xlsx`、`evidence_list.xlsx`、`peer_assessment.xlsx` 和带哈希的 `export_manifest.json`。账本变更后旧输出会被判定为过期。

干净版还需要 Master 和 Export Checkpoint 获批，并通过预检：

```text
uv run python skills/sustainability-report-harness/scripts/export_project.py \
  /absolute/path/to/client-project clean
```

### 11. 通过人工确认节点

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

## M4 的交付边界

M4 在 M1–M3 基础上已交付：

- 自包含的 `sustainability-report-harness` Skill 包；
- 标准客户项目脚手架；
- `project.yaml` 和 `disclosure_ledger.jsonl` 模式；
- 可恢复的工作流与 Checkpoint 状态；
- 项目、账本和导出前校验器；
- 模拟规则、示例项目、自动化测试和开发说明；
- DOCX、文本型 PDF 和 XLSX 本地解析；
- 文件哈希、增量复用、证据定位和显式年份/单位提取；
- 扫描版 PDF、空文件、空资料集和解析错误的阻塞状态。
- 准则包、原始条款和可检查要求的完整性校验；
- 报告期版本推荐、用户确认锁定和防静默升级；
- 五类跨准则映射、统一披露并集和逐要求完整性检查；
- 证据多对多关系、矛盾证据、覆盖缺口和分准则覆盖摘要；
- 映射、证据关系和缺口的 Human-in-the-loop 审核与跨 Agent 恢复。
- 扫描 PDF 兜底选项发现、用户决策和源文件哈希绑定；
- 正式目录完整覆盖、冲突显示、Anchor 选定和 Outline Checkpoint；
- Anchor-first 与完整母版起草、逐项人工审核和人工编辑保护；
- 准则回应与同行最佳实践双轨评价；
- 内部 DOCX、四份 XLSX、导出清单及干净版阻断逻辑。

M4 不会交付：

- 正式监管准则知识库；
- 内置 OCR 引擎、旧版 `.doc`/`.xls` 和复杂嵌入对象解析；
- 正式监管准则内容和未经专家审核即可使用的语义映射；
- 未经顾问审核即可使用的正式报告成品；
- 准则适配稿；
- 第二个 Agent 适配层；
- Web 界面、数据库服务或 SaaS。

## 项目进度

M4 工程测试和 Skill 验证结果以 [PROJECT_PLAN.md](./PROJECT_PLAN.md) 为准。M4 的正式完成门槛仍包括一次顾问专业审阅；真实领域试用需要经过专业人员审核的准则拆解与映射、脱敏客户材料和人工认可的期望输出，不得用模型猜测代替。
