# Garden 风格报告 Harness 架构

## 1. 设计目标

本项目借鉴 [ConardLi/garden-skills](https://github.com/ConardLi/garden-skills) 及其 [web-video-presentation](https://github.com/ConardLi/garden-skills/tree/main/skills/web-video-presentation) 的工程方法，不复制其视觉领域实现。

目标是把多准则报告工作固化为一个可安装、可复跑、可检查、可降级的 Agent Skill Harness，使不同 Agent 在相同输入和确认结果下，稳定地产生结构一致、可追溯的中间产物和业务交付物。

本文档是实现架构说明，必须服从 [PRD.md](./PRD.md) 定义的外部行为、公共路径和公共数据契约，不得以实现便利为由改变 PRD。

## 2. 借鉴原则

| Garden 方法 | 本项目对应设计 |
| --- | --- |
| `SKILL.md` 固定完整工作流 | `SKILL.md` 负责编排、提问、读取阶段参考和调用脚本 |
| 硬性 Checkpoint | 数据授权、项目计划、证据缺口、首章样稿、完整母版、导出前检查 |
| 按阶段读取 references | 证据、映射、起草、评价、适配和导出各有独立协议 |
| 确定性 scaffold 脚本 | `scaffold_project` 创建固定项目目录和初始配置 |
| 模板提供稳定原语 | 提供项目模板、母版结构、矩阵字段和内容标记协议 |
| 单一真相源防止漂移 | `disclosure_ledger.jsonl` 统一保存要求、证据、正文和评价关系 |
| 每阶段自检并修复 | 每阶段执行 validator，修复失败项后才能进入下一 Checkpoint |
| 能力检测和降级 | 根据 Agent、模型、文件工具和联网权限选择模式并说明限制 |
| manifest 和固定版本发布 | Skill 包含 `manifest.json`，发布不可变版本和校验值 |

## 3. 仓库目标结构

```text
report-agent/
├── AGENTS.md
├── REQUIREMENTS.md
├── PRD.md
├── PROJECT_PLAN.md
├── HARNESS_ARCHITECTURE.md
├── skills/
│   └── sustainability-report-harness/
│       ├── SKILL.md
│       ├── manifest.json
│       ├── references/
│       │   ├── PROJECT-BRIEF.md
│       │   ├── EVIDENCE-PROTOCOL.md
│       │   ├── MAPPING-PROTOCOL.md
│       │   ├── OUTLINE-FORMAT.md
│       │   ├── DRAFTING-PROTOCOL.md
│       │   ├── ASSESSMENT-PROTOCOL.md
│       │   ├── ADAPTATION-PROTOCOL.md
│       │   └── QA-CHECKLISTS.md
│       ├── scripts/
│       │   ├── scaffold_project.py
│       │   ├── standards.py
│       │   ├── ingest_sources.py
│       │   ├── build_requirement_union.py
│       │   ├── review_requirement_union.py
│       │   ├── validate_project.py
│       │   ├── validate_ledger.py
│       │   └── preflight_export.py
│       ├── templates/project/
│       └── standards/fixtures/    # M1 仅允许模拟规则
├── tests/
└── examples/
```

业务逻辑尽量随 Skill 包分发。只有跨 Skill 共用且稳定的代码才提升为仓库级共享模块。

## 4. 生成项目结构

```text
client-project/
├── project.yaml
├── brief.md                       # 已确认项目规格
├── sources/
│   ├── client/
│   ├── peer/
│   └── requirements/
├── state/
│   ├── workflow.json
│   ├── standards.lock.json           # 锁定准则后生成
│   ├── source_manifest.jsonl
│   ├── evidence.jsonl
│   ├── requirement_union.json        # 构建并集后生成
│   ├── disclosure_ledger.jsonl    # 唯一真相源
│   └── outline.md
├── drafts/
│   ├── master/
│   └── adaptations/
├── outputs/
│   ├── internal/
│   └── clean/
└── logs/
```

`disclosure_ledger.jsonl` 中每个披露单元必须关联统一披露要求、原始准则条款、证据、正文内容、内容状态、回应状态、置信度和人工审阅状态。Word、Excel 和适配稿均由该账本派生，不得各自维护独立判断。

## 5. 固定工作流

### Phase 0：能力和数据边界检测

- 检测 Agent、文件解析能力、模型调用方式和联网权限；
- 获取并持久化项目级数据授权；
- 选择完整模式或明确降级模式；
- **Checkpoint Data**：确认数据处理授权和运行模式。

### Phase 1：确认项目规格与准则版本

- 读取用户说明、任务书、客户模板和参考报告；
- 生成并确认 `brief.md`；
- 顾问指定准则，系统推荐版本并等待顾问确认；
- 可生成候选 `outline.md`，但不得作为正式目录或进入母版生成；
- **Checkpoint Plan**：组合确认项目规格与准则版本。持久化时分别写入 `project_spec` 和 `standards`；只有两者均为 `approved` 时，Plan 才视为通过。参考方式和缺口处理模式属于 `project_spec`。

### Phase 2：证据、准则并集与正式目录

- 解析材料并生成证据库；
- M2 以项目相对路径、SHA-256 和解析器版本管理增量复用；Word 保留段落/表格位置，文本型 PDF 保留页/文本块位置，Excel 保留工作表/单元格范围；
- 扫描版或无可提取文本的 PDF 标记为 `needs_ocr`，不得生成伪证据或推进状态；
- 构建统一披露要求和 `disclosure_ledger.jsonl`；
- M3 将已确认准则包完整复制到 `standards.lock.json`，以原始条款清单证明拆解无静默丢失，并以内容哈希防止规则漂移；
- 每条可检查要求必须且只能进入一个统一披露要求；映射类型、差异、证据关系、矛盾证据和缺口写入账本；
- Agent 新映射默认 `unreviewed`，确定性脚本不得替顾问接受语义判断；
- **Checkpoint Evidence**：确认关键缺口、未经审核映射和冲突证据。
- 基于已确认准则并集和证据覆盖生成正式 `outline.md`；
- **Checkpoint Outline**：确认章节、篇幅、颗粒度、准则覆盖和预计缺口。

### Phase 3：首章 Anchor

- 选择一个代表性章节，完整生成正文、证据关联、矩阵行和缺口；
- 执行起草与评价自检；
- **Checkpoint Anchor**：顾问确认颗粒度、文风、标记和评价方式。

首章未通过前不得批量生成其余章节。

### Phase 4：完整母版

- 按已确认 Anchor 生成剩余章节；
- 每章完成后校验账本、覆盖和内容状态；
- **Checkpoint Master**：顾问审阅完整母版、回应矩阵和缺口。

### Phase 5：适配与导出

- 按目标准则从母版派生适配稿；
- 执行 Word、Excel 和账本一致性检查；
- **Checkpoint Export**：处理未确认内容后生成干净版。

## 6. 强制质量协议

每个阶段必须遵循“生成 → 校验 → 修复 → 再校验 → 汇报”。只生成检查报告但不修复失败项，不得视为完成。

检查执行优先级：独立 reviewer Agent、subagent、主 Agent 严格自检。三种方式使用同一检查表。

确定性脚本负责检查模式有效性、ID 唯一性、引用完整性、条款覆盖、证据定位、未确认内容、输出字段和文件命名。模型或人工负责检查语义映射、证据支持程度、正文质量、同业比较和改进建议。

## 7. 运行模式与降级

| 模式 | 条件 | 能力 |
| --- | --- | --- |
| Full | 可运行本地脚本且允许所需模型调用 | 完整解析、映射、起草、校验和导出 |
| Local Restricted | 禁止客户原文外发 | 本地解析和确定性检查；语义能力按本地条件降级 |
| Advisor | Agent 无法执行脚本 | 只提供计划和人工操作指引，不声称生成可验证产物 |

Agent 必须在开始时说明模式，不得静默切换。

## 8. M1 最小交付

- 可安装的 Skill 目录、`SKILL.md` 和 `manifest.json`；
- 项目脚手架和固定目录；
- `project.yaml` 与 `disclosure_ledger.jsonl` 模式；
- 项目、账本和导出前 validator；
- 阶段参考文件骨架和 QA 检查表；
- 模拟准则、示例项目和自动化测试；
- 单一 Agent 可走通 Phase 0 至 Phase 1，并验证状态持久化；
- Skill 包可复制到 Codex 扫描目录，同时保留跨 Agent 兼容格式。

## 9. 明确不借鉴

- 不复制 Garden 的视觉主题、React 模板或视频阶段模型；
- 不把全部逻辑塞入一个超长 `SKILL.md`；
- 不用自然语言约束替代可执行校验；
- 不在未建立真实业务基准前批量生成正式准则映射；
- 不先建设数据库服务、Web UI 或复杂多 Agent 平台。
